# 开源代码仓特性周报（2026-05-04 ~ 2026-05-10）

## 说明

- 统计窗口：2026-05-04 00:00:00 CST ~ 2026-05-11 00:00:00 CST（最近一个完整周）。
- 覆盖仓库：SGLang、vLLM、LMCache、MoonCake。
- 统计口径：仅纳入在窗口内合并、且明确属于新增能力、功能扩展、性能特性扩展或新硬件/新模型支持的 PR；纯 bugfix、纯文档、纯 CI、纯无行为变化重构不纳入。
- 代码同步说明：本次自动化按要求先尝试同步本地代码，但当前运行环境无法解析 `ssh.github.com`，`git fetch/pull` 与新目录 `git clone` 均无法完成；因此“最新代码”和“本周 PR”以 GitHub 在线 PR 元数据为准。
- 本地仓库状态：
  - `sglang`：工作区干净，原计划 `pull`，实际因网络/DNS 受限未完成。
  - `vllm`：工作区干净，原计划 `pull`，实际因网络/DNS 受限未完成。
  - `LMCache`：工作区干净，原计划 `pull`，实际因网络/DNS 受限未完成。
  - `mooncake`：当前工作区存在本地未提交改动，按要求本应新目录拉取；实际同样因网络/DNS 受限未完成。MoonCake 的周报分析来源改为 GitHub 上游 `kvcache-ai/Mooncake`。

## 总览表

| 仓库 | 本周 feature PR 数 | 关键方向 | 代表性进展 |
| --- | ---: | --- | --- |
| SGLang | 4 | SpecDec、新模型支持、内核融合优化 | Kimi-K2.5 Eagle3 MLA、Gemma3/4 + Eagle3、MHC/ Gemma4 内核优化 |
| vLLM | 3 | 低比特量化、AsyncTP、SpecDec | NVFP4 W4A16、NVFP4 AsyncTP fusion、MiMo 2.5 MTP |
| LMCache | 4 | ROCm 稀疏注意力、MP L2、新后端控制项、Mooncake 集成 | CacheBlend Triton Sparse、DAX MP L2、Mooncake L2 batch API |
| MoonCake | 3 | 新模型能力、P2P 架构升级、新硬件传输后端 | Engram、共享 chunk pool P2P、MACA C500 transport |

## SGLang

