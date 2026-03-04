# Mooncake 本地可编译性评估

分析日期：`2026-03-04`

评估对象：

- 仓库：`https://github.com/kvcache-ai/Mooncake`
- 本地路径：`/Users/miaomili/Documents/Playground/Mooncake`
- 当前机器：Apple Silicon macOS

## 评估目标

这份评估只回答一个实际问题：

- 在当前这台 macOS 机器上，Mooncake 哪些部分可以本地进行有效开发或验证
- 哪些部分至少需要迁到 Linux
- 哪些部分不只需要 Linux，还需要对应的 RDMA / GPU / NPU / CXL 硬件环境

## 当前机器事实

当前本机实际状态如下：

- 操作系统：`macOS 26.3`
- 架构：`arm64`
- 编译器：`Apple clang 17`
- `cmake`：未安装
- Python：`3.9.6`
- Homebrew：已安装
- `extern/pybind11`：submodule 未初始化

这几个事实本身已经说明：

1. 当前机器连最基础的顶层 CMake 配置都还不能直接开始。
2. 即使把 `cmake` 补上，平台层面的 Linux 依赖仍然会阻塞核心模块构建。

## 直接证据

### 构建文档明确指向 Linux

仓库的 build guide 直接写了推荐环境是：

- `Ubuntu 22.04 LTS+`
- `gcc 9.4+` 或手工依赖安装

依赖列表也全部是 Linux 包管理器语义，例如：

- `apt-get install`
- `yum install`
- `libibverbs-dev`
- `libnuma-dev`
- `liburing-dev`

这说明官方默认支持路径不是 macOS。

### 依赖安装脚本是 Linux-only

`dependencies.sh` 的行为是：

- 要求 root
- 直接跑 `apt-get update`
- 安装一整套 Debian/Ubuntu 包
- 下载 `go...linux-<arch>.tar.gz`

这不是“跨平台脚本”，而是明确面向 Linux 的依赖安装脚本。

### `Transfer Engine` 在源码和链接层都依赖 Linux / RDMA

`mooncake-transfer-engine/src/CMakeLists.txt` 里，`transfer_engine` 直接链接：

- `rdma_transport`
- `ibverbs`
- `numa`
- `pthread`
- `yalantinglibs::yalantinglibs`

这里不是“开启 RDMA 时才链接”，而是核心 target 就直接带上了 `ibverbs` 和 `numa`。

同时，源码里还能看到明确的 Linux / RDMA 依赖：

- `topology.cpp` 直接 `#include <infiniband/verbs.h>`
- 直接读取 `/sys/class/infiniband/...`
- 直接读取 NUMA sysfs 信息

这意味着即使只想走 `TCP`，当前默认 `Transfer Engine` 构建路径也不是 macOS 友好的。

### `Mooncake Store` 同样是 Linux-first

`mooncake-store/src/CMakeLists.txt` 里能看到：

- `zstd` 是硬依赖，找不到直接 `FATAL_ERROR`
- `mooncake_master` 直接链接 `ibverbs`
- `io_uring` 是自动探测型可选增强
- 还依赖 `glog`、`gflags`、`asio_shared`、`cachelib_memory_allocator`

源码层面也有明显的 Linux 取向：

- `real_client.cpp` 引入 `numa.h`
- 多处使用 `unistd.h`
- `uring_file.cpp` 明确依赖 `io_uring`

结论很直接：`Mooncake Store` 不只是“最好在 Linux 上跑”，而是当前构建定义本身就默认 Linux。

### Python bindings 也不能脱离 C++ 核心单独成立

`mooncake-integration/CMakeLists.txt` 会构建：

- `engine` Python module
- `store` Python module

它们都直接链接：

- `transfer_engine`
- `mooncake_store`

同时 `mooncake-wheel` 里的 Python 脚本也直接 import：

- `from mooncake.engine import TransferEngine`
- `from mooncake.store import MooncakeDistributedStore`

所以 Python 层不是“纯 Python CLI 工具集”，而是建立在已编译的 C++ extension 之上。

## 结论矩阵

### 当前 Mac 上可以做的部分

这些部分在当前机器上是可行的：

- 阅读和分析源码
- 补文档、画架构图、做设计评审
- 编辑 C++ / Python / CMake 文件
- 对纯文本、配置、文档、Mermaid 图做修改
- 对部分纯 Python 文件做静态阅读和语义分析

这些事情不依赖本地完成编译。

### 当前 Mac 上理论上能做、但不值得投入的部分

理论上你可以尝试移植一小部分 CPU / `TCP` 路径到 macOS，但我不建议这么做。

原因是：

