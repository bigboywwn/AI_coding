# FAST 2026 AI and LLMs 论文分析报告

分析目录：`/Users/miaomili/Documents/FAST26_papers/sessions/AI_and_LLMs`

覆盖论文数：9

分析方法：基于论文 PDF 文本抽取，对每篇论文按照“问题定义 - 核心方法 - 实验结果 - 优势 - 局限 - 可复现性”统一评估。文中“分析判断”表示我根据论文证据做出的推断，不等同于作者原文表述。

## 一、会话级总览

这个 session 的论文虽然题目分散，但主线非常清晰：**AI/LLM 系统已经把瓶颈从单纯算力推向了存储、内存层次、检查点、KV cache 和工程演化成本**。九篇论文里，绝大多数工作都在回答同一个问题：当模型规模、上下文长度、并发规模和工程复杂度同步增长时，系统该如何把“数据移动成本”降下来。

从研究主题看，大致可以分成四类：

1. **LLM 推理期的数据通路优化**  
   包括 `Accelerating Model Loading...`、`Bidaw`、`CacheSlide`、`SolidAttention`、`Fast Cloud Storage for AI Jobs...`。这些工作分别从模型加载、交互式多轮会话 KV 缓存、Agent prompt KV 复用、本地长上下文 KV 外存化、云存储读写 API 五个层面降低推理时延或提升吞吐。

2. **训练期容错与数据管线优化**  
   包括 `AdaCheck`、`Preparation Meets Opportunity (Seneca)`、`GPU Checkpoint/Restore Made Fast and Lightweight`。核心思路是利用冗余、缓存和增量性，把 checkpoint 或输入管线的开销压低到更可接受的水平。

3. **把“系统知识”显式化、结构化**  
   `CacheSlide` 用 RPDC 明确定义一种新的 KV 复用模式；`AdaCheck` 用 tensor redundancy 建模状态冗余；`SysSpec` 则把文件系统开发经验提升为规格化生成范式。共同点是：**先把隐含规律说清楚，再围绕规律做优化**。

4. **跨层协同而不是单点优化**  
   这一 session 最突出的研究风格不是“某个算子更快”，而是**把应用层行为、运行时、缓存策略、SSD/DRAM/网络、内核或云存储 API 一起设计**。这是工程上更难、但也更有系统论文价值的路线。

## 二、总体判断

如果从工程成熟度看，最接近生产系统改造路线的是：

- `Accelerating Model Loading in LLM Inference by Programmable Page Cache`
- `Bidaw`
- `Fast Cloud Storage for AI Jobs via Grouped I/O API with Transparent Read/Write Optimizations`
- `GPU Checkpoint/Restore Made Fast and Lightweight`

如果从研究新意和问题建模能力看，最突出的几篇是：

- `CacheSlide`
- `AdaCheck`
- `Sharpen the Spec, Cut the Code: A Case for Generative File System with SysSpec`

如果从“是否抓住了未来几年 LLM 基础设施真实瓶颈”看，我认为最重要的趋势有三条：

- **KV cache 正在成为独立系统层**，而不是推理框架里的附属缓存。
- **checkpoint 正在从容错机制变成性能关键路径**，尤其是在弹性部署、任务切换和超大规模训练里。
- **兼容性与部署成本已经和性能一样重要**，很多论文不再追求“极致快”，而是在“快 + 可落地”之间做系统设计。

## 三、速览对比表

