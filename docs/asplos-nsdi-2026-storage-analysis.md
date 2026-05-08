# ASPLOS 2026 与 NSDI 2026 Storage Session 论文下载与分析

日期：2026-05-07  
范围：ASPLOS 2026 官方 `Storage & Caching` session；NSDI 2026 官方含 `Storage` 标题的 session，并补充若干强存储相关 session。

## 下载状态

本次本地下载目录：

- ASPLOS：`/Users/mlx/Documents/work/downloads/asplos2026-storage/papers`
- NSDI：`/Users/mlx/Documents/work/downloads/nsdi2026-storage/papers`
- PDF 抽取文本：`/Users/mlx/Documents/work/downloads/asplos2026-storage/text`、`/Users/mlx/Documents/work/downloads/nsdi2026-storage/text`

下载结果：

- ASPLOS：官方 `Storage & Caching` session 共 5 篇；已下载并抽取 4 篇 PDF。`Hitchhike` DOI 已确认，但 ACM 下载页被 Cloudflare challenge 拦截，未能可靠取得 PDF 正文。
- NSDI：下载并抽取 15 篇 USENIX 官方 PDF，其中 9 篇来自官方含 `Storage` 标题的两个 session，6 篇来自相邻但强存储相关 session。

主要官方来源：

- ASPLOS 2026 program: https://www.asplos-conference.org/asplos2026/program/index.html
- NSDI 2026 technical sessions: https://www.usenix.org/conference/nsdi26/technical-sessions
- NSDI 2026 单篇论文页与 PDF 均来自 `usenix.org/conference/nsdi26/presentation/...` 和 `usenix.org/system/files/nsdi26-*.pdf`

## ASPLOS 2026: Storage & Caching

ASPLOS 的这个 session 更偏“局部机制与硬件/系统交界处优化”：flash cache、指令 cache、cache 分析工具、NIC/LLC cache 交互，以及一篇请求提交路径优化。

| 论文 | 本地 PDF | 主题 | 核心判断 |
| --- | --- | --- | --- |
| Nemo: A Low-Write-Amplification Cache for Tiny Objects on Log-Structured Flash Devices | `01_nemo.pdf` | flash KV cache / tiny objects / 写放大 | 这篇最贴近传统 storage。核心是把 tiny-object flash cache 的应用层写放大从 set-associative mapping 的低填充率问题里拆出来，通过小 hash space 的 set-group、Bloom filter 索引和混合热度跟踪，让 log-structured SSD 更接近顺序批量写。 |
| ICARUS: Criticality and Reuse based Instruction Caching for Datacenter Applications | `02_icarus.pdf` | L2 instruction cache replacement | 面向 datacenter 大代码足迹的前端瓶颈。它不是 storage cache，而是架构 cache 策略，使用 branch history 作为上下文识别 critical instruction line，并把 criticality 和 reuse 结合。平均相对 TPLRU 提升 5.6%，最高 51%。 |
| CacheMind: From Miss Rates to Why | `03_cachemind.pdf` | cache trace reasoning / RAG tool | 重点不是提出新替换策略，而是把 cache trace 分析从“看 miss rate”推进到“解释为什么”。适合作为架构/系统工程师的诊断工具原型，但对线上 cache 系统的直接落地还需要工具链集成。 |
| Toasty: Speeding up network I/O with cache-warm buffers | `04_toasty.pdf` | NIC DMA / LLC / AF_XDP | 软件化处理 DDIO 下 packet buffer cache warmth。用 LIFO buffer pool 和自适应 RX ring 填充，在稳态复用 cache-warm buffer，突发时退回大 buffer pool。对 AF_XDP 默认实现最高提升 78%。 |
| Hitchhike: Efficient Request Submission via Deferred Enforcement of Address Contiguity | 未取到 PDF；DOI: `10.1145/3779212.3790173` | 请求提交 / 地址连续性约束 | 仅确认官方标题和 DOI，未分析正文。标题指向 I/O request submission 路径中的地址连续性约束延迟检查，可能属于 storage I/O stack/硬件请求接口方向。 |

ASPLOS 小结：

- 这里的 “Storage & Caching” 不是纯存储系统 session，而是 cache 作为共同抽象：flash cache、CPU instruction cache、LLC/NIC cache、cache trace reasoning。
- 最值得存储方向优先读的是 `Nemo`；如果关注高性能 I/O 路径，`Toasty` 也很有参考价值。
- `CacheMind` 代表一个新趋势：LLM/RAG 不直接替代系统设计，但可以进入 trace/root-cause 分析闭环。

## NSDI 2026: 官方 Storage 标题 Session

NSDI 的 storage 论文明显更系统化、生产化，关键词是 disaggregation、tail latency、AI/LLM workload、DPU/RDMA、升级正确性和云存储运维。

### Storage Systems and Architecture

