# Co-Designing Traffic Control with NVMe-oF for Disaggregated Storage 论文总结报告

论文：Chendong Wang, Joontaek Oh, Ming Liu. NSDI 2026.  
官方来源：https://www.usenix.org/conference/nsdi26/presentation/wang-chendong  
本地 PDF：`/Users/mlx/Documents/work/downloads/nsdi2026-storage/papers/15_nvmeof_san.pdf`  
本地抽取文本：`/Users/mlx/Documents/work/downloads/nsdi2026-storage/text/15_nvmeof_san.txt`

## 一句话总结

这篇论文比较了 dense NVMe storage disaggregation 场景下 switched SAN 与 switchless SAN 两种扩展路线，并证明：当把 NVMe-oF 流量的协议语义用于路由、带宽预约和调度时，switchless SAN 可以在吞吐接近 switched SAN 的同时，获得更低延迟、更低资本成本、更好的路径多样性和 ToR 单点故障规避能力。

## 问题背景

现代 storage appliance 越来越“密”：

- 新 CPU/PCIe root complex 支持更多 PCIe lanes，单机理论 I/O 带宽可达 TB/s 级。
- EDSFF/E1.S 等 NVMe form factor 提高盘密度，一个 1U server 可以从 10 块 2.5 寸 NVMe 增到 32 块 E1.S NVMe。
- 产业产品如 Microsoft/Fungible FS1600 已经把 24 块 NVMe SSD 配 12×100GbE 端口，提供 1500 万 random 4KB IOPS。

这导致 SAN fabric 需要大幅扩展带宽。常见两条路线：

- Switched SAN：使用高 radix、高带宽 SAN switch，scale-up。好部署、性能直观，但高端 switch、cable、adapter 成本高，且未来更高带宽 switch 芯片复杂度会继续增加。
- Switchless SAN：在 storage node 上使用低 radix adapter，多路径直连，scale-out。成本低、路径多，但 multi-hop routing、path selection、congestion control 会增加复杂度，并可能对上层 storage stack 不透明。

论文要回答的问题是：面向 disaggregated NVMe storage，哪种架构更适合扩展带宽？

## 方法论

论文结合了小规模真实原型和大规模仿真。

### Switched SAN 原型

- 32-port 100GbE Dell Z9100-ON SAN switch。
- 32-port 100GbE Netberg Aurora 710 Tofino P4 switch。
- x86 storage/client servers，ConnectX-6 NIC，Intel/Samsung NVMe SSD。
- 使用 NIC teaming/link aggregation 扩带宽。

### Switchless SAN 原型

论文用 BlueField-2 SmartNIC 构建低 radix storage adapter，原因是：

- 可编程数据平面，便于实现不同 traffic control 策略。
- 与 switched SAN 使用类似 NIC substrate，减少网卡差异造成的偏差。

Adapter 内部包括：

- parser/deparser：识别 NVMe-oF 命令，封装/解封装 packet。
- ingress/egress pipeline：查 forwarding table，改 packet。
- traffic manager：维护 telemetry、做调度和控制。

网络拓扑取决于 adapter port 数：1 port 可 daisy chain，2/3 port 可 ring/dual-ring，4+ port 可 3D torus/dragonfly 等。

论文先量化 adapter 额外 hop 的成本：每多一跳，4KB/256KB read 约增加 2.9us/3.1us，只占端到端 I/O 延迟 3.4%/1.7%。这支撑了后续结论：NVMe SSD access dominates，适度增加网络 hop 可以接受。

## NVMe-oF 流量特征

论文最重要的分析在第 4.1 节：NVMe-oF 不是普通数据中心流量，它有可利用的协议结构。

### 1. Network RTT 远小于 Storage RTT

拆解 NVMe-oF read/write 延迟后，发现 in-network delay 只占较小比例。QD=1 时，random read 平均 4.8%，sequential write 平均 12.7%；QD 增加后占比更低，例如 QD=64 的 4KB read/write 分别只占 3.8%/2.8%，256KB 甚至低至 0.5%/0.2%。

设计启发：可以用少量网络延迟换取更好的 I/O load balancing 和 storage-node execution streamline。

### 2. Command Pair 成对且方向不对称

NVMe-oF read：小 request capsule 去 storage，大 data block + completion 回 client。  
NVMe-oF write：大 data 去 storage，小 completion 回 client。

