# Prefill KVCache Store 的原始接口需求

以 vLLM-Ascend 对接社区 Mooncake Store 为例。Prefill 写出时，将已生成的 KV 从本地 HBM 存到指定 key。前缀命中时，将该 key 对应的 KV 读回本次请求使用的 HBM 位置。

## 1. HBM 内 KVCache 读写地址的管理

vLLM 的 KV cache manager 为请求分配或复用本地 KV 块，按 cache group 提供块表。vLLM-Ascend 的 connector worker 根据块表中的 `block_id` 和本地张量布局，把一次传输展开为一个或多个 `(HBM 地址, 字节数)`。对于一个 KV 分量，起始地址为 `分量基址 + block_id × 块步长 + 块内字节偏移`。步长决定相邻块的位置，字节数决定本次实际搬多少。[地址计算源码](https://github.com/vllm-project/vllm-ascend/blob/09317fc13a3daf2acb44e60dcb4b2ba877c24eca/vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/metadata.py#L477-L515)

调用方负责 HBM 缓冲区的生命周期。put 完成读取源区间后，调用方才可覆盖该区间。get 完成写入目标区间后，Attention 才可消费，待消费及其他在途访问完成后才可复用。按层共用 HBM 槽时，这个约束作用于每次复用的具体区间。[共享槽复用依赖](https://github.com/vllm-project/vllm-ascend/blob/09317fc13a3daf2acb44e60dcb4b2ba877c24eca/vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/layerwise/cache_planner.py#L235-L249)

## 2. key 到 HBM 地址的管理

**本次传输的映射由 vLLM-Ascend connector worker 建立。** 对同一个 cache group 的逻辑块位置 `i`，worker 将该位置的 Store key 与请求块表中的 `block_ids[i]` 配对，再按第 1 节的布局计算 HBM 地址列表。完整前缀块的 key 根据块哈希及模型、并行布局等信息构造。相同 key 在另一次请求中可以读入不同的本地块。Mooncake 每次调用都接收调用方给出的 HBM 地址。[块级配对](https://github.com/vllm-project/vllm-ascend/blob/09317fc13a3daf2acb44e60dcb4b2ba877c24eca/vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/kv_transfer.py#L916-L936) · [按层配对及地址展开](https://github.com/vllm-project/vllm-ascend/blob/09317fc13a3daf2acb44e60dcb4b2ba877c24eca/vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/layerwise/kv_transfer.py#L416-L475)

## 3. put 和 get 都按 key 访问

| 操作 | key 的含义 | HBM 地址的含义 |
| --- | --- | --- |
| put | 标识要写入的 Store 对象 | 源区间，Store 从这里读出 KV |
| get | 标识要读取的 Store 对象 | 目标区间，Store 将 KV 写入这里 |

接口需支持批量 key 和每个 key 的多段缓冲区。`keys[i]`、`buffers[i]`、`sizes[i]` 描述同一个对象，`buffers[i][j]` 与 `sizes[i][j]` 描述它的第 `j` 段 HBM 数据。调用方需要能判断每个 key 的传输结果。[Mooncake 整对象读写调用](https://github.com/vllm-project/vllm-ascend/blob/09317fc13a3daf2acb44e60dcb4b2ba877c24eca/vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/backend/mooncake_backend.py#L715-L776)

## 4. block-wise 和 layer-wise 的接口差异

| 接口需求 | block-wise | layer-wise |
| --- | --- | --- |
| 一次搬运的范围 | 每个 key 一次传输整个块对象，按顺序传入其各层、各分量的 HBM 地址及长度 | 同一块对象沿用同一 key。每次只传当前层各分量的 HBM 地址、长度及**对象内字节偏移** |
| put | `batch_put_from_multi_buffers` 一次写入整个对象 | `batch_put_session_start` 按 key 和对象总长度开始写入，逐层调用 `batch_put_from_multi_buffer_ranges` 指定目标偏移。各层写完后用 `batch_put_session_end` 提交，放弃写入用 `batch_put_session_revoke` |
| get | `batch_get_into_multi_buffers` 一次读回整个对象 | `batch_get_session_start` 开始读取，逐层调用 `batch_get_into_multi_buffer_ranges` 指定源偏移，用 `batch_get_session_end` 结束读取 |

layer-wise 有两个不同的完成时点。某层 range 写完成，意味着该次传输已读完该层的 HBM 源区间。整个 key 提交成功，意味着块对象已发布可读。共享槽可以据前者安排覆盖，前缀复用依赖后者。[vLLM-Ascend 的接口对应关系](https://github.com/vllm-project/vllm-ascend/blob/09317fc13a3daf2acb44e60dcb4b2ba877c24eca/vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/backend/mooncake_backend.py#L656-L713) · [社区 Mooncake 接口声明](https://github.com/kvcache-ai/Mooncake/blob/b524db2c89c795a0bd1b4df78c307f03f2b853b1/mooncake-store/include/real_client.h#L268-L305)
