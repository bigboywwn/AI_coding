# Libra: Flexible Request Partitioning and Scheduling for Serving Unbalanced and Dynamic LLM Workloads 论文总结报告

论文：Chaoyi Ruan, Yinhe Chen, Dongqi Tian, Yandong Shi, Yongji Wu, Jialin Li, Cheng Li. NSDI 2026.  
官方来源：https://www.usenix.org/conference/nsdi26/presentation/ruan-libra  
本地 PDF：`/Users/mlx/Documents/work/downloads/nsdi2026-storage/papers/07_libra.pdf`  
本地抽取文本：`/Users/mlx/Documents/work/downloads/nsdi2026-storage/text/07_libra.txt`

## 一句话总结

Libra 解决的是在线 LLM serving 中 prefill 与 decode 负载动态失衡的问题。它把传统“prefill/decode 固定共置或固定解耦”扩展成 Flexible Partition and Scheduling：每个请求可以在任意 token 位置切成 micro-requests，交给统一 GPU pool 动态调度，并用 SLO-aware batching 与 chunk-based KV transfer 同时追求高 goodput 和低 TBT tail latency。

## 问题背景

LLM inference 分为两个阶段：

- Prefill：并行处理 prompt token，计算初始 KV cache，compute-intensive。
- Decode：逐 token 生成输出，依赖历史 KV cache，memory-bound，TBT 对用户体验敏感。

现有 serving 架构有两个典型方向：

- PD colocation：prefill 和 decode 在同一 GPU instance 上执行，可共享权重/KV，吞吐潜力高，但 prefill chunk 会阻塞 decode，导致 TBT tail latency 失控。
- PD disaggregation：prefill 和 decode 分到不同 GPU instance，隔离干扰，SLO 更稳定，但阶段资源固定，遇到 prefill-heavy 或 decode-heavy 时一边忙、一边闲。

现实 workload 是动态且不平衡的。Azure Code、BurstGPT 等 trace 中，prompt length 和 output length 会随时间剧烈变化。固定的 P:D GPU 配比或固定 chunk size 在一种流量形态下可能合适，流量一变就会低效。

论文用 Qwen-2.5-14B 两 GPU microbenchmark 说明：

- PD Disaggregation 在 prefill-heavy、decode-heavy、balanced 三种形态下都能满足 100ms TBT SLO，但 GPU 利用率严重不平衡。
- PD Colocation 吞吐看起来更高，但 P99-TBT 可到 300ms 以上，SLO attainment 甚至低至 1.73%，在生产中不可用。

## 核心抽象：FPS 与 Micro-request

Libra 的核心是 Flexible Partition and Scheduling, FPS。一个请求可表示为 prompt length `P`、预测 decode length `D`、总逻辑长度 `L = P + D`。Libra 选择 split point `s`，把请求切成两个 micro-request：

- `r_alpha`：token 1 到 s。
- `r_beta`：token s+1 到 L。

当 `s = 0` 或 `s = L` 时，相当于不切分，接近 colocation。  
当 `s = P` 时，相当于传统 PD disaggregation。  
当 `s` 落在 prompt 或 decode 内部，就能形成更细粒度的混合切分。

这让 colocation 和 disaggregation 变成 Libra 搜索空间里的两个特殊点，而不是固定架构选择。系统可以按每个请求和当前负载动态选择切法。

## 系统设计

Libra 采用两级调度。

### 1. Global Scheduler: 请求切分与路由

Global scheduler 接收每个请求，决定 split ratio `phi`，并把两个 micro-request 路由到当前负载最低的 GPU instances。

论文的关键洞察是：disaggregated pipeline 的吞吐由慢的一侧决定，因此应平衡两个 micro-request 在目标 GPU 上的执行时间。它使用 bounded binary search 寻找 `phi`，使预测执行时间 `T1` 和 `T2` 接近。

实现上：

- 初始 `phi = P / (P + D)`，即传统 PD split。
- 最多搜索 K 次，论文取 K=6。
- 使用轻量 analytical predictor 和 offline-profiled lookup table 估计 batch/latency。
- 调度开销是微秒级 probe，整体 per-request overhead 低于端到端延迟的 0.51%。

Libra 不强依赖精确输出长度预测。论文加了 20-token safety margin，并做敏感性分析：当真实输出长度围绕 1467 token、标准差到 100 时，goodput 仅下降 2.9%。

### 2. Local Scheduler: SLO-aware Batch Composition

每个 GPU instance 有 local scheduler，负责把收到的 micro-request 组成 batch。它不是使用固定 chunk size，而是根据 runtime profile 动态决定一个 batch 能放多少 prefill token。

Local scheduler 记录上一批的 `(prefill length, context length, decode request number, latency)`，并查 profile table 来计算在目标 TBT SLO 下当前 decode batch 还能容纳多少 prefill token。策略是：

- decode token 是 latency-critical，先全部放入 batch。
- 根据 decode count 和 context length 计算 prefill token budget。
- 按 arrival order 贪心加入 prefill token，直到 budget 用尽。

这个机制对应论文的两个洞察：

- Decode-only 满足延迟但 GPU compute 利用率低；适量 prefill 可提升利用率，但太多会伤 TBT。
- 最优 batch composition 受 prefill length、decode context length、decode token number 共同影响，必须动态调整。

### 3. Chunk-based KV Transfer

Micro-request 切分导致不同 GPU instance 之间需要传 KV cache。Libra 用 chunk 粒度传输：