- `Transfer Engine` 当前默认 target 就硬链接 `ibverbs` 和 `numa`
- `YLT_ENABLE_IBV` 在公共配置里默认打开
- 源码里大量直接读取 Linux sysfs 与 Infiniband 设备信息
- `Mooncake Store` 的 master 二进制也直接链接 `ibverbs`

这说明要让它“仅在 macOS 上勉强编过”，你需要做的不是装几个包，而是实质性的移植和条件编译改造。

这类工作属于“移植项目”，不属于“本地编译验证”。

### 必须迁到 Linux 的部分

下面这些部分，想要正常编译或运行，至少应该迁到 Linux：

1. 顶层 CMake 构建
2. `Transfer Engine` 核心库
3. `Mooncake Store` 核心库
4. `mooncake_master`
5. `mooncake_client`
6. `mooncake-integration` 的 `engine` / `store` Python modules
7. 基于这些模块的 tests、examples、benchmarks

原因不是单一依赖缺失，而是构建定义、源码实现和运行假设都明显面向 Linux。

### 必须迁到 Linux + 对应硬件的部分

下面这些功能不只是要 Linux，还需要对应硬件或内核环境：

1. RDMA / Infiniband 路径
2. EFA 路径
3. NVLink / Multi-Node NVLink
4. CUDA GPUDirect / `cuFile`
5. MUSA / HIP / Ascend / CXL 相关路径
6. 依赖真实 `/dev/infiniband`、`/sys/class/infiniband`、NUMA 拓扑的测试

换句话说：

- Linux VM 或 Docker 容器可以帮助你做一部分“能否编译”的验证
- 但高性能 transport 和真实硬件路径，最终仍然需要带设备的 Linux 服务器或裸机

## 模块级判断

### `mooncake-transfer-engine`

结论：当前机器上不适合本地编译。

原因：

- CMake target 直接链接 `ibverbs`、`numa`
- 源码读取 Infiniband sysfs 和 NUMA 信息
- 即使只想走 `TCP`，当前默认 target 仍然把 RDMA 能力当成基础能力之一

评估：

- 本地阅读和改代码：可以
- 本地成功构建：基本不可行
- 推荐环境：Linux

### `mooncake-store`

结论：当前机器上不适合本地编译。

原因：

- `zstd` 是硬依赖
- `mooncake_master` 直接链接 `ibverbs`
- 若启用更完整能力，还会继续碰到 `io_uring`、`numa`、Linux 文件接口等问题

评估：

- 本地阅读和改代码：可以
- 本地成功构建：基本不可行
- 推荐环境：Linux

### `mooncake-integration`

结论：不能单独作为“轻量 Python 模块”在当前机器上成立。

原因：

- `engine` 绑定直接依赖 `transfer_engine`
- `store` 绑定直接依赖 `mooncake_store`
- `pybind11` submodule 还未初始化

评估：

- 本地阅读 bindings 和 Python API：可以
- 本地构建 Python extension：当前不可行
- 推荐环境：Linux

### `mooncake-wheel`

结论：只能做静态阅读，不能在当前机器上作为完整功能层运行。

原因：

- 多个脚本直接 import `mooncake.engine` 或 `mooncake.store`
- 这些模块本身来自前面的 C++ 编译产物

评估：

- 本地阅读 CLI / Python 入口：可以
- 本地独立运行完整能力：基本不可行

### tests / benchmarks / examples

结论：绝大部分必须迁到 Linux。

原因：

- 它们依赖前面那些本地无法构建的核心模块
- 一部分 benchmark 还显式依赖 `numa`、`io_uring`、RDMA 设备或真实网络拓扑

## 现实可执行的建议

### 当前这台 Mac 最适合承担的角色

建议把当前机器定位成：

- 源码阅读机
- 文档与架构分析机
- 普通代码编辑机
- 轻量静态检查机

不建议把它定位成：

- Mooncake 核心模块本地编译机
- 传输层行为验证机
- 性能测试机

### 下一步最合理的 Linux 验证分层

建议把验证环境拆成两级：

1. Linux 通用构建机
   - 目标：验证 `cmake`、`Transfer Engine`、`Mooncake Store`、Python bindings 是否能完整编过
   - 环境：Ubuntu 22.04+，不一定需要 RDMA / GPU

2. Linux 硬件验证机
   - 目标：验证 RDMA / EFA / NVLink / CUDA / Ascend / CXL 等真实路径
   - 环境：对应硬件齐全的 Linux 服务器或裸机

## 最终判断

如果只用一句话总结：

当前这台 macOS 机器适合继续做 Mooncake 的源码分析、文档整理和代码修改，但不适合作为 `Transfer Engine`、`Mooncake Store`、Python bindings、tests 或高性能 transport 路径的本地编译与运行环境；这些工作至少应迁到 Linux，而涉及 RDMA / GPU / NPU / CXL 的路径还必须使用对应硬件环境。
