# P3：WinPE 与 Linux 在同一 VM 内并行运行

P3 将 P2 的分区 EFI 自检替换为官方 WinPE 启动链。Linux 在 CPU 0–3 保持运行，CPU 4 执行独立 EDK2 DXE、Windows Boot Manager 和 WinPE；CPU 5–7 保持下线。**外层 QEMU/KVM 是实验机器，分区内部没有新增 Windows VM 或常驻 hypervisor。** 裸机、多核 Windows 和完整 Windows 安装属于后续阶段。

验收结果见 [P3 报告](../docs/2026-10-14-p3.md)。所有大型镜像、微软二进制、调试符号和完整运行日志保留在实验服务器，不提交 Git。

## 固定平台与资源

当前只支持 `lwlab-boot` 的 Q35 8.2 / 8 vCPU / 16 GiB 配置。`partition.json` 记录资源布局；`stage.py` 从已验收的 P2 构建脚手架生成 P3 overlay，不修改 P1/P2。此配置不是可任意迁移到另一台机器的通用分区描述器。

| 资源 | P3 分配与约束 |
| --- | --- |
| 主 RAM | `0x10000000..0x6fffffff`，1536 MiB，Linux `zdu_pool` 预留 |
| 低端 RAM | `0x00100000..0x00ffffff`，15 MiB，供 HAL 早期低地址分配 |
| 实模式启动 RAM | `0x00050000..0x0006ffff`，128 KiB，供 Windows startup stub；与 Linux AP trampoline 分离 |
| RAM GOP | `0x10200000..0x104fffff`，1024×768 BGRX，位于分区保留区，不使用 Linux VGA/PCI |
| IOAPIC | `0xfec00000`，ID 0，GSI base 0，Windows 独占；Linux `noapic` |
| HPET | `0xfed00000`，VM 必须启用；Windows 使用，Linux `hpet=disable` |
| LAPIC | 当前 AP 本地寄存器，`0xfee00000` |
| 串口 | Linux COM1；分区 UEFI COM2，`0x2f8`；本版 WinPE 未提供可用 COM 驱动 |
| 设备 | 启动使用预加载只读 GPT/FAT32 内存盘；没有 PCI 总线、物理磁盘或网卡分配给 WinPE |

主 RAM 不能简单放在 4 GiB 以上：本轮验证使用的 WinPE 早期分配路径还要求低于 16 MiB 和 1 MiB 的 RAM。两块低端区域必须在 Linux 初始化分配器前预留。内核检查其原始 E820 类型为 RAM、当前类型为 Reserved、没有 System RAM 冲突，并申请资源所有权后才映射和清零。

Linux 启动参数：

```text
console=tty0 console=ttyS0,115200n8 nokaslr no5lvl zdu_pool=1536M@0x10000000 memmap=15M$1M memmap=128K$0x50000 noapic hpet=disable 8250.nr_uarts=1 no_ipi_broadcast=1
```

`install-guest.sh` 已处理 GRUB 中 `$` 的转义；以上是 `/proc/cmdline` 应看到的值。Linux 禁用 8250 PNP，以免再次认领 COM2。`no_ipi_broadcast=1` 防止 shorthand IPI 到达已交给 Windows 的 AP。Linux 的外部中断使用 PIC/MSI/MSI-X，IOAPIC 与 HPET 不再由两个系统共同初始化。

## 引导适配

- 复用冻结的 Linux AP 启动代码、EDK2 DXE core、内存/协议/事件/镜像服务、Runtime core、模拟变量和 FAT 驱动。加入 GPT 分区驱动和专属 RAM GOP。
- 独立 HOB 只提供三段分区 RAM。RSDP/XSDT 指向 MADT、FADT/DSDT、SRAT 和 HPET；MADT 只暴露 APIC ID 4。FADT 使用 hardware-reduced 模式，不提供整机 PM/SMI/RTC/复位寄存器。
- Handoff ABI 为 3（96 字节），mailbox 为 128 字节。ABI 3 中旧 `Flags` 槽承载 Linux 交接时的 UTC 秒数；控制命令末尾 flags 参数仍必须为 0。运行时时间由该 UTC 基准与 TSC 推算，不调用宿主固件或共享 RTC。
- `GetTime` 返回有效日期；SetTime/唤醒不支持。变量仍只在分区 RAM 中保存，不提供持久化或认证变量。未实现分区 Secure Boot 验证。
- GOP 具有独立 DevicePath，WinPE 才能建立图形控制台。底层像素缓冲由 Linux 预留，UEFI 和 Windows 分配器不会将其当作自由内存。
- BDS 从 GPT ESP 加载 `\\EFI\\Microsoft\\Boot\\bootmgfw.efi`。Boot Manager/加载器执行微软原始代码；只向 WIM 增加测试程序和修改 `startnet.cmd`，不补丁修改 Windows 内核。
- `state=firmware-ready` / `stage=2` 只表示固件准备完成；`stage=3 phase=21` 只表示 `ExitBootServices` 成功。WinPE 用户态必须由独立证据确认。

UEFI `ResetSystem` 仅记录请求并停驻 AP；不能据此承诺 Windows 所有直接硬件复位都被拦截。每次实验通过正常关闭、重新启动整台 `lwlab-boot` 恢复资源，不做 Windows 分区单独回收。