- Server1 执行 `r_alpha` 时，完成一个 chunk 就立即把对应 KV block 通过 RDMA/NCCL/Mooncake 推给 Server2。
- Server1 继续计算下一个 chunk，Server2 同步接收。
- KV cache 是 append-only，完成 chunk 后不可变，因此可以安全重叠 compute 与 transfer。

论文报告 chunk-based KV transfer 可减少 94% 的 non-overlapped transfer。

### 4. Multi-split 支持

FPS 不限于二分。对 Chain-of-Thought workload，Libra 可以把请求切成 prefill、think、decode 三段。Think token 不直接面向用户，SLO 可放宽；调度器可以更激进地平衡负载。Mini-Reasoning 上，三段切分比二段切分 goodput 再提升 12%，总计比 PD Disagg. 高 41%。

## 实现与评估

实现：

- 基于 vLLM，约 4000 行 Python。
- 模型：Qwen-2.5 14B、32B、72B。
- 主平台：两台 cloud server，每台 4 张 A100 80GB、128 CPU、1TB RAM、4×200Gbps ConnectX-6 RoCE NIC；另有 H100 实验。
- Workload：BurstGPT、Azure Code、arXiv Summarization、Mini Reasoning。
- 指标：Goodput，即满足 latency SLO 的 output tokens/s；Serving capacity，即 P99 TBT 满足 100ms SLO 下最大 QPS。

对比：

- PD Colocation：vLLM chunked prefill，chunk size 在 256-2048 中调优。
- PD Disaggregation：vLLM disaggregation 模式扩展版，类似 DistServe 设计。

主要结果：

- Goodput：Libra 相比 PD Coloc. 最高提升 91%，相比 PD Disagg. 最高提升 61%。
- Serving capacity：Qwen-2.5-14B 上，Libra 平均为 PD Coloc. 的 2.37 倍，为 PD Disagg. 的 1.37 倍。
- Hybrid workload：50% BurstGPT + 50% Azure Code，Libra serving capacity 为 7.4 rps，高于 PD Coloc. 的 4.6 和 PD Disagg. 的 5.9；goodput 分别高 49% 和 20%。
- SLO-aware batching：不启用时只有 52% tokens 满足 100ms TBT；启用后 SLO attainment 到 99%。
- Asymmetric TP baseline：即使与更强的 4P1D、1P4D、2P1D、1P2D 等非对称配置比，Libra per-GPU goodput 仍提升 18.6%-74.2%。
- H100 + 50ms SLO：Azure workload 上，Libra 相比 PD Disagg. 高 53.1%，相比 PD Coloc. 高 134%；Mini Reasoning 上分别高 55.4% 和 4%。

## 为什么这篇有意思

Libra 的贡献是把 LLM serving 的资源分配粒度从“GPU role”降到“request token span”。它不把 prefill/decode 视为固定部署拓扑，而是按每个请求和实时负载做切分。

这非常适合在线服务的真实情况：

- 流量混合：代码、聊天、总结、reasoning 的 prompt/output 分布完全不同。
- 负载动态：同一个服务不同时间 prefill-heavy 和 decode-heavy 交替出现。
- GPU 昂贵：静态分配导致一侧闲置就是成本浪费。
- SLO 严格：colocation 的高吞吐如果不满足 TBT，也不能算有效吞吐。

Libra 用 goodput 而不是 raw throughput 作为目标，这一点很重要：它只计算满足 SLO 的 tokens。

## 局限与风险

- 依赖 runtime profiling table；模型、GPU、kernel、parallelism 策略变更后需要重新 profile。
- 需要输出长度预测，虽然论文说明不敏感，但极端 underestimation 仍可能影响调度质量。
- Cross-instance KV transfer 更频繁，对网络/NVLink/RDMA 质量敏感。论文认为 transfer latency 通常比 compute 小 1-2 个数量级，但这在不同模型和部署拓扑下需复核。
- 基于 vLLM 实现，迁移到其他 inference engine 要重新适配 scheduler、batching 和 KV transfer。
- 二分/三分 micro-request 会增加调度和状态管理复杂度，生产系统调试难度高于固定 PD。

## 对 MoonCake / KVCache 系统的启发

Libra 明确提到可用 RDMA-based libraries 如 NCCL 或 Mooncake 做 KV transfer。这对 MoonCake 很有参考价值：

- KV cache transfer 不只是搬数据，而是调度策略的一部分；调度器决定 split point 后，传输层必须支持 chunk-granular、低延迟、可重叠传输。
- MoonCake 如果作为 KV cache fabric，应提供对上层 scheduler 友好的接口，例如按 token chunk/prefix block 发起异步 transfer，并暴露 completion/placement 状态。
- 对 PD disaggregation 系统，固定 prefill/decode GPU role 可能不是最优；统一 GPU pool + 动态 split 会增加 KV transfer 量，但可能提高整体 goodput。
- 对 long-context/CoT 场景，非用户可见 token 阶段可用更宽松 SLO 调度，这是一个值得系统层显式支持的优化机会。

## 阅读建议

重点读第 2.3/2.4 节理解为什么静态 PD 配置会失败；第 3/4 节理解 FPS 抽象和两级调度；第 6.5/6.6/6.7 是最有信息量的 ablation 和强 baseline 对比。若关注 MoonCake 方向，应特别看第 4.3 的 chunk-based KV transfer 和第 6.7 的 multi-split。
