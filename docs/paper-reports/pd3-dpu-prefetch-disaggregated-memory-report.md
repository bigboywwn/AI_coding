# PD3: Prefetching Data with DPUs for Disaggregated Memory 论文总结报告

论文：Sidharth Sankhe, Felix Zhang, Umayrah Chonee, Sherman Lim, Jiasheng Hu, Jialin Li, Qizhen Zhang. NSDI 2026.  
官方来源：https://www.usenix.org/conference/nsdi26/presentation/sankhe  
本地 PDF：`/Users/mlx/Documents/work/downloads/nsdi2026-storage/papers/05_pd3.pdf`  
本地抽取文本：`/Users/mlx/Documents/work/downloads/nsdi2026-storage/text/05_pd3.txt`

## 一句话总结

PD3 的核心思想是把 disaggregated memory 的 cache miss 从“host 执行时发现并补救”变成“请求到达 DPU 时提前确定并预取”。它让 DPU 解析请求、维护 host cache 的近似视图、直接从远端内存 RDMA 取数据，再 DMA 到 host 的 Loading Zone，使应用在进入慢速 out-of-core 路径前就能像本地命中一样取到数据。

## 问题背景

内存解耦后，compute node 用本地内存做 cache，working set 大部分在 remote memory。理想情况下，本地 cache 命中时性能接近 monolithic；但 cache miss 会引入上下文切换、网络通信、RDMA polling、序列化和线程安全等额外路径。论文用一个 disaggregated hash map 说明：本地 cache 固定 1GB 时，随着 hash map/workload 变大，吞吐可从 5900 万 ops/s 降到 200 万 ops/s，p99 延迟最高增加 5 倍。

已有三类办法都有缺陷：

- Overlap compute and communication：可提升吞吐，但不减少 time-to-response，收益依赖 workload。
- Near-data/offload computation：适合 compute-light 操作，但多数逻辑仍在 compute node 执行，miss 仍会发生。
- 更好的 caching/prefetching：LRU、metadata pinning、Leap 这类模式预测仍会遇到 cold start、irregular access、false positive cache pollution。

PD3 要解决的是：能不能在 request 执行前就确定 cache miss，并把缺失数据提前放到 host 可快速访问的位置。

## 系统要求

论文总结了一个理想 disaggregated memory cache/prefetch 系统需要满足五点：

1. 早期访问预测：给远端读取留下时间窗口。
2. 高预测准确率：短期会访问的数据应被准备好。
3. 低 false positive：避免无用数据污染本地 cache。
4. 快速准备：在请求执行前完成缺失数据准备。
5. 最小应用修改：应用能用轻量接口消费 prefetched data。

PD3 的关键取舍是牺牲一部分通用性，换取“确定性 prefetch”：它要求能从网络请求中解析出 key/object/page id 等访问标识。

## 核心架构

PD3 运行在 compute server 的 DPU 上，主要组件包括 Request Parser、Host View、Transfer Engine 和 Loading Zone。

### 1. Request Parser: 请求到达即解析

DPU NIC 在不改变原始应用路径的情况下 mirror 目标应用 packet，把 copy 交给 DPU SoC 上的 parser。Parser 是用户定义的：

`Parse(PktBuf, PktLen) -> List<Key, Op>`

它把协议负载解析成按顺序排列的 key 和操作类型，如 Read、Write、Delete。论文实现支持自定义格式、RESP/Garnet 等。这里的重点是 packet mirroring 发生在 NIC 硬件，原始 packet 继续转发给 host，不因 DPU 解析而增加 host 收包延迟。

### 2. Host View: DPU 上的 host cache 视图

Host View 是 DPU 上维护的 set-membership/hash table，用于判断某个 key 是否已在 host cache 中。它存的是“host 已缓存 key”，而不是 remote memory 的全量 key，因为 DPU 内存有限。