| 合并时间 (UTC) | PR | 特性 | 详细说明 |
| --- | --- | --- | --- |
| 2026-05-10 11:03 | [#24775](https://github.com/sgl-project/sglang/pull/24775) | MHC pipeline 融合优化 | 该 PR 把 MHC 路径里的 split-k reduction、`mhc_pre` GEMM、RMSNorm 和 `hc_head` 多个阶段进一步融合，新增基于 DeepGemm 与 Triton 的融合 kernel。对 DeepSeek V4 这类 MHC-heavy 路径，收益不是“修 bug”，而是把原来多次 kernel launch 和 HBM round-trip 压成更短执行链。微基准显示 `norm + mhc_pre` 大多在 1.2x~1.9x，加上 `hc_head` 在小 batch/短 token 下可到 2.5x~3.6x，说明 SGLang 仍在持续把热点 kernel 往更深的 fused path 推进。 |
| 2026-05-10 07:24 | [#24696](https://github.com/sgl-project/sglang/pull/24696) | Gemma4 fused Q/K/V RMSNorm + FP8 专家权重加载 | 这个 PR 同时做了两件重要的能力补齐。其一是为 Gemma4 attention 增加 fused Q/K/V RMSNorm kernel，在 prefilling 等非 graph 路径显著减少 launch overhead；其二是补齐 Gemma4 FP8 MoE 的 per-expert checkpoint 加载，使 `RedHatAI/gemma-4-26B-A4B-it-FP8-Dynamic` 这类模型终于能被正确加载。前者是性能特性，后者实际上让一类新 checkpoint 形态“从不可用变为可用”，因此应按 feature 计入。 |
| 2026-05-10 06:57 | [#24826](https://github.com/sgl-project/sglang/pull/24826) | Kimi-K2.5 Eagle3 MLA speculative decoding 支持 | 该 PR 把 Kimi-K2.5 的 MLA 路径接入到 Eagle3 speculative decoding。它的价值不在代码量，而在模型族覆盖面继续扩张：SGLang 的 spec-dec 已不再停留在少数标准架构，而是开始向更复杂的 MLA 模型对齐。这意味着 SGLang 正把 speculative decoding 作为平台级能力向更多前沿模型推广，而不是每个模型单独维护一套例外路径。 |
| 2026-05-09 20:34 | [#23976](https://github.com/sgl-project/sglang/pull/23976) | Gemma3/4 + Eagle3 支持 | PR 为 Gemma3/4 打通 Eagle3，重点补齐 aux embedding capture、额外 norm layer 以及 TP>1 时 embedding 处理不一致的问题。对用户来说，这不是单纯的兼容修补，而是把 Gemma3/4 纳入了 SGLang speculative decoding 可覆盖的主流模型范围，后续推理加速和 accept-rate 调优才有落地基础。 |

## vLLM

| 合并时间 (UTC) | PR | 特性 | 详细说明 |
| --- | --- | --- | --- |
| 2026-05-10 01:13 | [#41882](https://github.com/vllm-project/vllm/pull/41882) | NVFP4 AsyncTP all-gather + GEMM fusion | 该 PR 把 NVFP4 的 all-gather 与 FlashInfer FP4 GEMM 融合进 AsyncTP 路径，新增 `fused_all_gather_flashinfer_fp4_matmul`。这意味着 NVFP4 不再只是“能加载/能算”，而是开始进入张量并行下的高性能融合执行路径。基准中，随着输入长度增大，总吞吐提升约 0.9% 到 13.5%，说明 vLLM 对低比特权重的优化已从算子可用性推进到分布式执行效率。 |
| 2026-05-09 21:15 | [#41769](https://github.com/vllm-project/vllm/pull/41769) | 原生支持 ModelOpt NVFP4 W4A16 checkpoint | vLLM 新增对 NVIDIA ModelOpt 产出的 NVFP4 W4A16 checkpoint 的原生支持，新增 `W4A16_NVFP4` 路由和专用 linear method，可直接走 `marlin_fp4` kernel。这个能力很关键，因为它把“新一代 4-bit 权重格式”从外部转换流程拉回到 vLLM 原生加载链路里，也为后续 CLI 配置和更多模型覆盖打了底。 |
| 2026-05-09 18:23 | [#41905](https://github.com/vllm-project/vllm/pull/41905) | MiMo 2.5 多 token MTP speculative decoding | 该 PR 为 `XiaomiMiMo/MiMo-V2.5` 扩展了 `num_speculative_tokens > 1` 的 MTP 支持，使 MiMo 2.5 不再局限于单 speculative token。它的意义在于 speculative decoding 从“模型能否支持”继续演进为“模型能否支持更高阶 spec 配置”，这会直接影响吞吐和延迟调优空间。测试结果也表明，关闭 async scheduling 后能更稳地保持 GSM8K 精度。 |

## LMCache

| 合并时间 (UTC) | PR | 特性 | 详细说明 |
| --- | --- | --- | --- |
| 2026-05-09 01:19 | [#3092](https://github.com/LMCache/LMCache/pull/3092) | ROCm Triton block-sparse backend for CacheBlend | 这是本周 LMCache 最硬核的一条 feature。PR 新增 `LMCTritonSparseBackend` 与对应 Triton kernel，让 CacheBlend 的非前缀 KV 复用在 AMD MI300X / MI355X 上可运行，不再依赖 flashinfer。除此之外，它还顺手补齐了对 vLLM 0.18+ 的 lookup 序列化与 embedding fallback 兼容。方向上看，这代表 LMCache 开始把 CacheBlend 从“偏 CUDA 的实验能力”推进为“可跨硬件落地的稀疏注意力能力”。 |
| 2026-05-07 21:09 | [#3161](https://github.com/LMCache/LMCache/pull/3161) | MP 模式内建 DAX L2 adapter | LMCache MP mode 新增内建 `dax` L2 adapter，提供基于 Device-DAX 的异步 store、lookup-and-lock、load、unlock、delete 和 usage/status reporting。它的重要性在于：L2 不再只有文件、对象存储或网络型 backend，而是开始支持更接近本地持久内存/字节寻址设备的高性能层。尽管当前是 volatile-only，但对追求更低延迟 L2 的部署场景来说，这是一条非常明确的产品能力扩张。 |
| 2026-05-07 04:56 | [#3172](https://github.com/LMCache/LMCache/pull/3172) | Mooncake L2 adapter 原生 batch API | PR 为 `MooncakeConnector` 原生实现 `do_batch_get`、`do_batch_set`、`do_batch_exists`，不再退回到逐 key 循环。对于大对象 KV 读写，吞吐瓶颈仍主要在 RDMA 带宽，但在 lookup-heavy 场景中，批处理带来 3.6x~5.4x 的延迟改善。更重要的是，这使 LMCache 与 Mooncake 的集成层从“功能可用”升级到“接口语义对齐、性能语义对齐”，是生态协同上的 feature。 |
| 2026-05-06 21:26 | [#3169](https://github.com/LMCache/LMCache/pull/3169) | RawBlock backend 新增跳过 checkpoint 恢复选项 | `rust_raw_block.load_checkpoint_on_init` 让 `RustRawBlockBackend` 可在启动时跳过已有 metadata checkpoint 恢复。默认值不变，但新选项给了用户“强制从空状态启动”的能力。虽然改动不大，但这是明确的新控制面 feature，尤其适合调试、压测或希望避开历史状态污染的场景。 |

## MoonCake

| 合并时间 (UTC) | PR | 特性 | 详细说明 |
| --- | --- | --- | --- |
| 2026-05-09 16:28 | [#2059](https://github.com/kvcache-ai/Mooncake/pull/2059) | Metax MACA C500 `maca_transport` | MoonCake Transfer Engine 新增独立 `maca_transport`，把 Metax MACA C500 的设备内 P2P 支持正式抽成单独 transport，而不是继续挤在 `nvlink_transport` 的兼容分支里。这个特性的意义是 MoonCake 的 transport abstraction 正在继续外扩，能够更系统地纳入新型 GPU/AI 加速器平台。验证数据里 2-GPU C500 可达到约 6.9 GB/s。 |
| 2026-05-08 11:52 | [#1483](https://github.com/kvcache-ai/Mooncake/pull/1483) | Mooncake Store 支持 Engram | 这是本周 MoonCake 最值得关注的新能力。PR 按 DeepSeek Engram 论文，把 N-gram 哈希映射、embedding lookup、context-aware gating、ShortConv 与 Mooncake Store 结合起来，并提供 Pybind11 Python 绑定、零拷贝 registered buffer 路径以及完整文档与测试。它意味着 MoonCake 不再只是“存/传 KV cache 或 tensor”的基础设施，而开始尝试承接更上层的新型 memory-augmented 推理能力。 |
| 2026-05-07 04:17 | [#1971](https://github.com/kvcache-ai/Mooncake/pull/1971) | Mooncake-PG 共享 chunk pool + credit-based P2P protocol | 虽然 PR 标成 refactor，但它本质上引入了一套新的 P2P 数据面协议：从 sender-driven ring buffer 切换到 receiver-driven、credit-based RDMA pull，并用共享 `SendPool/RecvPool` 替代原本按 peer 预分配的大块 buffer。结果是同样 256 MB 内存预算下，最小传输单元从 2 MB 提升到 16 MB，`regular-k` 基准带宽从 121 GB/s 提升到 297 GB/s。对 Mooncake-PG 而言，这已经是平台级能力升级，而不只是代码整理。 |

## 跨仓库观察

| 主题 | 观察 |
| --- | --- |
| SpecDec 继续从“支持”走向“按模型族扩张” | SGLang 本周把 Kimi-K2.5、Gemma3/4 继续并入 Eagle3；vLLM 则把 MiMo 2.5 的 MTP 配置往多 speculative token 推进。说明 speculative decoding 已进入“广覆盖 + 深调优”阶段。 |
| 低比特/压缩权重栈在快速演进 | vLLM 同时推进 NVFP4 W4A16 与 AsyncTP fusion；SGLang 补齐 Gemma4 FP8 MoE checkpoint 加载。行业重点已经从“有没有量化能力”转向“量化格式是否能进入主执行路径”。 |
| KV / L2 生态开始跨项目协同 | LMCache 本周最明显的 feature 之一是 Mooncake L2 adapter 的 batch API；MoonCake 自身也在继续演进存储与传输底座。这说明 KV 生态不再是单项目内闭环，而是逐步形成 LMCache + MoonCake + serving engine 的协同栈。 |
| 多硬件后端仍是基础设施主线 | LMCache 给 AMD ROCm 补齐 CacheBlend sparse backend，MoonCake 给 Metax MACA C500 增加新 transport。硬件多样性依然是推理基础设施演进的第一驱动力之一。 |

## 结论

本周四个仓库的 feature 演进，比上周更集中在“把已有方向做深”而不是“零散补点”。最值得持续跟踪的四条主线是：

1. SGLang 对 speculative decoding 的模型覆盖扩张，尤其是 Kimi/Gemma 系列。
2. vLLM 对 NVFP4 的原生支持和分布式融合优化，代表低比特权重正走向主流执行路径。
3. LMCache 在 MP L2、Mooncake 集成和 AMD 稀疏注意力上的产品化推进。
4. MoonCake 从传输/存储底座继续向新模型能力和新硬件 transport 外扩。
