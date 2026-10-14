# P6：多核、长稳与独立恢复（进行中）

当前状态见 [进度与证据](../docs/2026-10-14-p6-progress.md)。完整验收条件见
[P6–P8 计划](../docs/p6-p8-plan.md)。本目录包含已测基础工具和**尚未运行验证的恢复原型**；不是 P6 完成声明。

## 工具与运行边界

- `stage.py`：在 P5 固定 Q35 平台上生成 1/2/4 个 Windows CPU 的 MADT、SRAT、DSDT；APIC ID 从 4 开始。额外将 `0x6f000` 停驻页作为 EFI Reserved Memory 预留。
- `apply.py`、`park.asm`、`recovery.inc`：P6 内核覆盖层。`stop` 向 APIC 4–7 发送定向 INIT/SIPI，核验每 CPU nonce 确认，然后屏蔽 NVMe 中断、关闭控制器、清除 bus master、等待事务和复位。失败进入 `failed-retained`；RAM 不返还 Linux。
- `prepare` 要求 generation 严格大于上一代。建议 `max(time.time_ns(), previous+1)`，禁止重用旧代号使旧 fd 复活。停止、清空和读取共用内核锁。
- `cpu-profile.py`、`cpu-probe.py`：从固定 PDB 生成 PRCB 偏移，独立发现内核并读取逐 CPU 标识、执行时间。
- `workload.c`：固定亲和性线程验证内存、NVMe 写入/flush/读回，创建子进程、装卸 DLL；仅在 Windows 独占盘写真值，不创建共享地址辅助页。
- `observe.py`、`clock.c`：有界 JSONL 采样，记录对象身份、读取范围、TSC 和 Linux 单调时钟。新增 `--windows-clock` 选项，使用 PDB 中的共享系统时间结构为语义读取加时间区间；须先重新生成 profile。运行时验证尚未完成。
- `recover.py`：一次分区停止/重建冒烟工具，检查同一 Linux boot ID、停止期间拒绝 open、旧 fd 拒绝、代号重用拒绝和新代独立发现。不能单独替代故障矩阵/逐 CPU 负载/网络连续性验收。
- `setup.ps1`、`console.py`：仅用于普通激活 VM，安装须提升权限。关闭休眠后完整关机，避免离线修改处于休眠状态的 NTFS。QMP 仅用于安装界面，不能充当外部内存读取验收路径。
- `resource-gate.py`：宿主机只读资源采样；只写实验历史文件，不启动或关闭 VM。

## 10 月 15 日续作工具（尚待 VM 验证）

- `windows_clock.py` 从目标页表映射的共享用户页读取 Windows 系统时间，以高低字重读排除撕裂；偏移只从已验证 PDB 生成，不使用猜测偏移。
- `verify-semantics.py` 离线读取独占盘真值，用 Windows 时钟区间筛选稳定样本，核对 generation、进程身份、子进程、DLL 和内核模块；所有请求均进入覆盖率分母，变化窗口和不可用分别计数。默认 50 ms 余量仍须实际校准，运行测试完成前不算 P6 验收。
- `extract-offline.py` 从关闭且未被 QEMU 使用的 P6 磁盘克隆提取 `p6-truth.jsonl`；只读 loop，不修复文件系统。
- `verify-workload.py` 检查指定 workload 实例的逐 CPU/I/O 进展、错误、时长和生命周期计数；它不验证外部语义。
- `guest-probe.py` 和 `run-attempt.py` 采集 Linux 持续 TCP、fsync/readback、I/O 用时与可选外部观察。后者只接受已经启动且 idle 的 r5 Linux，以及 `state-p6/windows.qcow2` 专用克隆；默认采集结束请求关闭外层 VM，仍须单独做冷盘校验。`--keep-running` 仅供后续恢复试验。
- 本地合计 17 项 P6 测试通过；新路径还没有实机数据。PDB 时钟类型需在 dev 资源准入后重新生成。