Host View 的性能挑战很大：现代数据系统可能每秒处理千万级请求，DPU core 又弱于 host CPU。论文基于 bucketized cuckoo hash table 做了多项优化：

- 利用 client-side batching 做 multi-key lookup。
- 使用 huge page 降低 TLB miss。
- 用 SIMD compare/movemask 搜 bucket。
- 延迟计算第二个 cuckoo bucket，只在第一个 bucket miss 时才查。
- 按 shard 扩展到多个 DPU core。

结果是 1 亿个 8-byte key、80% load 下，从普通 hash set 的几百万 ops/s 提升到约 7000 万 ops/s。

Host View 的维护规则也很关键：

- client write 会把 key 加到 Host View。
- remote memory read response 会把 key 加到 Host View。
- client delete 或 flush/writeback remote memory 会把 key 从 Host View 删除。
- host 静默生成或静默丢弃 clean data 不完全同步；这可能带来 false negative，但 false negative 只会让 host 走正常 miss 路径，不破坏正确性。

### 3. Transfer Engine: DPU 直接走远端内存最短路径

一旦 Prefetcher 发现某个 request 要访问的 key 不在 Host View 中，DPU 直接通过 RDMA 从 remote memory 读数据。这样避免了“DPU -> host -> DPU -> remote memory”的绕路。

Transfer Engine 同时统一 DMA 和 RDMA：

- host-DPU 之间用 DPU-issued DMA。
- DPU-remote memory 之间用 DPU-issued RDMA。
- DPU 内部使用 unified buffers，避免 DMA buffer 和 RDMA buffer 之间额外 copy。
- 请求和响应都用 ring buffer 批量化，尽量不牺牲延迟。

论文报告 Transfer Engine 相比 host-issued RDMA 在 16 个 host CPU core 场景下吞吐高 1.5 倍，并且 host CPU 消耗为 0。DPU-direct prefetch 路径相比先转发到 host 再访问 remote memory 最多快 24%，同时节省 host CPU。

### 4. Loading Zone: host 上的轻量消费缓冲区

Prefetched item 被 DMA 到 host 内存中 PD3 预留的 Loading Zone。应用在进入原有 out-of-core path 前调用：

`CheckAndReturn(Key, DestBuf) -> Size`

如果 item 已经被 DPU 准备好，则复制到 `DestBuf` 并返回大小；否则返回 0，应用继续走原本 remote memory miss 路径。这个接口非阻塞，适合高性能 pipeline。

Loading Zone 用 ring buffer 组织，但普通多消费者 ring 会有 head contention 和 same-key contention。PD3 的优化是每个 consumer 复制一个 LocalHead，从 Head 扫到 Tail；数据项 header 带 Key、Size、State，命中后用 CAS 把 State 从 PRODUCED 改成 CONSUMED。DPU 在后台 lazy clean。这样消除了全局 Head 更新竞争，仅保留命中项上的 CAS。

论文测得 Loading Zone 在 16 个线程并发调用 `CheckAndReturn` 时可达到约 1.5 亿 invocations/s，比 locking baseline 快 224 倍，比 lock-free baseline 快 35 倍。

## 评估结果

硬件平台：

- DPU：NVIDIA BlueField-3，200Gbps NIC，8 个 ARMv8 A78 core，32GB DDR4。
- Host：AMD EPYC 9254，24 cores，128GB DDR5。
- 网络：compute、client、memory server 通过 200Gbps ConnectX 连接。
- 原型：约 15000 行 C++，DPU/host/remote memory 三侧代码。

应用：

- Open-address hash map，YCSB 1B keys，95% read / 5% write。
- Database page server，随机页读，10M pages，每页 4KB。
- Microsoft Garnet KV cache，RESP benchmark，425M keys。

对比：

- Host-issued synchronous RDMA。
- Redy：异步、批量、pipeline 的 remote memory API。
- Leap：基于 Boyer-Moore 趋势检测的 prediction prefetcher。