| 论文 | 核心问题 | 核心方法 | 关键结果 | 简要评价 |
| --- | --- | --- | --- | --- |
| Accelerating Model Loading in LLM Inference by Programmable Page Cache | LLM 冷启动/弹性部署时模型加载过慢 | 可编程页缓存 PPC + 面向模型加载的 MAIO 策略 | 模型加载延迟最高降 79%，弹性部署吞吐最高提升 36% | 兼容性意识很强，偏工程落地 |
| AdaCheck | 大规模 LLM 训练 checkpoint 冗余过高 | tensor redundancy 建模 + 离线/在线冗余利用 | checkpoint 尺寸降 6-896x，频率增 1.46-111x | 针对并行冗余的系统化方案 |
| Bidaw | 交互式多轮会话中两级 KV 缓存加载过慢 | 计算侧按 I/O 延迟调度，存储侧按会话模式驱动淘汰 | 延迟最高降 3.58x，吞吐最高升 1.83x | 很贴近真实交互式服务负载 |
| CacheSlide | Agent prompt 中多段固定上下文难以高效复用 KV | 定义 RPDC，并设计 CCPE/WCA/SLIDE | 延迟降 3.11-4.3x，吞吐升 3.5-5.8x | 问题定义和系统设计都很强 |
| Fast Cloud Storage for AI Jobs via Grouped I/O API... | AI 作业对云存储带宽需求过高 | 分组 I/O API + DRAM/compute fabric 作为暂存层 | checkpoint 写入比通用存储快 3.9-58.8x，最高比 Gemini 快 5.9x | 基础设施层价值高，生产味很重 |
| GPU Checkpoint/Restore Made Fast and Lightweight | GPU C/R 难以同时做到低延迟、低开销、增量化 | control/data separation + CPU shadow execution | checkpoint 延迟降 72.1%/63.6%，恢复降 54.2%/87.1% | 对 serverless/切换/容错都重要 |
| Preparation Meets Opportunity (Seneca) | 多作业训练时数据预处理与缓存瓶颈严重 | cache partitioning + opportunistic data sampling | makespan 降 45.23%，DSI 吞吐最高升 3.45x | 更偏通用 ML 数据通路 |
| Sharpen the Spec, Cut the Code | 文件系统演化成本高，LLM 直接生成不可靠 | SysSpec 规格驱动生成 + DAG patch 演化 | 生成的 SpecFS 在 754 个 xfstests 中仅因未实现功能失败 64 个，并接入 10 个 Ext4 特性 | 非 LLM serving，但对“用 LLM 造系统”有启发 |
| SolidAttention | 内存受限 PC 上长上下文推理的 KV cache 占用过大 | 稀疏注意力与 SSD 管理协同设计 | 128k 上最高提速 3.1x，KV 内存最高降 98% | 聚焦 AIPC，本地部署场景清晰 |

## 四、逐篇分析

### 1. Accelerating Model Loading in LLM Inference by Programmable Page Cache

