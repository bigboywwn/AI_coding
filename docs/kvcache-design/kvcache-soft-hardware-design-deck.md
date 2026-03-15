# KVCache 软硬件设计汇报文稿

## Deck Meta

- **Title**: KVCache 软硬件一体化设计
- **Audience**: 架构评审 / 基础设施 / 推理平台
- **Goal**: 用 10-12 页讲清楚 KVCache 在 coding-agent 场景下的需求、推导逻辑、硬件建议和软件架构
- **Duration**: 15-20 分钟

## Slide 1: 标题页

- **Title**: KVCache 软硬件一体化设计
- **Subtitle**: Coding-Agent 场景下的分层缓存、带宽约束与参考架构
- **Key message**: 我们不是在设计一个通用缓存，而是在设计一个服务推理效率的数据面系统

### Speaker Notes

先给听众一个总框架：这次设计不是“如何把 KV 存起来”，而是“如何把重复 prefill 变成可控的系统收益”。

## Slide 2: 问题定义

- KVCache 的目标不是单纯提高命中率
- 目标是在算力、内存、SSD、网络和时延约束下，实现系统推理效率最大化
- 命中率必须拆成：
  - 理论可复用率
  - 存储可命中率
  - 有效命中率

### Speaker Notes

强调有效命中率才是真正和 TTFT、吞吐、系统收益相关的指标。

## Slide 3: 场景与模型假设

- 业务场景：`coding-agent`
- 上下文档位：`25K / 50K / 100K / 150K / 200K`
- 默认参数：
  - `h_eff = 0.90`
  - `TTL_hot = 60s`
  - `TTL_cold = 15min`
- 模型：
  - `Kimi K2.5 = 39.1 KiB/token`
  - `MiniMax M2.5 = 124.0 KiB/token`

### Speaker Notes

这页讲清楚参数口径，不然后面的容量和带宽会没有锚点。

## Slide 4: 推导核心逻辑

- 读带宽下界：
  - `BW_read_hide = (h_eff / (1 - h_eff)) * R_eff * B_tok`
- 性能驱动容量：
  - `M_step = (1 - h_eff) * L_step`
  - `lambda_step = R_eff / M_step`
  - `Cap_hot = lambda_step * TTL_hot * L_hot * B_tok`
  - `Cap_cold = lambda_step * TTL_cold * L_cold * B_tok`

### Speaker Notes

强调两件事：更快的推理节点不仅推高带宽，也推高驻留容量。

## Slide 5: 硬件结论

- 推理节点自带 DDR 是热层主体
- 专用 DRAM 节点负责热点溢出和不均衡
- SSD 节点负责冷层、write-back 和 fallback
- 节点数量必须按：
  - `max(容量下限, 读带宽下限, 写带宽下限)`

### Speaker Notes

不要只按容量买机器，这是整套方案里最容易错的地方。

## Slide 6: 现实服务器形态

- 目标是主流 `2U 2P`
- SSD 节点不能按 `6-8 x NIC` 设计
- 更现实的口径是：
  - `4 x 400G NIC`
  - `16 x NVMe`
  - `512GB-1TB DDR`
- 推荐：
  - `SSD-48`
  - `SSD-64`

### Speaker Notes

这里把“理论 NIC 数”和“实际能插下的 NIC 数”区分开。

## Slide 7: 为什么软件会先撞到内存带宽

- 当前默认路径：
  - 网络走 `RDMA`
  - SSD 走 `SPDK`
  - 但仍经 `host pinned DDR`
- 端到端内存放大下界：
  - `remote DDR hit = 3x`
  - `SSD hit = 4x`
- 一次额外 host copy 后：
  - `remote DDR hit = 5x`
  - `SSD hit = 6x`

### Speaker Notes

这页要讲清楚：RDMA/SPDK 很重要，但还远远不够。

## Slide 8: 4 x 400G 对内存通道的压力

- `4 x 400G` 单方向 payload 约 `200 GB/s`
- 对应 host DDR 带宽需求：
  - 理想接收路径：`400 GB/s`
  - 一次额外 copy：`800 GB/s`
  - 两次额外 copy：`1.2 TB/s`
- 结论：
  - `16 channels total` 很紧
  - `24 channels total` 更合理

### Speaker Notes

强调软件路径和内存通道数是同一个设计问题，不是分开的。

## Slide 9: 为什么不能直接用 Ceph 或 Alluxio

- `Ceph` 适合：
  - 强持久化
  - 通用对象/块/文件
  - 超冷层
- `Alluxio` 适合：
  - tiered cache
  - 统一命名空间
- 但两者都不把下面这些作为第一约束：
  - pinned DDR
  - HBM 协同
  - copy budget
  - NUMA / memory channel pressure

### Speaker Notes

不是说它们不好，而是目标函数不一样。

## Slide 10: 参考架构

- 控制面：
  - `Metadata / Index`
  - `Tier Manager`
- 热层数据面：
  - `DRAM Page Server`
- 冷层数据面：
  - `Streaming SSD Page Server`
- 推理节点数据面：
  - `RDMA Recv Runtime`
  - `Layer Runtime`

### Speaker Notes

这一页先把模块讲清，再讲下一页的 IO 流。

## Slide 11: IO 流设计

- `remote DDR hit`
  - `metadata -> DRAM shard -> RDMA -> pinned DDR -> layer runtime -> HBM`
- `SSD hit`
  - `metadata -> SSD shard -> SPDK read -> RDMA -> pinned DDR -> layer runtime -> HBM`
- `miss / write-back`
  - `recompute -> local DDR/HBM -> admission -> promote/demote`

### Speaker Notes

强调 page-wise 和 layer-wise 必须解耦，接收路径不要顺手做 layer pack。

## Slide 12: 最终结论

- KVCache 是推理数据面系统，不是通用缓存系统
- 先盯住 `A_mem`，再谈 hit rate
- 硬件要按容量和带宽双约束 sizing
- 软件要围绕：
  - 固定 page 布局
  - pinned buffer
  - NUMA-local queue
  - streaming page server
  - copy budget aware scheduling

### Speaker Notes

收口时突出一句话：如果不把 copy 次数当成一等约束，4 x 400G 的 NIC 和大容量 DDR/SSD 也无法转化成有效推理收益。