主要结果：

- Hash map uniform workload：PD3 相比 RDMA 吞吐高 26 倍，相比 Redy 高 2.2 倍。
- Page server：PD3 相比 RDMA 高 65%，相比 Redy 高 33%。
- Garnet：PD3 相比 synchronous RDMA/Leap 高 6 倍，相比 Redy 高 8.5 倍；原因是 Garnet RESP 协议限制每线程一次只能 active 一个请求，Redy 的异步批量反而不适配。
- 延迟：PD3 在各应用上 median latency 降低 1.5x-11x，tail latency 降低 1.8x-10x。
- Prefetch 贡献：关闭 prefetch 后，PD3 不再优于现有方案，应用吞吐最高比完整 PD3 低 12.7 倍，说明主要收益来自 DPU-enabled prefetch，而不是单纯 RDMA offload。
- 与本地内存差距：PD3 能把 disaggregated memory 和 local memory 的性能差距压到 10% 以内。
- Host CPU 节省：PD3 在 compute host 不占 CPU core，空出的 core 可继续给应用，16 application threads 下 hash map/page server/Garnet 相比 8 threads 分别再提升 30%/54%/35%。
- 本地内存需求：以 Garnet 为例，只需 128MB compute-local cache，即低于数据库大小的 1%，PD3 就能达到 local memory 性能；传统方案只有全量 cache 后才能做到。

## 为什么这篇有意思

PD3 的关键创新不是“DPU 做 RDMA offload”，而是把 DPU 放在网络路径上的信息优势用起来：DPU 比 host 更早看到请求，并且离 remote memory 的网络路径更短。它把 prefetch 从统计预测变成 request semantic-driven deterministic prefetch。

它把 disaggregated memory 的慢路径拆成三段：

- 什么时候知道要访问什么：网络请求到达时。
- 谁去取：DPU，不占 host CPU。
- 放到哪里：Loading Zone，不强耦合应用 buffer manager。

这个分层让 PD3 既能快，又保持应用改动相对小。

## 局限与风险

- 需要能从 packet/request 中解析出访问 key/object/page，复杂 SQL 查询或访问集合动态生成的 workload 不一定适用。
- Host View 不是强一致 cache directory，允许 false negative；这对性能可接受，但系统设计要确保不会破坏正确性。
- DPU 内存和 core 资源有限，Host View 规模、parser 复杂度、并发应用数都会影响可部署性。
- 对强加密、压缩、应用层协议多变、请求语义不可见的服务，DPU 解析成本和可行性是问题。
- Prefetched item 可能在 Loading Zone 中被后续 prefetch 覆盖；论文显示低于 64MB Loading Zone 时性能明显下降，说明仍存在空间/性能 trade-off。

## 对 MoonCake / KVCache / 存储解耦的启发

PD3 对 MoonCake 这类分布式 KVCache/远端内存系统有几个直接启发：

- 如果请求语义能在网络入口解析，DPU/NIC 侧可以提前发起 KV/page/chunk 拉取，而不是等 GPU/CPU 执行到 miss。
- Host-side cache directory 不一定要强一致；性能路径可以允许 false negative，避免 false positive 污染更重要。
- “Loading Zone” 是一种很实用的解耦接口：不要求重写上层 cache manager，只在慢路径前插一个 opportunistic check。
- DPU 的价值不只是 offload CPU，而是改变时序：更早知道、更早拉取、更短路径。
- 对 LLM KVCache，如果 prefix/chunk id 能从调度层请求中提前知道，可以考虑类似 PD3 的 deterministic prefetch，而不是只靠 LRU/热度预测。

## 阅读建议

重点读第 4-7 节：架构、Host View、Transfer Engine、Loading Zone 是完整闭环。第 8.3 很关键，它证明收益主要来自 prefetch 而不是 RDMA offload；第 8.5 对理解 disaggregated memory 的本地 cache 最小需求尤其有价值。