因此 ingress/egress bandwidth 极不对称。论文给出例子：read block size 为 4/32/128KB 时，egress traffic 可比 ingress 高 37x/296.7x/1187.3x；write 则反过来，incoming 比 outgoing 高 75.8x/609.7x/2440.7x。

设计启发：不需要简单追求 full bisection bandwidth，可以基于 read/write ratio 和 I/O size 做提前带宽规划。

### 3. Queueing 会从 storage target 反向传播

NVMe-oF session 的吞吐由网络传输 pipe 和 SSD serving pipe 共同决定。SSD 性能又受 workload、fragmentation、GC、read/write mix 影响。论文观察到 fragmented SSD 比 clean SSD read/write throughput 分别低 25.9%/31.9%。

设计启发：只看网络拥塞不够，必须把 SSD 的可服务能力传回网络 fabric，做 end-to-end flow control。

## 三个 traffic control 机制

论文把 traffic control 拆成三类问题：path selection、congestion/rate control、packet scheduling，并针对 NVMe-oF 语义做 co-design。

### 1. INT-assisted Symmetric Routing, ISR

目标：选择到远端 SSD 的最低拥塞路径，避免某个 overloaded SSD 或路径导致 HoL blocking。

做法：

- 在 NVMe-oF header 后加 ISR header，包含 traversed hop ID、timestamp vector、ECN vector、SSD access latency。
- Submission path 上，每个 hop 选择当前估计最不拥塞的 next hop，记录 hop ID 和 timestamp，队列占用高则置 ECN bit。
- Storage node 在 completion response 中复制 ISR header，并填入 SSD access latency。
- Completion path 按 header 对称返回，同时更新各 switch/adapter 的 telemetry table。

“Symmetric” 只要求一个 command pair 的 submission/completion 路径对称，不要求整个 NVMe-oF session 固定路径；不同 I/O 可以动态切路径。

### 2. Eager Bandwidth Reservation

NVMe-oF request/response 成对且大小可预测，因此可以在看到 submission request 时，为未来 completion I/O 提前预约带宽。

机制：

- 根据 I/O type 和 size 用 offline profiling 得到带宽估计 `BW_est`。
- 在对应 egress queue 的 token bucket policer 中安装 reservation。
- read completion 和 write completion 使用不同 priority queue，降低 mixed stream interference。
- reservation 按 NVMe-oF session 粒度更新。

严格预约会导致低利用率，因为 completion 还没回来时带宽已经被保留。论文引入 over-commitment factor `R_over <= 1` 做 bandwidth deflation，让系统在有 headroom 时允许更多 I/O。

### 3. Storage-driven Traffic Scheduling

Storage node 监控每个 SSD 的 bandwidth headroom，把它编码到 NVMe-oF completion 中带回网络。Switch/adapter 用这些 credit 做调度：

- client 根据 credit 做 rate control，避免压垮 SSD。
- switching hop 根据 target SSD 可用 credit 给 packet 计算 rank。
- 基于 SP-PIFO/PIFO 思想把 packet 放入不同 priority queue。
- 同一 NVMe-oF I/O 的后续 packet 使用相同 rank，避免 packet reordering。

这个机制把“SSD 当前能不能服务”变成网络调度输入，而不只是等网络队列拥塞后才反应。

## 评估结果

### 性能

真实 testbed：4 个 storage nodes，4×100GbE。Switched SAN 单路径聚合 4 port；Switchless SAN 用 2D Torus 四路径。

结果：

- FIO 访问 4 个 NVMe drive 时，在 clean SSD 上，switchless SAN 相比 switched SAN 对 4KB random read 和 128KB sequential write 分别降低 32.3% 和 18.0% 延迟。
- Fragmented SSD 上延迟降低更明显，分别为 43.1% 和 20.3%。
- RocksDB + BlobFS + YCSB：吞吐基本相当，switchless SAN 平均/99.9 分位 read latency 分别低 28.3%/25.0%。
- 大规模仿真 27 storage nodes、每节点 600GbE、3D-Torus：switchless SAN 在 OLTP/Systor/WebSearch 上平均 read latency 分别降低 50.0%/19.5%/15.9%。

### 成本

论文用一个 20 storage nodes 的例子：

