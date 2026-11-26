# Prefill 与 Decode DSA Offload 的 KVCache Store 原始需求

## Prefill 与 Decode DSA 的 HBM 驻留差异

两条路径都按层、按 KV 分量确定 HBM 基址。差异在于当前层需要保留哪些 token、按什么粒度判断命中，以及 Store 读回时要填入哪些位置。

| 比较项 | Prefill（以全注意力、chunked prefill 为例） | Decode DSA（默认 `fused_copy_sfa` 路径） |
| --- | --- | --- |
| 每个请求在当前层的 KV | 计算当前 chunk 时，HBM 中需要有命中前缀的 KV、此前各 chunk 已算出的 KV，以及当前 chunk 新生成的 KV。 | HBM 中保留可跨 step 复用的历史热 KV，以及存放近期新 KV 的两个轮转尾块。热槽容量可以大于单步 Top‑K，例如每步选 2K 个 token，预留 8K 个热槽。 |
| 命中与复用粒度 | 以 block 查询前缀命中。块就绪后，Attention 直接按块内偏移访问所需 token。 | 稳态下对选中的历史 token 逐个判断驻留。命中时沿用原热槽，miss 时选择可替换槽，更新“请求内 token 位置 → 热槽”的映射。 |
| HBM 寻址 | 由当前层分量基址、本地 `block_id` 和块内偏移计算地址。启用层间共享槽时，不同层可在不同时刻复用同一基址。 | 由当前层分量基址、热槽和 HBM 块表定位物理行。两个尾块按序列进度轮转。 |
| Store 读回的目标 | 调用方按 key 指定本地 HBM 块对应的地址区间。block-wise 填整个块对象，layer-wise 填当前层的区间。 | vLLM-Ascend 在设备侧完成命中判断与逐出，为每个 miss 指定目标热槽。一次可将多个离散 token 行分别填入对应热槽。 |

