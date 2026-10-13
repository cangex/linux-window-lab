# P1：AP 启动基础

P1 将一个已从主 Linux 下线的 AP 转入独立的 x86-64 payload。payload 采用自己的栈、页表、GDT 和 IDT，通过保留 RAM 中的 mailbox 报告实际 APIC ID、启动 generation、阶段和心跳。主 Linux 继续在 CPU 0–3 上运行。

这是一台 QEMU/KVM 实验 VM 内的 AP 启动验证。尚未加载分区 UEFI 或 Windows，不证明裸机兼容性。P1 使用既有 ZDU 早期内存预留和 AP trampoline；payload 由 `request_firmware()` 加载，未通过 kexec-tools 或完整 KHO/ZDU 更新事务加载。现有 `kexec_trylock()` 只用于串行化共享启动设施。

## 固定输入

- Linux 源码与输入文件哈希：[`sources.lock.json`](sources.lock.json)。`apply.py` 修改之前会检查源文件哈希，拒绝未知版本和重复应用。
- 完整内核配置：[`kernel.config`](kernel.config)；构建脚本重新生成配置并逐字比较。
- 实测二进制、源码覆盖层哈希及工具链版本：[`tested-build.json`](tested-build.json)。二进制重建可能因时间、构建计数或编译器不同而变化，不声称逐字可重复。
- payload：[`payload/ap-probe.asm`](payload/ap-probe.asm)，NASM 生成的平坦 64 位代码。
- Linux 接口：[`kernel/lwlab.c`](kernel/lwlab.c)；AP 入口适配由 [`apply.py`](apply.py) 加入冻结源码的 `smpboot.c`。

源码保留原许可证。新增内核和汇编代码采用 GPL-2.0-only。

## 实验资源和交接 ABI

当前是固定的 P1 配置，并非可任意配置的平台管理器。使用 8 vCPU / 16 GiB 的 `lwlab-boot`，两个虚拟插槽各 4 核，分别位于两个 NUMA 节点。CPU 0–3 留在 Linux；4–7 先全部下线，只有 CPU 4 被重新启动。此次 CPU 4 的 APIC ID 为 4。

`zdu_pool=16M@0x180000000` 在 Linux 的早期 memblock 阶段预留 guest physical RAM；主 Linux 分配器不能分配此范围。地址必须结合当前 VM 的 e820 图确认，不能直接用于其他 VM 或裸机。该地址在本实验中属于 NUMA node 0；CPU 4 位于 node 1，因此这是功能配置，非本地内存性能配置。

| 相对 0x180000000 的偏移 | 用途 |
| --- | --- |
| 0x0000 | 88 字节交接结构 |
| 0x1000 | 64 字节 mailbox |
| 0x2000 / 0x3000 / 0x4000 | PML4 / PDPT / PD |
| 0x10000 | 平坦 payload；长度上限 64 KiB |
| 0x100000 | 向低地址增长的私有栈顶 |

所有 ABI 地址均为这台 VM 的 guest physical address。AP trampoline 在 64 位模式下以 RSI 传递交接地址，payload 不返回。私有页表采用 2 MiB 大页，恒等映射包含此区域的 1 GiB 窗口；这不是访问隔离，只在 16 MiB 预留范围内安排 payload 自有数据。低端 trampoline 另由冻结源码的早期启动代码预留。

交接结构按小端布局，`magic=0x313030765041574c`，`version=1`：

| 偏移 | 字段 |
| --- | --- |
| 0 | u64 magic |
| 8 / 12 | u32 version / u32 size=88 |
| 16 | u64 generation（非零） |
| 24 / 28 | u32 Linux CPU 编号 / u32 APIC ID |
| 32 / 40 | u64 base / u64 bytes |
| 48 / 56 | u64 entry / u64 stack |
| 64 / 72 / 80 | u64 cr3 / u64 mailbox / u64 flags |

mailbox：`generation` 在偏移 0；`apic_id` 和 `stage` 在 8、12；u64 `heartbeat/tsc/error/cr3/stack/magic` 依次在 16、24、32、40、48、56。

Linux 在启动前清零整个预留区域并发布新 generation；payload 回写 CPUID 获得的 APIC ID。阶段 1 表示已进入；阶段 2 在换用私有 CR3、栈、GDT、IDT 后发布；阶段 255 表示失败。启动方用 acquire 读取阶段，并校验 generation、APIC ID、magic、CR3、栈与非零心跳。它不会仅凭 IPI 返回成功标记 ready。等待握手期间保持 kexec 串行化；正常握手、payload 异常或超时之后调用原生 AP 启动清理函数，恢复临时 warm-reset 向量。IPI 发送本身失败的清理由既有路径负责。

状态迁移为 `idle → prepared → loaded → start-issued → payload-entered → payload-ready`，异常和超时进入 `failed`。私有 IDT 将可捕获异常记录为错误码 3 并停驻，不做异常恢复，也不识别具体向量。早于 IDT 安装的故障可能仅表现为启动超时。