- Switched SAN：40 个 adapter + 3 个 32-port switch，总计约 105000 美元。
- Switchless SAN：20 个 4-port adapter，总计约 52000 美元。
- 资本成本节省约 50500-53000 美元，即 50.5%。

重点不是绝对价格，而是趋势：高 radix high-bandwidth switch 成本曲线陡，低 radix adapter 更适合 scale-out。

### 可扩展性

- Uniform 4KB read/write 下，switchless SAN 平均 read latency 降 39.7%。
- 混合 4KB/32KB/128KB I/O 时，read/write latency 降 85.4%/91.2%，因为不同大小 I/O 可以走不冲突路径。
- Incast 到单个 NVMe drive 时，两种架构差异缩小，因为瓶颈在目标 SSD。
- 启用 traffic control 后，switched/switchless 都随 client 数增加保持更稳定延迟；关闭后 SSD overloading 和 network queueing 明显。

### 可靠性

Switched SAN 的 ToR switch 是潜在单点；switchless SAN 有多路径，可绕开失败路径。仿真中：

- Uniform 4KB 95/5 read/write：3D-Torus/dragonfly failure 时吞吐下降 1.6%/2.1%，0.5ms/0.75ms 恢复。
- Mixed 4KB/32KB/128KB 50/50 read/write：吞吐下降 6.8%/4.5%，2ms/1.8ms 恢复。

### Traffic Control Drill-down

- ISR：路径少的 ring topology 可能比 switched 更差；路径丰富如 2D mesh 时，switchless read/write latency 比 switched 低 16.1%/6.4%。
- Eager reservation：无预约时吞吐高但 latency 高；保守预约 latency 低但 bandwidth 利用不足；over-commitment 可在最大吞吐和 modest latency increase 之间平衡。
- Storage-driven scheduling：在 fragmented SSD 上，如果只看网络拥塞，client 会超发 I/O，导致 SSD queueing；把 SSD credit 带回网络后，平均 switchless latency 比 switched 低 25.1%。

## 为什么这篇有意思

这篇论文的价值在于它没有孤立比较“有 switch/无 switch”，而是指出 NVMe-oF 流量本身带有强语义：

- read/write 方向和大小可预测；
- request/response 成对；
- SSD 服务能力是流控的一部分；
- 网络延迟占端到端小头，适度多 hop 可换多路径负载均衡。

所以 switchless SAN 并不是简单省 switch，而是用更多低成本路径和协议感知 traffic control 取代昂贵高 radix switch 的一部分价值。

## 局限与风险

- 论文自己承认没有深入讨论大规模管理复杂度、网络监控、故障定位等运维成本。
- Switchless 需要 storage adapter 支持可编程数据平面或至少支持类似 telemetry/rate control/scheduling 能力。
- 多 hop 虽然相对 SSD latency 小，但未来 ultra-low-latency SSD 下网络占比可能上升，结论需重新评估。
- 当前原型大量依赖仿真扩展到大规模，真实大规模部署中的 cabling、topology management、firmware failure、debuggability 可能改变成本收益。
- 与已有云厂商网络/存储隔离策略、租户 QoS、故障域设计的集成难度未充分展开。

## 对 MoonCake / disaggregated storage 的启发

这篇对 MoonCake 或 KVCache-over-network 的启发很直接：

- 不要把网络看成透明管道。I/O request 的语义、大小、方向、目标设备状态都应该进入网络层调度。
- 如果 KVCache/SSD pool 的请求也有 pairwise 或 read/write asymmetry，可以提前做 bandwidth reservation，而不是等拥塞发生后再控流。
- 目标设备可服务能力需要反向传播。对 SSD 是 headroom/latency，对 KVCache server 可能是 GPU memory pressure、PCIe pressure、SSD queue depth、cache eviction pressure。
- 多路径设计要和上层对象/块调度协同，否则路径多也可能只是增加复杂度。
- Switchless/adapter-based 架构对 rack-scale pooling 有吸引力，但可观测性和故障定位要作为一等设计目标。

## 阅读建议

优先读第 4.1 节，它把 NVMe-oF 的三个 traffic 特征讲清楚，是整篇设计的根。第 4.3-4.5 是协议语义如何变成路由/预约/调度机制。第 5.1-5.5 用来判断 switchless 结论在什么场景成立：路径多、负载异构、SSD 状态变化明显时收益最大；单点 incast 或极低网络复杂度时收益有限。