实现依据见 [Prefill 块寻址](https://github.com/vllm-project/vllm-ascend/blob/09317fc13a3daf2acb44e60dcb4b2ba877c24eca/vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/metadata.py#L477-L515)、[Decode 热缓存与尾块分配](https://github.com/vllm-project/vllm-ascend/blob/09317fc13a3daf2acb44e60dcb4b2ba877c24eca/vllm_ascend/distributed/kv_transfer/sparse_kv_offload/sparse_kv_offload_manager.py#L114-L159) 和 [Decode 稳态命中与替换](https://github.com/vllm-project/vllm-ascend/blob/09317fc13a3daf2acb44e60dcb4b2ba877c24eca/csrc/attention/fused_lightning_indexer_manage/README.md#L89-L96)。

## Prefill KVCache Store

以 vLLM-Ascend 对接社区 Mooncake Store 为例。Prefill 写出时，将已生成的 KV 从本地 HBM 存到指定 key。前缀命中时，将该 key 对应的 KV 读回本次请求使用的 HBM 位置。

### 1. HBM 内 KVCache 读写地址的管理

vLLM 的 KV cache manager 为请求分配或复用本地 KV 块，按 cache group 提供块表。vLLM-Ascend 的 connector worker 根据块表中的 `block_id` 和本地张量布局，把一次传输展开为一个或多个 `(HBM 地址, 字节数)`。对于一个 KV 分量，起始地址为 `分量基址 + block_id × 块步长 + 块内字节偏移`。步长决定相邻块的位置，字节数决定本次实际搬多少。[地址计算源码](https://github.com/vllm-project/vllm-ascend/blob/09317fc13a3daf2acb44e60dcb4b2ba877c24eca/vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/metadata.py#L477-L515)

调用方负责 HBM 缓冲区的生命周期。put 完成读取源区间后，调用方才可覆盖该区间。get 完成写入目标区间后，Attention 才可消费，待消费及其他在途访问完成后才可复用。按层共用 HBM 槽时，这个约束作用于每次复用的具体区间。[共享槽复用依赖](https://github.com/vllm-project/vllm-ascend/blob/09317fc13a3daf2acb44e60dcb4b2ba877c24eca/vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/layerwise/cache_planner.py#L235-L249)

使用 Store 显式注册 HBM 缓冲区时，调用 `register_buffer(buffer_ptr: int, size: int) -> int`。`buffer_ptr` 是缓冲区基址（底层类型 `uintptr_t`），`size` 是整个注册区间的字节数（`size_t`），返回 0 表示注册成功。后续 put/get 可传入该区间内各数据段的起始地址。[Python 绑定](https://github.com/kvcache-ai/Mooncake/blob/b524db2c89c795a0bd1b4df78c307f03f2b853b1/mooncake-integration/store/store_py.cpp#L3199-L3209)

### 2. key 到 HBM 地址的管理

**本次传输的映射由 vLLM-Ascend connector worker 建立。** 对同一个 cache group 的逻辑块位置 `i`，worker 将该位置的 Store key 与请求块表中的 `block_ids[i]` 配对，再按第 1 节的布局计算 HBM 地址列表。完整前缀块的 key 根据块哈希及模型、并行布局等信息构造。相同 key 在另一次请求中可以读入不同的本地块。Mooncake 在每次数据搬运调用中接收调用方给出的 HBM 地址。[块级配对](https://github.com/vllm-project/vllm-ascend/blob/09317fc13a3daf2acb44e60dcb4b2ba877c24eca/vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/kv_transfer.py#L916-L936) · [按层配对及地址展开](https://github.com/vllm-project/vllm-ascend/blob/09317fc13a3daf2acb44e60dcb4b2ba877c24eca/vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/layerwise/kv_transfer.py#L416-L475)

### 3. put 和 get 都按 key 访问

| 操作 | key 的含义 | HBM 地址的含义 |
| --- | --- | --- |
| put | 标识要写入的 Store 对象 | 源区间，Store 从这里读出 KV |
| get | 标识要读取的 Store 对象 | 目标区间，Store 将 KV 写入这里 |

接口需支持批量 key 和每个 key 的多段缓冲区。`keys[i]`、`buffers[i]`、`sizes[i]` 描述同一个对象，`buffers[i][j]` 与 `sizes[i][j]` 描述它的第 `j` 段 HBM 数据。调用方需要能判断每个 key 的传输结果。[Mooncake 整对象读写调用](https://github.com/vllm-project/vllm-ascend/blob/09317fc13a3daf2acb44e60dcb4b2ba877c24eca/vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/backend/mooncake_backend.py#L715-L776)

### 4. block-wise 和 layer-wise 的接口差异

| 接口需求 | block-wise | layer-wise |
| --- | --- | --- |
| 一次搬运的范围 | 每个 key 一次传输整个块对象，按顺序传入其各层、各分量的 HBM 地址及长度 | 同一块对象沿用同一 key。每次只传当前层各分量的 HBM 地址、长度及**对象内字节偏移** |
| put | `batch_put_from_multi_buffers` 一次写入整个对象 | `batch_put_session_start` 按 key 和对象总长度开始写入，逐层调用 `batch_put_from_multi_buffer_ranges` 指定目标偏移。各层写完后用 `batch_put_session_end` 提交，放弃写入用 `batch_put_session_revoke` |
| get | `batch_get_into_multi_buffers` 一次读回整个对象 | `batch_get_session_start` 开始读取，逐层调用 `batch_get_into_multi_buffer_ranges` 指定源偏移，用 `batch_get_session_end` 结束读取 |

layer-wise 有两个不同的完成时点。某层 range 写完成，意味着该次传输已读完该层的 HBM 源区间。整个 key 提交成功，意味着块对象已发布可读。共享槽可以据前者安排覆盖，前缀复用依赖后者。[vLLM-Ascend 的接口对应关系](https://github.com/vllm-project/vllm-ascend/blob/09317fc13a3daf2acb44e60dcb4b2ba877c24eca/vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/backend/mooncake_backend.py#L656-L713) · [社区 Mooncake 接口声明](https://github.com/kvcache-ai/Mooncake/blob/b524db2c89c795a0bd1b4df78c307f03f2b853b1/mooncake-store/include/real_client.h#L268-L305)

#### Mooncake Python 接口签名

以下为 vLLM-Ascend 调用的 Store 实例方法，省略 `self`。默认值取自社区 Mooncake 的 Python 绑定。[绑定源码](https://github.com/kvcache-ai/Mooncake/blob/b524db2c89c795a0bd1b4df78c307f03f2b853b1/mooncake-integration/store/store_py.cpp#L3459-L3594)

**block-wise**

```python
def batch_put_from_multi_buffers(
    keys: list[str], all_buffer_ptrs: list[list[int]], all_sizes: list[list[int]],
    config: ReplicateConfig = ReplicateConfig(),
) -> list[int]: ...

def batch_get_into_multi_buffers(
    keys: list[str], all_buffer_ptrs: list[list[int]], all_sizes: list[list[int]],
    prefer_alloc_in_same_node: bool = False,
) -> list[int]: ...
```

**layer-wise 写入**

```python
def batch_put_session_start(
    keys: list[str], sizes: list[int], config: ReplicateConfig = ReplicateConfig(),
) -> list[int]: ...

def batch_put_from_multi_buffer_ranges(
    keys: list[str], all_buffer_ptrs: list[list[int]], all_sizes: list[list[int]],
    all_dst_offsets: list[list[int]],
) -> list[int]: ...

def batch_put_session_end(keys: list[str]) -> list[int]: ...
def batch_put_session_revoke(keys: list[str]) -> list[int]: ...
```

**layer-wise 读取**

```python
def batch_get_session_start(keys: list[str]) -> list[int]: ...

def batch_get_into_multi_buffer_ranges(
    keys: list[str], all_buffer_ptrs: list[list[int]], all_sizes: list[list[int]],
    all_src_offsets: list[list[int]],
) -> list[int]: ...

def batch_get_session_end(keys: list[str]) -> int: ...
```

#### 参数与返回值

下表中，`i` 是本次调用中 key 的下标，`j` 是该 key 在本次调用中的数据段下标。二维参数的外层长度等于 `len(keys)`。对同一个 `i`，地址、长度和 range 偏移按 `j` 一一对应。

| 参数 | Python 类型 | 调用方传什么 |
| --- | --- | --- |
| `keys` | `list[str]` | 本批对象的 key。逐层读写和会话结束时沿用对应会话的 key。 |
| `all_buffer_ptrs` | `list[list[int]]` | `[i][j]` 是第 `j` 段本地 HBM 起始地址，底层类型为 `uintptr_t`。put 传源地址，get 传目标地址。 |
| `all_sizes` | `list[list[int]]` | `[i][j]` 是该段本次搬运的字节数，底层类型为 `size_t`。 |
| `sizes` | `list[int]` | 仅用于开始写会话。`sizes[i]` 是要为整个对象预留的总字节数，覆盖将要写入的各层。 |
| `all_dst_offsets` | `list[list[int]]` | range put 在对象内的目标字节偏移。从 HBM 的 `all_buffer_ptrs[i][j]` 读出 `all_sizes[i][j]` 字节，写到对象的这个偏移处。 |
| `all_src_offsets` | `list[list[int]]` | range get 在对象内的源字节偏移。从对象的这个偏移处读出 `all_sizes[i][j]` 字节，写入 HBM 的 `all_buffer_ptrs[i][j]`。 |
| `config` | `ReplicateConfig` | 写入的副本与放置配置。整块写在 put 时传，逐层写在开始写会话时传一次。可省略以采用默认配置。 |
| `prefer_alloc_in_same_node` | `bool` | 整块 get 的可选参数，底层用于决定是否按目标节点组织批量传输。vLLM-Ascend 此处省略该参数，绑定默认值为 `False`。 |

**返回值按操作解释。** 对返回列表的接口，正常批量返回时 `result[i]` 对应 `keys[i]`，负值是该 key 的错误码。[社区接口文档](https://github.com/kvcache-ai/Mooncake/blob/b524db2c89c795a0bd1b4df78c307f03f2b853b1/docs/source/api-reference/python/mooncake-store.md#L3146-L3396)

| 接口 | 返回类型 | 成功时的含义 |
| --- | --- | --- |
| 整块 put，读写 session start，写 session end/revoke | `list[int]` | 每个 key 返回状态码 0。 |
| 整块 get，range put/get | `list[int]` | 每个 key 返回本次实际传输的字节数。range 调用可与该 key 本次请求的区间总长度 `sum(all_sizes[i])` 核对。 |
| 读 session end | `int` | 整批返回一个状态码，0 表示成功，负值表示失败。 |

## Decode DSA Offload 的 DDR Store

以下需求对应 vLLM-Ascend 开启 Sparse KV Offload 后的默认 `fused_copy_sfa` 路径。DDR 保存请求的稳定历史 KV。vLLM-Ascend 管理每层的 HBM Top‑K 热槽、请求内 token 位置到热槽的驻留映射，以及两个轮转尾块。[路径选择](https://github.com/vllm-project/vllm-ascend/blob/09317fc13a3daf2acb44e60dcb4b2ba877c24eca/vllm_ascend/ascend_config.py#L1844-L1849) · [HBM 空间分配](https://github.com/vllm-project/vllm-ascend/blob/09317fc13a3daf2acb44e60dcb4b2ba877c24eca/vllm_ascend/distributed/kv_transfer/sparse_kv_offload/sparse_kv_offload_manager.py#L114-L159)

### 1. 按层组织读写

同一 cache group 内，各层沿用请求块表中的同一个物理块号。每层分别持有 CKV、KPE 两个 DDR 基址。例如 GLM‑5.3 的 78 个主模型层共用块号 `b`，这个编号在各层分别选中 CKV 和 KPE 的第 `b` 块，合计 156 个数据区间。Attention 只召回当前层的数据，写回时可以批量提交多层的区间。[逐层分配](https://github.com/vllm-project/vllm-ascend/blob/09317fc13a3daf2acb44e60dcb4b2ba877c24eca/vllm_ascend/worker/v2/attn_utils.py#L1310-L1325) · [分层记录基址](https://github.com/vllm-project/vllm-ascend/blob/09317fc13a3daf2acb44e60dcb4b2ba877c24eca/vllm_ascend/distributed/kv_transfer/sparse_kv_offload/sparse_kv_offload_manager.py#L892-L928)

### 2. 按完整 block 写入 DDR

新 token 先写入当前层的 HBM 尾块。满足整块写回条件时，按请求块表确定 DDR 目标块号。以每块 128 个 token 为例，单层写出两段连续数据，分别是 128 行 CKV 和 128 行 KPE。各层写回完成后，请求的 `stable_prefix` 才前进一个 block。块表记录写到哪里，`stable_prefix` 记录已经可以从 DDR 读取的历史范围。[写回条件与目标块](https://github.com/vllm-project/vllm-ascend/blob/09317fc13a3daf2acb44e60dcb4b2ba877c24eca/vllm_ascend/distributed/kv_transfer/sparse_kv_offload/sparse_kv_offload_manager.py#L2042-L2080) · [传输长度](https://github.com/vllm-project/vllm-ascend/blob/09317fc13a3daf2acb44e60dcb4b2ba877c24eca/vllm_ascend/distributed/kv_transfer/sparse_kv_offload/sparse_kv_offload_manager.py#L1736-L1760) · [推进可读范围](https://github.com/vllm-project/vllm-ascend/blob/09317fc13a3daf2acb44e60dcb4b2ba877c24eca/vllm_ascend/distributed/kv_transfer/sparse_kv_offload/sparse_kv_offload_manager.py#L1816-L1836)

### 3. 按当前层的 token 行读取

召回以 token 在该请求序列中的位置为索引。稳态 Decode 时，Top‑K 命中 HBM 的行直接复用；对缺失的行，vLLM-Ascend 给出配对的源 token 位置和目标热槽。一批召回可以包含多个离散位置，每个位置只取当前层的一行 CKV 和一行 KPE。[缺失位置与目标槽](https://github.com/vllm-project/vllm-ascend/blob/09317fc13a3daf2acb44e60dcb4b2ba877c24eca/csrc/attention/fused_lightning_indexer_manage/README.md#L89-L96)

### 4. 在 NPU 上计算 DDR 地址

NPU 可直接访问当前层的分量基址和 HBM 中的请求块表。给定请求内 token 位置 `p` 和每块 token 数 `B`，只需一次块表索引，随后用相同的行号计算 CKV、KPE 两个地址。请求按 block 保存映射，逐 token 召回无需向 Host 查询对象 key。[设备侧块表](https://github.com/vllm-project/vllm-ascend/blob/09317fc13a3daf2acb44e60dcb4b2ba877c24eca/vllm_ascend/attention/sfa_kv_offload.py#L402-L407) · [算子寻址](https://github.com/vllm-project/vllm-ascend/blob/09317fc13a3daf2acb44e60dcb4b2ba877c24eca/csrc/attention/fused_scatter_copy_sparse_flash_attention/op_kernel/first_fill_scatter_copy_kernel.h#L142-L180)

```text
物理块号 = 请求块表[p // B]
物理行号 = 物理块号 × B + p % B
CKV 源地址 = CKV_base[layer] + 物理行号 × CKV 每行字节数
KPE 源地址 = KPE_base[layer] + 物理行号 × KPE 每行字节数
```

### 5. 单个 token 召回产生两个小读区间

GLM‑5.3 的 CKV 为 512 维，KPE 为 64 维。下表按一个 token 在一层的有效数据量计算。当前实现要求主 KV 使用 BF16；FP8 一行用于估算两个分量都按 1 字节存储时的读粒度，量化 scale 另计。表中的两段对应两个源地址区间，实际链路包数取决于传输实现。[GLM‑5.3 配置](https://huggingface.co/zai-org/GLM-5.3/raw/main/config.json) · [BF16 类型检查](https://github.com/vllm-project/vllm-ascend/blob/09317fc13a3daf2acb44e60dcb4b2ba877c24eca/vllm_ascend/distributed/kv_transfer/sparse_kv_offload/sparse_kv_offload_manager.py#L815-L828) · [两次分量读取](https://github.com/vllm-project/vllm-ascend/blob/09317fc13a3daf2acb44e60dcb4b2ba877c24eca/csrc/attention/fused_scatter_copy_sparse_flash_attention/op_kernel/first_fill_scatter_copy_kernel.h#L183-L193)

| 主 KV 精度 | CKV 读区间 | KPE 读区间 | 单层、单 token 合计 |
| --- | ---: | ---: | ---: |
| BF16（当前实现） | 1024 B | 128 B | 1152 B |
| FP8（估算） | 512 B | 64 B | 576 B |