共享页与时间字段依据微软的 [!kuser 文档](https://learn.microsoft.com/en-us/windows-hardware/drivers/debuggercmds/-kuser)、[KUSER_SHARED_DATA 定义](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntddk/ns-ntddk-kuser_shared_data) 和 [系统时间说明](https://learn.microsoft.com/en-us/windows/win32/sysinfo/system-time)。TSC 保留为诊断数据，验收器使用 Windows 系统时间区间，并核查其推进与 Linux 单调时钟一致。

## 资源准入（试跑规则 v1）

每 60 秒采样；连续 600 秒所有采样通过、相邻采样间隔不超过 90 秒：

| 项目 | 门限 |
| --- | --- |
| MemAvailable | ≥128 GiB |
| MemFree | ≥64 GiB |
| 每 NUMA 节点 MemFree | ≥4 GiB |
| memory PSI some avg10 | <1% |
| 实验卷可用磁盘 | ≥80 GiB |

缺失、过期、压力事件会阻止准入；不能用整机空闲掩盖单节点耗尽。
当前门限用于恢复试跑，正式长稳前还需冻结资源分配/矩阵/停止规则。
持续压力下暂停新增负载；构建 VM 配置为 8 GiB、内存跨 0–7 节点交错、构建并发 2；构建已结束，VM 已关机。

```sh
python3 p6/resource-gate.py --history artifacts/p6/resource-history.jsonl
python3 -m unittest discover -s p6 -p 'test*.py'
python3 -m unittest discover -s p5 -p 'test*.py'
```

gate 返回 0 表示准入，75 表示等待；一次通过采样不构成连续窗口。取窗口起点前最近一个采样作为边界，窗口外更早的失败不延长等待；窗口内任何失败、缺口或过期仍拒绝。

## 构建与部署

使用已有 P5 源码/EDK2 输入，从干净内核解包目录开始：

```sh
python3 p6/stage.py /opt/lwlab/build/p6-stage --disk INPUT_DISK --cpus 4
python3 p6/apply.py /opt/lwlab/src/linux-p6 /opt/lwlab/build/p6-stage
# 将 P5 .config 复制到新的 build 目录；LOCALVERSION 改为 -lwlab-p6。
make -C /opt/lwlab/src/linux-p6 O=/opt/lwlab/build/p6-kernel olddefconfig
make -C /opt/lwlab/src/linux-p6 O=/opt/lwlab/build/p6-kernel -j2 bzImage modules
# 将生成的 build-uefi.sh 内并发也设为 2，再构建固件、运行 pack/verify。
# 使用 p3/package.sh 打包，p6/install-guest.sh 仅在 lwlab-boot 安装。
x86_64-w64-mingw32-gcc -O2 -Wall -Wextra -Werror -static p6/workload.c -o lwtruth.exe
cc -shared -fPIC -O2 -Wall -Wextra -Werror p6/clock.c -o p6/clock.so
```

**不要将旧四核冒烟固件用于恢复测试**：该固件没有停驻页预留。
服务器最终部署候选必须为 `p6-package-r5` 加 `p6-firmware-r4`（后者已预留停驻页），并核验 SHA256SUMS。
初始 r4 内核缺少最后的 generation 单调约束与 ICR 中断保护，只作构建中间产物。
最终候选已编译并校验，复制在宿主 `artifacts/p6/p6-package-r5/`；尚待实际 VM 验证。
修复后的 `p6-stage-r5/verify-layout.py` 已核验完整固件，仍保留 `p6-firmware-r4` 目录名，因为固件字节未修改。

## 等待恢复后的执行次序

1. 确认资源连续通过；读取构建日志，从宿主 `artifacts/p6/p6-package-r5/` 检查 r5 包和磁盘余量；dev 已关闭，不必启动它读取日志。
2. 仅启动 `lwlab-p6-activation`。使用管理员 PowerShell 运行 setup，验证新负载、关闭休眠、完整关机。确认 NTFS 可安全离线读取，保存许可和真值。不得强制清除休眠状态写盘。
3. 从关闭的激活副本创建独立 P6 克隆，保留 P5 基线不变。安装 P6 包，记录新的内核/固件/磁盘/profile 哈希。
4. 先 4 CPU 短试跑并核对每 CPU 负载，再完成离线真值时序验证；基础稳定后试单次 `recover.py`。它需要正在运行的 Windows 分区，停止失败即保留现场。
5. 按计划完成 1/2/4 CPU 冷启动矩阵、2 小时、24 小时长稳及独立故障矩阵。长测试由可恢复的后台任务执行，跟进任务检查真实日志，不能用预定时长冒充实际通过。

所有破坏性故障只在项目 VM 克隆内；不重启物理宿主机，不修改业务进程，不开始 P7 裸机改造。