| 论文 | 本地 PDF | 主题 | 核心判断 |
| --- | --- | --- | --- |
| FalconFS: Distributed File System for Large-Scale Deep Learning Pipeline | `01_falconfs.pdf` | 分布式文件系统 / DL pipeline | 针对 AI pipeline 中 client-side metadata cache 反而浪费内存、效果差的问题，改成 stateless client，把 path resolution 和 metadata indexing 放到 server 侧。对 CephFS/Lustre，小文件读写最高 5.72x，训练最高 12.81x，且有 10000 NPU 生产部署经验。 |
| DistVS: Large-scale Vector Search with Compute-Memory Disaggregation | `02_distvs.pdf` | 向量检索 / 分层存储 / disaggregation | 把 ANNS 向量数据按低精度、高精度、全精度拆到 compute、memory server、SSD 三层，以逐级剪枝减少昂贵 I/O。对 RAG/推荐系统这类向量密集型存储很有启发。 |
| Lemonshark: Asynchronous DAG-BFT With Early Finality | `03_lemonshark.pdf` | BFT consensus | 被安排在 storage architecture session，但本质更偏共识协议。和存储系统的关联在于复制状态机/分布式数据库的共识层。 |
| CacheCatalyst: Enhancing Web Caching for the Latency-Constrained Internet | `04_cachecatalyst.pdf` | Web cache / validation latency | 指出高速网络下 revalidation RTT 成为瓶颈，提前进行 cache validation，并优化 Server Push 形态，平均提升关键 Web 性能指标约 40%。 |

### Scalable Storage Systems

| 论文 | 本地 PDF | 主题 | 核心判断 |
| --- | --- | --- | --- |
| PD3: Prefetching Data with DPUs for Disaggregated Memory | `05_pd3.pdf` | DPU / disaggregated memory / prefetch | 用 DPU 在请求进入 compute server 前解析和预取远端内存数据，把 RDMA/DMA 开销下沉到网络路径。价值在于把“应用语义 + DPU 近数据路径”结合，减少 disaggregated memory 的 cache miss 成本。 |
| UpFuzz: Detecting Data Format Incompatibility Bugs during Distributed Storage System Upgrade | `06_upfuzz.pdf` | 分布式存储升级 / fuzzing | 聚焦升级中的数据格式不兼容，追踪 transitively persisted states，并用格式属性选择更可能触发失败的测试。已在 Cassandra、HBase、HDFS 中发现 15 个未知升级故障，8 个被开发者确认。 |
| Libra: Flexible Request Partitioning and Scheduling for Serving Unbalanced and Dynamic LLM Workloads | `07_libra.pdf` | LLM serving scheduling | 虽在 scalable storage session，但更像 LLM serving 系统。storage 相关点是 KV cache transfer 与 disaggregated/colocated serving 的调度边界。 |
| Come Hell or Still Water: Alleviating Tail Latency in Cloud Block Store | `08_blockstore.pdf` | 云块存储 / tail latency / 生产系统 | 阿里云 EBS 生产经验。识别少量虚拟盘突发导致集群尾延迟问题，用双 bucket throttle 和优先级调度处理 burst 与 underloaded 场景。生产中 burst 场景 P99999 steady segment 尾延迟降 59.7%，underloaded 全 I/O 降 22%。 |
| Wallet: Confidential Serverless Computing | `09_wallet.pdf` | confidential serverless | 安全/serverless 系统，和 storage session 的联系较弱；数据中心机密数据流和 I/O 架构是相关点。 |

## NSDI 2026: 强存储相关补充

这些论文不都在官方 `Storage` 标题 session 下，但对 storage 方向非常值得一起看。

| 论文 | 本地 PDF | Session | 主题 | 核心判断 |
| --- | --- | --- | --- | --- |
| ZipLLM: Efficient LLM Storage via Model-Aware Synergistic Data Deduplication and Compression | `10_zipllm.pdf` | Hot Data, Cold Data | LLM model storage / dedup / compression | 面向 Hugging Face 等模型仓库的十 PB 级模型存储。利用同族微调模型的稀疏结构化差异、bitwise family clustering、tensor-level dedup，组合 BitX lossless delta compression，整体节省 54% 存储，较单独 dedup/compression 高 20%+。 |
| Latency-Aware Caching with Delayed Hits | `11_latency_caching.pdf` | Hot Data, Cold Data | latency-aware cache policy | 把 cache 策略拆成 pipeline 的正交 policy，并加入 Least Bursty Used 处理 delayed hits。13 个真实 trace 上平均请求延迟比最佳 SOTA 降 10%。 |
| Cortex: Low-Latency, Cost-Efficient Remote Data Access For LLM via Semantic-Aware Knowledge Caching | `12_cortex.pdf` | Hot Data, Cold Data | LLM agent / semantic cache | 面向跨云/跨区域知识访问，把 exact-match cache 扩展成语义 cache。通过 Semantic Element 和 Semantic Retrieval Index 两级检索，用小 LLM judge 验证语义命中；搜索 workload 吞吐最高 3.6x，coding task 吞吐提升 20%。 |
| Unleashing The Potential of Datacenter SSDs by Taming Performance Variability | `13_sandook.pdf` | Hot Data, Cold Data | rack-scale block storage / SSD variability | Sandook 是机架级块存储系统，统一处理 SSD 磨损/型号差异、读写干扰、GC 等 variability。无需特殊硬件，raw I/O throughput 提升 30%-82%，应用端到端性能提升 12%-94%。 |
| XLL: Cross-Layer Logging for Data Deduplication in Consensus-Based Storage | `14_xll.pdf` | Distributed Data Systems | consensus storage / write amplification | 识别共识日志和本地数据库日志之间的 cross-layer duplication，做共享 log 和 KV separation。TiKV 上写吞吐 5.5x，写放大降 73%。 |
| Co-Designing Traffic Control with NVMe-oF for Disaggregated Storage | `15_nvmeof_san.pdf` | Distributed Data Systems | NVMe-oF / SAN 架构 | 比较 switched 和 switchless SAN，并围绕 NVMe-oF I/O flow co-design traffic control。结论倾向 switchless SAN 可以在吞吐接近的同时降低延迟、成本和 ToR 单点风险。 |