## 构建与安装

在 x86-64 Ubuntu 24.04 构建 VM 安装 P1/P2 工具链及：

```sh
sudo apt-get install cabextract msitools wimtools mtools dosfstools mingw-w64 nasm acpica-tools
python3 p3/fetch-media.py /opt/lwlab/build/p3-adk
python3 p3/make-media.py /opt/lwlab/build/p3-adk /opt/lwlab/build/p3-media
python3 p3/wrap-gpt.py /opt/lwlab/build/p3-media/winpe-fat.img /opt/lwlab/build/winpe-gpt.img
python3 p3/stage.py /opt/lwlab/build/p3-stage --disk /opt/lwlab/build/winpe-gpt.img
# 用 p2/fetch-edk2.sh 获取 sources.lock.json 指定的 EDK2 和子模块
bash /opt/lwlab/build/p3-stage/build-uefi.sh /opt/lwlab/src/edk2-p3 /opt/lwlab/build/p3-firmware
# 将 P1 锁定源码归档解压到全新 linux-p3（归档没有顶层目录）
python3 p3/apply.py /opt/lwlab/src/linux-p3 /opt/lwlab/build/p3-stage
sh p3/build-kernel.sh /opt/lwlab/src/linux-p3 /opt/lwlab/build/p3-kernel
sh p3/package.sh /opt/lwlab/src/linux-p3 /opt/lwlab/build/p3-kernel /opt/lwlab/build/p3-package /opt/lwlab/build/p3-firmware
```

`make-media.py` 校验固定微软输入，保留原始 WIM，只操作实验副本。安装包版本不等于 WIM 内系统版本。详细制作与哈希说明见 [WinPE 文档](../docs/winpe.md)。构建记录包括源版本、编译器、配置和各层产物哈希；没有承诺 PE/WIM/内核按位可复现。

生成脚本完成两组独立检查：继承的 `verify-layout.py` 检查资产哈希、HOB 保留区、不重叠布局和 ACPI 校验和；`verify-image.py` 检查实际打包字节中的 MADT/FADT/HPET/SRAT、GOP 保留区、GPT 两份表和 ESP 边界。

普通镜像基线（宿主机）：

```sh
python3 p3/provision-baseline.py --name lwlab-winpe-baseline --image /data/linux-window-lab/images/winpe/winpe-gpt.img
```

从 idle P2 升级：将包内容复制到宿主机 `artifacts/p3/package/`，再运行 `python3 p3/prepare-boot-vm.py`。该脚本正常关闭实验 VM、冷备份 P2 磁盘/NVRAM/XML、启用 VM HPET，并安装 P3。已有备份时默认拒绝覆盖；`--resume-saved-p2` 仅用于已有冷备份且当前仍为 idle P2 的中断恢复。P3 安装不能作为无条件重入脚本使用。

当前已安装的 P3 实验机直接运行下面的验收命令。正式产物包保留在宿主机 `artifacts/p3/package-final/`，不会覆盖较早失败实验的产物。

## 双系统验收

宿主机（需要免交互 sudo、既有实验密钥和 `lwlab-boot`）：

```sh
python3 p3/run-attempt.py /data/linux-window-lab/artifacts/p3/firmware-visual.bin trial-01 --seconds 90
python3 p3/run-matrix.py /data/linux-window-lab/artifacts/p3/firmware-visual.bin --prefix acceptance
python3 -m unittest discover -s p3/tests -v
```

每轮重新冷启动同一台实验 VM，验证初始 idle 和新 Linux boot ID；记录镜像/内核/配置哈希、generation、UEFI 日志、CPU 寄存器、VM XML、中断状态、dmesg 和两套连续性流。启动失败不重新利用 AP 内存。

Linux 每秒执行文件写入、fsync、读回校验，通过启动前建立的一条 TCP 连接汇报；宿主机每十个样本 ping 一次。验收要求连接没有重连、序号连续、无 ping 失败、最大消息间隔小于 8 秒、kernel taint 为 0。

WinPE 的 `startnet.cmd` 经 `wpeinit` 启动 `lwprobe.exe`。程序每秒在命令行打印 nonce/序号/PID/tick，并通过 GDI 在专属帧缓冲绘制一条 48 字节记录：magic、nonce、序号、tick、PID、版本、CRC32 及其反码。宿主机 QMP 每两秒读取固定 GOP 区，验证颜色、CRC、身份一致和序号/tick 进展，拒绝过期画面；不暂停 VM。有效进展间隔必须小于 8 秒，系统 tick 与宿主时间需一致，首个有效记录须在 90 秒内出现。

这是一条**合作的用户态存活遥测路径**，不是 P4 的 Linux 外部读取后端，也不证明任意 Windows 对象的定位、权限路径或一致性。GOP 截图另外保留命令提示符和测试程序的可见证据。COM 驱动未就绪不作为串口用户态成功上报。

矩阵运行 10 次冷启动；首轮启动后观察 1900 秒，并要求 Linux 与有效 WinPE 心跳重叠至少 1800 秒；其余每轮观察 90 秒。额外要求 10 个 Linux boot ID、generation、WinPE nonce 各自唯一，内核和固件哈希相同。单轮 `result.json` 的 pass 只代表 Linux；`coexistence.json` 才合并双系统证据；最终以 `acceptance-summary.json` 为准。