**作者**：Yubo Liu, Hongbo Li, Xiaojia Huang, Yongfeng Wang, Hanjun Guo, Hui Chen, Yuxin Ren, Ning Jia  
**会议**：FAST 2026  
**链接**：[USENIX 页面](https://www.usenix.org/conference/fast26/presentation/liu-yubo)

#### 论文概述

论文关注 MaaS 场景中经常被低估的冷启动瓶颈：**模型加载**。作者认为，现有优化经常依赖特定推理框架、硬件或内核改造，虽然快，但兼容性差，因此很难在真实生产系统中广泛落地。为此，论文提出可编程页缓存框架 `PPC`，并在其上实现面向模型加载的缓存策略 `MAIO`。

核心思想不是改推理框架，而是把优化下沉到**文件系统页缓存策略**：通过 I/O 模板来感知模型加载模式，再利用 SSD 带宽、XPU affinity 和数据局部性做精细预取和淘汰。

#### 关键亮点

- 明确把“兼容性”作为一等设计目标，而不是附带条件。
- 用 `PPC` 把页缓存策略用户态可编程化，同时避免侵入式修改内核。
- `MAIO` 利用“同类推理服务具有稳定 I/O 模式”这一观察构造 I/O template。
- 实验显示模型加载延迟最高下降 79%，弹性部署吞吐最高提升 36%。

#### 方法分析

方法分两层：

- `PPC`：由内核中的 routing file system 和用户态 cache policy runtime 组成，让用户在不改原生内核文件系统的前提下接管缓存决策。
- `MAIO`：针对模型加载这一特定阶段设计三类机制，包括中断式预取、XPU 亲和加载和 “Burn-after-Reading” 淘汰。

这个设计的价值在于，它不要求推理框架知道底层缓存策略，也不要求硬件具备特定能力，因而部署摩擦较低。

#### 实验结果

- 模型加载延迟：在内存充足与受限场景中，分别最高优于现有兼容优化 79% 和 74%。
- 推理服务启动：相对 Native 最多降低 38% 启动延迟。
- 真实弹性部署场景：吞吐最高提升 36%。
- I/O template 开销：即便是 DeepSeek-R1-671B，模板也只有 545KB，额外存储开销很低。

#### 优势

- 问题选择很务实，确实击中了弹性 LLM 服务的冷启动痛点。
- 将优化点放在页缓存而不是框架内部，兼容性论证完整。
- 同时比较了兼容和不兼容方案，实验叙事清楚。
- I/O template 的存储开销非常小，利于工程化。

#### 局限与风险

- 评测环境高度依赖华为 Ascend/NPU 生态，兼容性主张在异构 GPU 生态上的证据仍有限。
- 方法依赖“同一推理服务 I/O 模式稳定”这一前提；若模型加载流程高度动态化，模板收益可能下降。
- 论文聚焦本地文件系统模型加载，不覆盖远程对象存储到本地的全链路冷启动。

#### 可复现性

- 论文提供了清晰系统设计和实验结果，但我没有看到明确公开代码信息。
- 复现难点主要在内核模块、页缓存钩子和特定推理栈配合。

#### 结论评价

这是篇很典型的“生产基础设施优化”论文。它最有价值的地方不是单点提速，而是证明了：**在不侵入推理框架的前提下，文件系统页缓存仍有可观优化空间**。

---

### 2. AdaCheck: An Adaptive Checkpointing System for Efficient LLM Training with Redundancy Utilization

**作者**：Weijie Liu, Shengwei Li, Zhiquan Lai, Keshi Ge, Qiaoling Chen, Peng Sun, Dongsheng Li, Kai Lu  
**会议**：FAST 2026  
**链接**：[USENIX 页面](https://www.usenix.org/conference/fast26/presentation/liu-weijie)

#### 论文概述

AdaCheck 的出发点是：超大规模 LLM 训练里 checkpoint 是刚需，但现有系统通常只针对某种并行方式或模型结构做静态优化，无法适配更复杂的并行形态，也没有充分利用**参数状态在不同并行、不同结构、不同训练轮次之间的冗余**。

论文提出 `tensor redundancy` 抽象来统一刻画这些冗余，并同时利用：

- **离线冗余利用**：只保存无冗余状态；
- **在线冗余利用**：进一步利用训练迭代间的冗余。

#### 关键亮点

- 从“保存整个模型副本”转向“保存恢复所需的最小状态集合”。
- 面向各种并行策略，包括自动规划生成的不规则并行。
- 同时覆盖 dense 和 sparse（MoE）架构。
- checkpoint 尺寸最高降低 896x，频率最高提升 111x。

#### 方法分析

方法核心是把复杂状态冗余映射为 tensor redundancy 问题，然后通过：

- 哈希一致性检查；
- 环形通信算法；
- 离线与在线两阶段冗余利用；

来识别“哪些状态其实不需要落盘”。这个思路比传统只在 data parallel 上做 rank-0 save 更一般化。

#### 实验结果

- 相比 SOTA checkpoint 方案，checkpoint 大小降低 6.00-896x。
- checkpoint 频率提升 1.46-111x。
- 对训练吞吐“几乎无开销”。
- 相比 Gemini，仅离线冗余利用就可把 checkpoint 开销最高再降 130x；在线利用还能在离线基础上最高再降 7.09x。

#### 优势

- 对“冗余”这个问题做了抽象提升，不再绑死在某一并行范式上。
- 适配 irregular parallelism，这点对未来自动并行器很重要。
- 结果幅度很大，而且逻辑上自洽。
- 把 checkpoint size 与 checkpoint frequency 一起考虑，指标选择合理。

#### 局限与风险

- 系统复杂度较高，部署前需要可靠的冗余检测和元数据管理。
- 论文主要强调状态冗余利用，对故障恢复路径本身的额外复杂性讨论相对少。
- “几乎无吞吐开销”成立于其评测栈；在通信更紧张的集群上，冗余检测成本是否同样可忽略，还需要更多证据。

#### 可复现性

- 我没有看到明确的开源实现声明。
- 文中提到基于 Merak 等训练框架做分析，但完整系统复现门槛较高。

#### 结论评价

AdaCheck 是这组论文里**最系统地处理训练状态冗余**的一篇。它的价值不只是节省存储，而是让 checkpoint 从“粗粒度的容错快照”变成“可按冗余感知优化的数据产品”。

---

### 3. Bidaw: Enhancing Key-Value Caching for Interactive LLM Serving via Bidirectional Computation-Storage Awareness

**作者**：Shipeng Hu, Guangyan Zhang, Yuqi Zhou, Yaya Wei, Ziyan Zhong, Jike Chen  
**会议**：FAST 2026  
**链接**：[USENIX 页面](https://www.usenix.org/conference/fast26/presentation/hu-shipeng)

#### 论文概述

Bidaw 解决的是**交互式多轮对话**里的 KV cache 问题。用户每次发来新问题时，系统要利用前几轮对话生成的历史 KV；但 GPU 显存不足时，这些 KV 只能缓存在主机内存和 SSD 组成的两级存储里。现有方案的问题是：计算引擎不懂存储延迟，存储系统也不懂交互行为模式，导致 KV 加载成为服务瓶颈。

Bidaw 的核心是“bidirectional awareness”：

- 计算侧知道 KV 在哪一层、大小多少，据此做请求调度；
- 存储侧知道用户会话模式，据此做更合理的 KV 淘汰。

#### 关键亮点

- 目标负载不是离线 batch inference，而是交互式多轮对话。
- 将队列调度与 KV 存储层级联合起来考虑。
- 利用“模型上一轮回答长度”预测下一次 KV 重用距离，这个观察很有意思。
- 在真实交互负载上延迟最高降 3.58x，吞吐最高升 1.83x。

#### 方法分析

Bidaw 包含两条主线：

- **计算侧调度**：把请求分成 ready queue 和 preparing queue，避免高 I/O 延迟请求阻塞低延迟请求。
- **存储侧淘汰**：利用 LLM 生成答案长度与用户下一次访问时间的相关性，估计 KV 的命中概率，从而决定淘汰对象。

论文还进一步比较了缓存不同历史 tensor 的收益与空间占用，选择更“存储效率高”的历史表示。

#### 实验结果

- 现有两级存储方案相对理想大内存基线，延迟最高恶化 3.8x、吞吐最高下降 2.0x。
- Bidaw 相比 SOTA 方案，响应延迟最高降低 3.58x。
- 吞吐最高提升 1.83x。
- 论文使用了自有 interactive conversation workload 和公开多轮对话负载。

#### 优势

- 非常贴近真实线上交互式对话服务，而非纯 benchmark。
- 问题根因定位准确：不是 SSD 慢本身，而是计算调度和存储管理彼此盲。
- 同时优化延迟和吞吐，且指标与交互服务场景吻合。

#### 局限与风险

- 方法依赖会话行为统计规律，若用户交互模式变化很大，预测式淘汰的收益可能波动。
- 主要针对低成本本地部署的两级存储，不直接覆盖大规模分布式内存池方案。
- 论文提供了 workload trace，但未看到完整系统开源。

#### 可复现性

- 论文提到公开了 interactive conversation workload trace。
- 但系统级复现仍需要对计算引擎和存储层同时改造，门槛不低。

#### 结论评价

Bidaw 的贡献在于把 KV cache 当成**交互系统问题**而不是纯缓存问题。对于真正做对话式产品的人，这篇论文的现实意义大于很多只看离线吞吐的工作。

---

### 4. CacheSlide: Unlocking Cross Position-Aware KV Cache Reuse for Accelerating LLM Serving

**作者**：Yang Liu, Yunfei Gu, Liqiang Zhang, Chentao Wu, Guangtao Xue, Jie Li, Minyi Guo, Junhao Hu, Jie Meng  
**会议**：FAST 2026  
**链接**：[USENIX 页面](https://www.usenix.org/conference/fast26/presentation/liu-yang)

#### 论文概述

CacheSlide 聚焦 Agent 场景下的 prompt 结构。作者指出，现有 KV cache 复用分成两类：

- `PDC`：位置依赖缓存，只能在固定位置复用；
- `PIC`：位置无关缓存，可以任意位置复用，但容易产生 positional drift 与额外重计算。

而很多 Agent prompt 实际上更符合第三种模式：**可复用片段的相对顺序稳定，但绝对位置会平移**。作者将其定义为 `RPDC`（Relative-Position-Dependent Caching），并围绕这种模式设计 `CacheSlide`。

#### 关键亮点

- 提出了一个很有说服力的新问题定义：RPDC。
- 设计了 `CCPE`（Chunked Contextual Position Encoding）缓解位置漂移。
- 用 `Weighted Correction Attention` 混合新旧 KV。
- 用 `SLIDE` 做 spill-aware、load-write decoupling 和 dirty-page eviction。
- 在多个 Agent benchmark 上延迟下降 3.11-4.3x，吞吐提升 3.5-5.8x。

#### 方法分析

CacheSlide 的方法是“算法 + 系统”联合设计：

- 编码层：通过 CCPE 提高可复用段在位置变化时的编码相似性；
- 注意力层：只对少量 token 计算注意力，再用加权纠正恢复质量；
- 存储层：把 KV spill 到 SSD 时，显式考虑 load/write 解耦和 dirty-page eviction。

这篇论文强在它不是“又一个 KV cache trick”，而是把 Agent prompt 的结构特性和 KV 复用逻辑完整打通了。

#### 实验结果

- 基于 vLLM 0.8.5 实现，测试模型包括 Mistral-7B、MPT-30B、Llama-3 70B。
- 在 HotPotQA、Multi-Session Chat、SWE-Agent-Bench 等任务上，延迟下降 3.11-4.3x，吞吐提升 3.5-5.8x。
- 相比 ContextCache，TTFT 降低 2.4-3.3x，且准确率几乎无损。
- SSD 写放大降低 3.11-3.62x，GPU 存储占用相对 PromptCache 降低 1.63-1.9x。

#### 优势

- 问题抽象非常到位，RPDC 很可能会成为后续工作的常用术语。
- 评估维度丰富，覆盖 TTFT、吞吐、准确率、写放大、显存占用。
- 既有算法设计，也有系统实现，论文完成度高。
- 代码已开源。

#### 局限与风险

- 一个重要前提是作者为模型引入了 CoPE 支持，并通过 adapter-based continued pretraining 获得兼容实现；这意味着它**不是完全零改模型的方案**。
- 基线使用原生 RoPE/ALiBi，而 CacheSlide 使用启用 CoPE 的实现，比较虽有合理性，但严格公平性仍值得继续讨论。
- 主要适用于 Agent/prompt 结构具有明显 RPDC 特征的场景；在普通前缀缓存任务上，优势未必同样显著。

#### 可复现性

- 论文明确给出开源仓库：`https://github.com/SJTU-Storage-Lab/CacheSlide`
- 基于 vLLM 0.8.5，复现友好度较高。

#### 结论评价

CacheSlide 是这组论文里我最看重的一篇之一。原因不是结果数字最大，而是它给出了一个**新的、可泛化的问题框架**，很可能影响后续 Agent 系统如何设计 KV cache。

---

### 5. Fast Cloud Storage for AI Jobs via Grouped I/O API with Transparent Read/Write Optimizations

**作者**：Yingyi Hao, Ting Yao, Xingda Wei, Dingyan Zhang, Tianle Sun, Yiwen Zhang, Zhiyong Fu, Huatao Wu, Rong Chen  
**会议**：FAST 2026  
**链接**：[USENIX 页面](https://www.usenix.org/conference/fast26/presentation/hao)

#### 论文概述

这篇论文讨论的是更底层、更基础设施化的问题：**AI 作业对云存储带宽的需求已经高到传统分离式存储架构很难经济满足**。作者提出 `AITURBO`，通过两个关键设计来解决：

- 利用 compute fabric 和主机 DRAM 作为中间暂存层；
- 通过 `grouped I/O API` 让存储层能够推导分组读写计划，透明完成 dedup、读写规划、负载均衡。

#### 关键亮点

- 不是做某个框架的 patch，而是提升“云存储层”对 AI I/O 模式的理解能力。
- 分组 I/O API 很简单，但它暴露了跨客户端协同的信息。
- 既支持 checkpoint write，也支持 checkpoint read 和 KV-cache read。
- 已在华为生产云中部署训练任务。

#### 方法分析

AITURBO 把 AI 作业视为成组的协同 I/O 主体，而不是互相独立的文件访问者。存储系统通过 grouped API 获得：

- 哪些 XPU 客户端参与同一组读写；
- 哪些数据存在重复；
- 哪些读写适合通过 compute fabric 广播而不是各自访问存储。

因此，它可以在存储层统一规划 deduplicated write plan 和 staged read plan。这个方向很像把集体通信思想引入存储 API。

#### 实验结果

- checkpoint 写入：相对通用云存储 `SFST URBO`，快 3.9-58.8x。
- 相对 Gemini，在存在重复写时最高快 5.9x。
- checkpoint 读取：部署 Qwen 72B 到 64 XPU 时，只需 2.25s。
- 推理读路径：相对 Mooncake，性能最高提升 1.28x。
- 额外 group coordination 开销在最大 64 XPU 下仅 45ms，较小。

#### 优势

- 生产部署证据很强，可信度高。
- grouped I/O API 抽象简洁，迁移成本低。
- 对 checkpoint write/read 和推理读都能带来收益，适用面广。
- 论文明确讨论了与应用层优化的边界，论证成熟。

#### 局限与风险

- 强依赖云厂商对底层基础设施和 fabric 的控制权，普通用户难以单独采纳。
- 为性能允许部分写先缓存在 buffer 中，存在 durability trade-off。
- 论文明确指出其更适合大块 bulk transfer，不适合小 I/O。
- 对推理场景的 grouped API 协同能力仍弱于训练写入场景。

#### 可复现性

- 论文未明确给出开源实现。
- 由于涉及云基础设施、fabric 和存储层协同，外部团队完整复现难度较高。

#### 结论评价

这是非常标准的“工业界会认真看”的论文。它真正重要的地方在于提出：**AI 存储接口不应继续沿用传统单文件、单客户端抽象**，而应该显式编码群组语义。

---

### 6. GPU Checkpoint/Restore Made Fast and Lightweight

**作者**：Shaoxun Zeng, Tingxu Ren, Jiwu Shu, Youyou Lu  
**会议**：FAST 2026  
**链接**：[USENIX 页面](https://www.usenix.org/conference/fast26/presentation/zeng)

#### 论文概述

GCR 关注 system-level GPU checkpoint/restore。作者认为，现有方案面临三难：

- driver-integrated C/R 正常运行开销低，但 checkpoint/restore 延迟高；
- interception-based C/R 数据复制快，但正常执行开销大；
- 增量 checkpoint 通常做不好。

GCR 尝试同时解决这三个问题。

#### 关键亮点

- 提出 control/data separation 的 hybrid C/R 方案。
- 用 CPU shadow execution 做 dirty buffer 识别，避免把脏页检测放进 GPU 关键路径。
- 支持 fine-grained incremental checkpointing。
- checkpoint 延迟分别比 `cuda-ckpt` 和 `PhOS` 下降 72.1% 和 63.6%。

#### 方法分析

论文把 GPU checkpoint 分为两部分：

- control state：更适合 driver-integrated 机制；
- data buffer：更适合 interception-based 高带宽复制。

于是 GCR 采用混合策略，并通过保存 GPU 虚拟地址映射来保证恢复时地址一致性。同时，为支持增量 checkpoint，论文使用 shadow execution 和 dirty templates 在 CPU 上轻量推导 dirty buffer。

#### 实验结果

- checkpoint 延迟平均下降 72.1%（对 cuda-ckpt）和 63.6%（对 PhOS）。
- restore 延迟平均下降 54.2% 和 87.1%。
- 正常运行开销低于 1%。
- 增量 checkpoint 使 checkpoint 大小平均降低 86.6%，延迟平均降低 43.8%。

#### 优势

- 很清楚地识别了现有方案的 trade-off，并给出结构化折中。
- checkpoint、restore、steady-state overhead 三个指标都覆盖到了。
- 适用场景广：serverless scaling、任务切换、容错计算都能用到。

#### 局限与风险

- 设计依赖较强的 GPU 运行时和地址管理假设，实际系统整合复杂度高。
- 论文主要围绕 CUDA / NVIDIA 生态展开，对其他 GPU 生态的泛化证据有限。
- CPU shadow execution 虽然开销小，但其正确性依赖对 kernel dirty 行为的模板化抽象。

#### 可复现性

- 论文未明确给出开源实现。
- 由于需要深度介入 GPU 运行时和恢复路径，外部复现实操难度较高。

#### 结论评价

GCR 的意义不只是 checkpoint 更快，而是把 GPU C/R 从“某些框架里的特例功能”重新拉回到**通用系统能力**的轨道上。

---

### 7. Preparation Meets Opportunity: Enhancing Data Preprocessing for ML Training With Seneca

**作者**：Omkar Desai, Ziyang Jiao, Shuyi Pei, Janki Bhimani, Bryan S. Kim  
**会议**：FAST 2026  
**链接**：[USENIX 页面](https://www.usenix.org/conference/fast26/presentation/desai)

#### 论文概述

Seneca 关注的是训练中经常被忽视的瓶颈：`data storage and ingestion (DSI)` 管线。随着 GPU 越来越快、CPU 和主机内存相对跟不上，数据解码、转换、采样和装载过程正成为多作业并发训练的主要限制因素。

Seneca 通过两个机制来优化：

- `MDP`：用性能模型决定缓存分配给 encoded / decoded / augmented 三种数据形态的比例；
- `ODS`：在随机采样时优先消费已缓存数据，让多个训练作业共享缓存收益。

#### 关键亮点

- 很好地解释了为什么 CPU-GPU 性能差扩大后，DSI 会成为更严重瓶颈。
- 不是简单多加缓存，而是优化“缓存给谁”和“采样是否感知缓存”。
- makespan 降低 45.23%，相对次优 dataloader 吞吐最高提升 3.45x。
- 工件开源。

#### 方法分析

Seneca 的关键洞见有两个：

- 不同数据形态的缓存价值不同，必须建模而不能拍脑袋分配；
- 随机采样不必死守预定顺序，只要保持伪随机且每个样本在 epoch 内被消费一次，就可以优先用缓存命中的样本。

这使得系统可以在不破坏训练语义的前提下提升 cache hit rate。

#### 实验结果

- 相比 PyTorch，整体 makespan 降低 45.23%。
- 相对次优 dataloader，数据处理吞吐最高提升 3.45x。
- 跨 7 个模型、3 个数据集、5 种硬件配置评估。

#### 优势

- 评测覆盖面较广，不容易被特定 workload 绑死。
- 方法兼顾 cache partitioning 和 sampling，比较完整。
- 开源实现提升了论文可信度和后续影响力。

#### 局限与风险

- 主题更偏通用 ML 数据通路，并非专门针对 LLM。
- 依赖采样顺序可调整这一前提，对某些严格顺序敏感的数据处理流程可能不适用。
- 修改了 PyTorch，工程集成成本虽合理，但仍不是“即插即用”。

#### 可复现性

- 论文明确给出开源仓库：`https://github.com/swiftomkar/seneca-fast26-pytorch`
- 复现友好度较好。

#### 结论评价

Seneca 虽然不是最“LLM 味”的论文，但它提醒了一件重要的事：**训练加速不只是算子和并行，数据预处理系统同样可能吞掉大部分收益**。

---

### 8. Sharpen the Spec, Cut the Code: A Case for Generative File System with SysSpec

**作者**：Qingyuan Liu, Mo Zou, Hengbin Zhang, Dong Du, Yubin Xia, Haibo Chen  
**会议**：FAST 2026  
**链接**：[USENIX 页面](https://www.usenix.org/conference/fast26/presentation/liu-qingyuan)

#### 论文概述

这篇论文与前几篇不同，它不是优化 LLM 系统，而是反过来问：**能否用 LLM 帮我们构建和演化复杂系统软件，例如文件系统？** 作者的结论是，直接用自然语言 prompt 几乎不行，但如果把 prompt 升级为带有功能、模块和并发语义的多部件规格，就有机会。

论文提出 `SysSpec`，并通过它生成并演化文件系统 `SpecFS`。

#### 关键亮点

- 先做 Ext4 演化分析，证明文件系统大量工程成本来自 feature 引入后的修 bug 和维护。
- 用规格而非自然语言 prompt 驱动 LLM 生成系统代码。
- 用 DAG-structured patch 管理规格演化。
- `SpecFS` 在 754 个 xfstests 中只因未实现功能失败 64 个，并平滑接入 10 个真实 Ext4 特性。

#### 方法分析

SysSpec 的核心不是“让 LLM 写代码”，而是：

- 明确规格语义，缩小 specification semantic gap；
- 通过模块化和并发描述降低生成歧义；
- 用多 agent 流水线做生成、验证和修正；
- 让 patch 作用于规格层，而不是直接 patch 代码。

这比常见的代码生成工作要系统得多。

#### 实验结果

- 分析 Ext4 从 Linux 2.6.19 到 6.15 的 3157 个提交，发现 82.4% 属于 bug fix 和 maintenance，直接新增 feature 的只有 5.1%。
- 生成的 `SpecFS` 代码约 4300 LOC。
- 在 754 个 xfstests 中失败 64 个，且均归因于未实现功能。
- 成功以 spec patch 方式接入 10 个 Ext4 特性。

#### 优势

- 问题切入角度很新：不是让 LLM 替代程序员，而是重构复杂系统的开发范式。
- 规格层 patch 的想法很有长远意义。
- 不是玩具系统，评测使用真实文件系统测试套件。

#### 局限与风险

- 这项工作更多证明“可行性”，离工业级文件系统仍有明显距离。
- 正确性主要通过测试与 LLM-based validation 保证，并非严格形式化验证。
- 规格编写本身仍然需要高水平专家，工作并没有消灭复杂性，只是把复杂性迁移到了 specification 层。

#### 可复现性

- 论文未在文中明确给出开源链接。
- 复现需要 agent 流水线、规格工具链和文件系统测试环境。

#### 结论评价

这篇论文是本 session 里最具“范式探索”意味的一篇。它不一定会立刻改变文件系统开发，但很可能影响大家如何思考“LLM 参与系统软件开发”的正确接口。

---

### 9. SolidAttention: Low-Latency SSD-based Serving on Memory-Constrained PCs

**作者**：Xinrui Zheng, Dongliang Wei, Jianxiang Gao, Yixin Song, Zeyu Mi, Haibo Chen  
**会议**：FAST 2026  
**链接**：[USENIX 页面](https://www.usenix.org/conference/fast26/presentation/zheng)

#### 论文概述

SolidAttention 针对 AIPC / 本地 PC 部署场景。作者指出，很多现有工作默认“整个 KV cache 能放进内存”，但现实中的 PC 往往只有 8-16GB DRAM，长上下文下 KV cache 远超可承受范围。直接量化 KV cache 会损失精度，而把 KV spill 到 SSD 又会因低并发场景难以隐藏 I/O 延迟。

论文提出的核心思路是：**把动态稀疏注意力算法和 SSD 存储管理协同设计**。

#### 关键亮点

- 明确聚焦“低并发、延迟敏感、本地部署”这一与数据中心不同的目标。
- 用 KV block consolidator 把细粒度随机访问转成更适合 SSD 的粗粒度访问。
- 用 speculative prefetcher 预测并提前载入 KV block。
- 用 SSD-aware scheduler 微任务化注意力模块。
- 在 128k 上最高提速 3.1x，KV 内存最高降低 98%。

#### 方法分析

SolidAttention 解决的是稀疏注意力和 SSD 特性之间的结构性冲突：前者天然是动态且细粒度的，后者偏好粗粒度顺序访问。论文通过：

- KV consolidation；
- speculative prefetch；
- compute/I/O orchestration；

把“注意力选择”与“SSD 访问粒度”绑定起来，尽量避免 I/O 阻塞。

#### 实验结果

- 在 128k token 上，相对现有方案最高提速 3.1x。
- KV cache 内存占用最高降低 98%。
- 在 CUDA 后端，相对 Offload+Sparse 最高提速 2.8x/3.1x/2.4x。
- 对 14B 模型在更大内存条件下，仍可把 KV footprint 压低 98%，吞吐最高提升 1.7x。
- speculative prefetch 可带来最高 3.1x（SYCL）和 3.9x（CUDA）的 blocking latency 降低。

#### 优势

- 场景定位准确，抓住了本地 LLM 部署与数据中心部署的不同约束。
- 不是简单 offload，而是完整的 attention-storage co-design。
- 兼顾了延迟、内存占用与精度。

#### 局限与风险

- 主要针对支持动态稀疏注意力和 SSD offloading 的推理栈，工程整合复杂。
- 结果很依赖 SSD 特性、PCIe/后端带宽和模型结构，不同终端设备上的收益波动可能较大。
- 虽然论文强调 accuracy 基本不损失，但完整生态兼容性和开箱即用程度还有距离。

#### 可复现性

- 论文中未看到明确开源链接。
- 实现涉及 CUDA/SYCL 双后端和较多底层优化，复现门槛中等偏高。

#### 结论评价

SolidAttention 证明了一点：**内存受限终端上的长上下文推理，并不一定只能靠更激进的量化，也可以通过系统层次的外存协同来做**。

## 五、跨论文比较与趋势总结

### 1. 最重要的共同主题：利用“可预测性”

这批论文里，收益最大的设计几乎都在利用某种可预测性：

- `MAIO` 利用模型加载 I/O 模式稳定；
- `AdaCheck` 利用训练状态冗余稳定；
- `Bidaw` 利用交互会话重用距离与回答长度相关；
- `CacheSlide` 利用 Agent prompt 中固定段相对顺序稳定；
- `AITURBO` 利用 AI 作业中 group I/O 模式稳定；
- `GCR` 利用 dirty buffer 的模板化可分析性。

这说明 AI 系统虽然规模更大了，但并没有变得“完全不可预测”；相反，**一旦把模式刻画清楚，系统优化空间很大**。

### 2. 存储已经从“底层设备”变成“协同控制层”

传统系统里，存储常被当成被动资源；这组论文里，存储层开始主动参与：

- 决定如何调度请求；
- 决定如何推断未来访问；
- 决定如何做组播、去重和预取；
- 决定哪些 KV / checkpoint 应该保留、丢弃或重写。

这意味着未来 AI 基础设施里，storage runtime 会越来越像一个调度器，而不是文件读写接口。

### 3. 兼容性是系统论文的新硬约束

这组论文里有多篇都明确把“兼容性”写进动机：

- `MAIO` 强调不改内核主线、不依赖特定框架与硬件；
- `AITURBO` 强调少量代码改动；
- `GCR` 强调 application-transparent；
- `SysSpec` 则把人写代码的负担转移到规格层。

这反映出一个现实：AI 系统栈已经太复杂，**单点极致优化如果破坏兼容性，边际价值会明显下降**。

### 4. 我认为最值得持续跟踪的三篇

如果你的关注点是 **LLM serving / infra**，建议优先持续跟踪：

- `CacheSlide`：因为它定义了一个可能持续扩展的新问题类 RPDC。
- `Bidaw`：因为交互式 KV cache 很可能成为线上服务长期瓶颈。
- `Accelerating Model Loading in LLM Inference by Programmable Page Cache`：因为冷启动和弹性扩缩容是大模型服务的现实硬问题。

如果你的关注点是 **训练系统与可靠性**，优先看：

- `AdaCheck`
- `GPU Checkpoint/Restore Made Fast and Lightweight`
- `Fast Cloud Storage for AI Jobs via Grouped I/O API with Transparent Read/Write Optimizations`

## 六、简短结论

FAST 2026 这个 AI and LLMs session 的共同特征不是“把 Transformer 算得更快”，而是**把 AI 系统里那些原本被当作附属开销的部分重新提升为一等研究对象**：页缓存、KV cache、两级存储、检查点、输入管线、存储 API、系统规格。

从这个角度看，这个 session 释放了一个很清楚的信号：**下一阶段 AI 系统优化的核心，不只是更强算力，而是更聪明的数据移动与更低摩擦的系统演化**。