`flags=0` 正常运行；`1` 在 entered 后停驻以注入超时；`2` 执行 UD2 检查异常记录。心跳采用 PAUSE 循环和 RDTSC，尚未启用 AP 本地定时器、中断处理或其他设备。

## 构建和安装

在 `lwlab-dev` 内，先安装 P0 工具链（包含 gcc、make、binutils、nasm、bc、bison、flex、libssl-dev、libelf-dev、uuid-dev）。从项目仓库执行：

```sh
sh p1/fetch-source.sh /opt/lwlab/src/linux-p1
python3 p1/apply.py /opt/lwlab/src/linux-p1
sh p1/build.sh /opt/lwlab/src/linux-p1 /opt/lwlab/build/p1
sh p1/package.sh /opt/lwlab/src/linux-p1 /opt/lwlab/build/p1 /opt/lwlab/build/p1-package
```

若已有冻结源码 archive，可验证 `sources.lock.json` 的 archive SHA256 后解压到新的目录；不能在已有 NUKA/ZDU 工作树上直接应用覆盖层。

宿主机先以 `python3 p1/provision-boot.py` 从 P0 冷备份派生 `lwlab-boot`。该脚本遇到已有 VM 或 state 目录即停止；使用单独磁盘 overlay、NVRAM、MAC、IP、cloud-init instance 和串口日志。冷备份及其原始 backing image 必须保留。

将开发机上的 `p1-package` 整个目录经宿主机复制到 boot guest 的 `/tmp/p1-install`，将 `install-guest.sh` 复制到 guest，然后在 `lwlab-boot` 中执行：

```sh
sudo sh /tmp/install-guest.sh /tmp/p1-install
sudo systemctl reboot
```

安装脚本保留 `/lib → usr/lib`，不直接把 modules archive 解包至根目录；保留原 Ubuntu 内核的 GRUB 救援入口。内核参数是 `nokaslr no5lvl zdu_pool=16M@0x180000000`，通过 OVMF/GRUB 正常启动，不采用 QEMU `-kernel` 绕过固件。

安装后检查 `uname -r`、`/sys/firmware/efi`、`/sys/kernel/lwlab/status` 和 `dmesg`。期望内核 `6.18.0-rc3-lwlab-p1`，初始 `state=idle`、`started=0`。

## 控制接口与失败恢复

仅 root 可写 `/sys/kernel/lwlab/control`。本配置的 prepare 命令如下（先下线 CPU 4–7；建议直接使用测试脚本）：

```text
prepare 1 4 180000000 1000000 180010000 GENERATION 0
start
```

地址与长度采用十六进制，generation 和 flags 采用十进制。运行状态从 `/sys/kernel/lwlab/status` 读取。`error` 是最近一次 control 请求的负 errno；测试故意拒绝再次启动后，它会为 `-16`，而 payload 仍为 ready。payload 是否异常应看 `state`、`stage` 和 `payload_error`。

启动请求发出后，即使超时也不归还 CPU 或内存。P1 全局禁用该 guest 的 Linux CPU hotplug，确保目标 CPU 不能重新 online。恢复需要正常关闭并重新启动整个 `lwlab-boot`；没有实现独立 AP 回收。不要在这台实验 guest 同时运行其他 ZDU/kexec 资源管理操作。

## 完整验收

在宿主机把 `p1/` 复制为可读目录，执行：

```sh
python3 p1/run-matrix.py --output /data/linux-window-lab/artifacts/p1/validation-NEW
python3 p1/verify-results.py /data/linux-window-lab/artifacts/p1/validation-NEW
python3 p1/capture-environment.py --output /data/linux-window-lab/artifacts/p1/environment-NEW.json
```

runner 只控制 `lwlab-boot`：每轮先正常关机，确认 `shut off` 后再启动。关闭超时不会自动强制断电。默认 10 次正常冷启动（第一次 1800 秒，其余 30 秒），另加 entered 后超时和 UD2 两次冷启动。所有 boot ID 和 generation 必须不同。

guest 在 AP 启动前 5 秒建立 TCP 连接，启动后继续使用同一个连接，逐秒执行文件写入、fsync、回读校验并上报 AP mailbox。宿主机连接后不重连，每十个样本做一次 ping。正常运行要求每个后续样本的心跳递增；TCP 间隙阈值 8 秒用于检测本次实验中的停顿，不是实时性保证或性能结论。

每轮还验证在线 CPU、错误版本、CPU 0、零 generation、畸形命令、越界内存、错误大小、非法入口均被拒绝；启动后再次启动、重新加载、重新 online 均被拒绝。故障注入要求记录正确失败阶段，同时 Linux TCP 与文件 I/O 继续运行。

`verify-results.py` 独立复核 raw stream、时间跨度、身份/上下文、全部错误码、不同 boot ID/generation 和 dmesg 中的内核警告。完整原始流、guest 日志、dmesg 留在服务器；Git 保存筛选后的摘要。

该测试只覆盖指定负载下的连续性，不代表任意 Linux 工作负载、设备或后续 Windows 初始化均无影响。