## 横向趋势

1. AI workload 正在改写 storage 问题定义。
   `FalconFS` 针对深度学习 pipeline 的 namespace/metadata 行为，`ZipLLM` 针对模型仓库，`DistVS` 针对 RAG/向量检索，`Cortex` 针对 LLM agent 的知识访问，`Libra` 则触及 KV cache transfer 与 LLM serving 调度。传统文件/块/缓存问题没有消失，但 workload 假设已经从通用 Web/KV 转向 AI 数据路径。

2. Disaggregation 已经从架构口号进入细节工程。
   `PD3`、`DistVS`、`Sandook`、`NVMe-oF SAN`、阿里云 `Block Store` 都在处理 disaggregation 后的真实代价：网络路径上的 miss、RDMA/DMA 开销、SSD variability、SAN fabric 成本、tail latency 传播。下一步创新空间不只是“把资源池化”，而是围绕池化后的调度、预取、隔离和反馈控制。

3. 写放大仍然是强主线，但层次更深。
   `Nemo` 处理 tiny-object flash cache 的应用层写放大，`XLL` 处理共识层和本地存储层的重复日志，`ZipLLM` 处理模型仓库对象级/张量级冗余。共同点是：只在单层做优化很难见底，必须跨抽象层找重复和批量化机会。

4. Tail latency 和 variability 成为生产存储论文的主战场。
   `Block Store`、`Sandook`、`CacheCatalyst`、`Latency-Aware Caching` 都把平均吞吐放到次要位置，关注 P99/P99999、burst、delayed hit、SSD variability。存储系统的卖点越来越像“稳定地快”，而不只是峰值快。

5. 正确性与可运维性开始和性能并列。
   `UpFuzz` 说明分布式存储升级中的数据格式兼容是高风险区；`Wallet` 虽非传统存储，但强调数据在 serverless 链路中的安全边界；`Lemonshark` 则属于共识层延迟/正确性的 storage-adjacent 方向。这些工作适合作为可靠性/运维论文脉络阅读。

## 阅读优先级

如果目标是跟进存储系统研究，建议优先读：

1. `FalconFS`：AI pipeline 时代的 DFS 设计，非常贴近生产。
2. `Sandook`：disaggregated SSD/block storage 的 variability 管理。
3. `XLL`：跨层日志重复和写放大，问题定义漂亮。
4. `Nemo`：tiny-object flash cache，ASPLOS 中最 storage。
5. `ZipLLM`：模型仓库存储优化，AI storage 新方向。
6. `PD3`：DPU + disaggregated memory 的预取路径。
7. `DistVS`：向量检索的存储层次化设计。
8. `Cloud Block Store`：云厂商生产尾延迟治理经验。

如果目标是找可落地工程启发：

- 读 `Block Store` 和 `Sandook` 学 production tail latency/variability control。
- 读 `XLL` 和 `Nemo` 学跨层写放大拆解。
- 读 `FalconFS` 学如何为 AI workload 重做 metadata/data path。
- 读 `UpFuzz` 学升级兼容性测试如何从“跑更多 case”变成“选更有价值的 case”。

## 风险与待补

- `Hitchhike` 未下载到 PDF 正文；已确认 DOI `10.1145/3779212.3790173`，但 ACM 页面当前对命令行访问返回 Cloudflare challenge。本文未对其正文贡献做深入判断。
- ASPLOS 的 PDF 有 4 篇来自可访问开放 PDF/预印本或已下载文件，后续如需严谨引用页码，应从 ACM 正式 PDF 再核一次。
- NSDI 的 PDF 均来自 USENIX 官方下载路径，可信度较高；但本分析按 storage 视角筛选了相邻 session，未覆盖所有 CDN/edge/data delivery 论文。
