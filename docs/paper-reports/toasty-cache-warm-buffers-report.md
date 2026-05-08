# Toasty: Speeding Up Network I/O with Cache-Warm Buffers 论文总结报告

论文：Preeti, Nitish Bhat, Ashwin Kumar, Mythili Vutukuru. ASPLOS 2026.  
官方来源：https://doi.org/10.1145/3779212.3790235  
本地 PDF：`/Users/mlx/Documents/work/downloads/asplos2026-storage/papers/04_toasty.pdf`  
本地抽取文本：`/Users/mlx/Documents/work/downloads/asplos2026-storage/text/04_toasty.txt`

## 一句话总结

Toasty 解决的是 AF_XDP/DDIO 网络 I/O 中“大 buffer pool 保突发但破坏 LLC locality、小 buffer pool 性能好但容易丢包”的两难。它不用改 NIC 硬件，而是在 userspace 把 packet buffer pool 改成 LIFO，并在 kernel driver 里自适应控制 RX ring 实际填充的 buffer 数量，使稳态流量复用 cache-warm buffers，突发流量再临时拉入更多 buffer。

## 问题背景

现代 NIC 通过 DDIO/DCA 可以把 DMA packet 直接写进 LLC，避免应用每个包都从 DRAM 取数据。但 DDIO 只使用有限 LLC ways，网络 packet buffer working set 一旦超过 LLC 可容纳范围，就会出现两个问题：

- Leaky DMA：新到 packet 把尚未被应用处理的旧 packet 从 LLC 挤掉，应用处理时又要从 DRAM 取回。
- Unnecessary writebacks：应用处理完并回收到 free pool 的 buffer 仍然是 dirty cacheline，如果在 NIC 复用前被逐出，就会写回 DRAM，而这些内容未来会被新 DMA 覆盖，这次写回是纯浪费。

直觉方案是把 packet buffer pool 缩小到 LLC/DDIO ways 能容纳的规模。但这会牺牲突发流量韧性：burst 到来时 NIC 找不到可 DMA 的 free buffer，出现 packet drop。传统默认配置通常选择大 buffer pool 和满 RX ring，保证不丢包但性能不佳；理想小配置在稳态快，但遇到 microburst/Poisson burst 会丢包。

## 核心设计

Toasty 有两个互补组件。

### 1. Userspace LIFO Buffer Pool

默认 AF_XDP 的 Fill Queue 是 FIFO：应用把处理完的 buffer 放到 producer 端，driver 从 consumer 端取 buffer 填 RX ring。刚被处理过的 cache-warm buffer 要等队列绕一圈才会被复用，往往已经从 cache 中被逐出。

Toasty 的 userspace 改动是把新回收的 buffer 指针和 consumer 端附近的指针做 atomic swap，本质上把最近回收的 warm buffer 提前到队头。注意它只交换 buffer pointer，不移动 buffer 内容，因此成本较低。论文测得 100 万次 swap 用 4.9ms；以 NAT 处理 100 万个 512B packet 的 72ms 为基准，swap 开销约 6.8%，可被 cache locality 收益抵消。

这个机制依赖 AF_XDP busy poll 模式下 producer/consumer 不并发执行，从而避免 race。论文也指出 interrupt 模式下需要额外同步，例如 compare-and-swap 检查队头是否被并发消费。

### 2. Kernel Driver Adaptive RX Refill

仅有 LIFO pool 不够，因为硬件 RX ring 仍然是 FIFO。如果 driver 总是把 RX ring 填满，那么 warm buffer 仍要排在大量 cold buffer 后面，NIC 很久之后才会复用。

Toasty 修改 AF_XDP driver 的 refill 策略：RX ring 物理容量仍配置得较大，但每轮只填“当前流量所需”的 buffer 数量。关键变量包括：

- `N_FQ`：上一轮应用回收到 Fill Queue 的 buffer 数。
- `N_RXQ`：当前轮 NIC 已 DMA 并送到应用 RXQ 的 packet 数。
- `N_avail`：RX ring 中当前可供 DMA 的 free buffer 数。
- `k`：安全余量倍数，论文实现取 `k = 10`。

算法目标是保持 `N_avail` 大约不低于 `k * N_RXQ`。当链路利用率低于 50% 时，系统认为短期丢包风险小，只补最近回收的 warm buffer，甚至在 buffer 过多时不补，让 ring 慢慢 drain 回小 working set。当链路利用率较高时，则更积极地填充，允许拉入 cold buffer 应对 burst。

这个策略的关键不是动态 resize RX ring，而是动态改变“已填充 descriptor 数量”。resize ring 需要重启设备/应用，不适合毫秒级响应。

## 评估结果

实验基于 Ubuntu 22.04.5、Linux 6.10.9、AF_XDP zero-copy busy poll，使用多种网络函数：NAT、IDS、Decrypt、L2Fwd、MICA、Maglev。

主要结果：

- 单核吞吐：Toasty 相比默认 AF_XDP 最高提升 78%，并基本接近手工调优的小 buffer “ideal” 配置。
- Tail latency：在 L2Fwd 上，Toasty 相比默认配置 99 分位延迟提升 36.2%，99.99 分位提升 2.6 倍。
- Cache 行为：Toasty 使应用接近零 LLC miss，IPC 相比默认配置更高。
- 突发流量：在 microburst 和 Poisson 流量下，Toasty 的丢包率接近大 buffer 默认配置，显著好于 ideal 小 buffer 配置。
- Co-located memory pressure：使用 Intel MLC 制造内存压力时，Toasty 相比默认 AF_XDP 提升 30%-86%。
- 多核/包长扩展：多核复制应用中，Toasty 随 core 数近线性扩展，直到 100Gbps 链路饱和。
- 对比相关工作：Toasty 优于 user-only LIFO、DPDK LIFO mempool、ShRing 和 software prefetching。软件 prefetch 能改善部分吞吐，但会显著增加内存带宽消耗，例如 Maglev 和 NAT 场景可高出 25x-35x。

## 为什么这篇有意思

这篇论文的价值不在于提出复杂算法，而在于抓住了一个非常工程化的跨层事实：packet buffer 是否 cache-warm，取决于 userspace free pool、kernel driver refill、硬件 RX ring、DDIO ways 共同形成的循环路径。只改其中一层效果有限，必须让“最近释放的 buffer”真的尽快进入 NIC DMA 路径。

它的设计点很轻：

- 不要求新 NIC、SmartNIC 或修改 DDIO。
- 不改应用语义，只改 AF_XDP library 和 driver。
- 保留大 buffer pool 和大 RX ring 的抗突发能力。
- 用简单 runtime 指标近似负载变化，而不是读 NIC drop register。

## 局限与风险

- 主要面向 AF_XDP busy poll + zero-copy；interrupt 模式需要额外同步。
- 依赖 DDIO/DCA 这类 NIC-to-LLC 行为，收益会随平台 cache/NIC 行为变化。
- 当前策略中的 `k = 10` 和 50% link utilization threshold 是经验值，虽然论文做了敏感性分析，但生产部署仍需按 workload 校准。
- 对 compute-heavy 网络函数提升较小，因为瓶颈不在 I/O buffer cache locality。
- 修改 kernel driver，工程上比纯 userspace library 更难进入标准发行版。

## 对 MoonCake / 高性能数据路径的启发

如果我们在 MoonCake、KVCache 传输或 SSD/NIC 数据路径中遇到“buffer 生命周期长、DMA/网络设备重复访问同一批内存”的场景，Toasty 提供了一个很好的思路：

- 不只看 buffer pool 大小，还要看 buffer reuse order。
- “最近释放”的 buffer 往往最有 cache/TLB/locality 价值，应优先复用。
- 大池子保弹性，小 working set 保稳态性能，两者可以通过动态填充而不是静态配置兼得。
- 如果路径中有 NIC/DPU/GPU DMA，应该显式分析 descriptor queue 的 FIFO/LIFO 语义，否则 userspace 的 locality 优化可能被硬件 ring 抹掉。

## 阅读建议

优先读第 2 节和第 3 节，弄清楚 leaky DMA、unnecessary writebacks、FQ/RX ring 的生命周期。第 4.5 和 4.6 很适合看 ablation：它证明 user-only LIFO 或 kernel-only adaptive refill 单独都不够，完整收益来自二者闭环。
