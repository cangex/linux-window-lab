# P2：分区 UEFI 与平台描述

P2 在 `lwlab-boot` 的 Linux 保持运行时，将 CPU 4 交给独立 EDK2 DXE 环境。它复用 P1 的定点 AP 启动机制，替换 handoff、私有页表与 payload。**此阶段测试 EFI 服务，不启动 Windows，也不宣称完整 UEFI/Windows 平台兼容。**

## 固定平台

`partition.json` 是资源布局来源，`generate.py` 生成 C/汇编常量，`pack.py` 生成 PI HOB 和 ACPI。当前仅支持固定的 QEMU q35 / 8 vCPU / 16 GiB 配置：Linux 使用 CPU 0–3，CPU 4 运行 UEFI，CPU 5–7 下线停驻。ACPI 只暴露 APIC ID 4，不提供 MP Services，不发送广播 IPI。

- 内存：`0x40000000..0x4fffffff`，256 MiB，通过 `zdu_pool` 从 Linux 分配器中预留。
- CPU 4 属于原 VM NUMA domain 1；1 GiB 地址处内存属于 domain 0，SRAT 保留这种远端内存关系。
- 页表：身份映射 0–4 GiB，另将 1–2 GiB 映射到 5–6 GiB，供 runtime 虚拟地址验证。映射可达范围大于资源所有权范围；本项目不以安全隔离为目标。
- 缓存：RAM 使用 WB，LAPIC 所在 2 MiB 页使用 UC；无 EPT/NPT 新增隔离层。
- 串口：Linux COM1；分区 COM2 `0x2f8` 轮询输出。Linux 禁用 `CONFIG_SERIAL_8250_PNP` 并用 `8250.nr_uarts=1` 固定只注册 COM1；单独设置 nr_uarts 不足以阻止 PNP 后续注册或改变 tty 编号。
- Linux IPI：必须设置 `no_ipi_broadcast=1`，让常规 IPI 根据在线 CPU 集合发送。仅将 CPU 下线不能阻止 shorthand 广播到达已移交 AP。
- 定时器：仅操作当前 AP 的 LAPIC；不触碰 HPET、PIT、RTC、IOAPIC 或中断重映射器。
- 存储：预加载只读 FAT12 内存盘，使用 EDK2 DiskIo/FAT 驱动。无 PCI、物理磁盘或网络设备。

## 固件组成与限制

使用锁定版本 EDK2 的真实 DXE core、句柄/协议数据库、内存与事件服务、PE/COFF 加载器、Runtime core、变量服务及 FAT 驱动。自定义 bootstrap 直接向 DXE core 传递 PI HOB；未启动第二套 OVMF SEC/PEI，也不恢复主 Linux 已结束的 Boot Services。

`LwCpuDxe` 提供 CPU arch 和 LAPIC Timer arch；`LwPlatformDxe` 提供 ACPI 和只读 BlockIo；`LwBdsDxe` 从内存盘加载自检应用；`LwRuntimeDxe` 提供明确受限的时间/复位行为。DSC/FDF 是驱动白名单。16550 库的 PCI 设备表以 `0xff` 终止，使用固定串口地址，不执行 PCI 配置访问；没有 PCI bus/root bridge 驱动。

| 服务 | 当前行为 |
| --- | --- |
| 内存、协议、事件、镜像、FAT 文件读取 | EDK2 实现，自检覆盖实际调用 |
| 变量 | 内存模拟存储；跨 ExitBootServices / 虚拟地址转换保留，冷启动不持久化；无认证变量支持 |
| 时间与唤醒 | 返回 `EFI_UNSUPPORTED`，不读取整机 RTC |
| ResetSystem | 记录失败并停驻分区 AP，不操作整机复位寄存器；不代表能阻止以后 Windows 的直接硬件复位 |
| Capsule | 上游 Null Capsule 后端，不支持更新 |
| 内存属性改变 | 仅接受当前 WB 映射可满足的请求，不支持 NX/RO 重映射 |
| 控制台/GOP、PCI、SMM、MP Services | 未提供；调试通过专用串口 |

ACPI 包括独立 RSDP/XSDT、MADT、FADT/DSDT、SRAT。FADT 设置 hardware-reduced，没有全局 PM/SMI/RTC/复位寄存器。该表集用于 P2 EFI 测试；Windows 的电源/中断/设备需求须在 P3 验证并扩展。

## 构建

在 Ubuntu x86-64 构建 VM 安装 P1 工具链以及 `nasm acpica-tools dosfstools mtools uuid-dev`。源码与子模块版本见 `sources.lock.json`；所有大型产物放在 Git 忽略的 `artifacts/` 或 `/opt/lwlab/build/`。

```sh
p2/fetch-edk2.sh /opt/lwlab/src/edk2-p2
python3 p2/generate.py
p2/build-uefi.sh /opt/lwlab/src/edk2-p2 /opt/lwlab/build/p2-firmware
python3 p2/verify-layout.py /opt/lwlab/build/p2-firmware
# 将 P1 锁定的 Linux 源码归档解压到一个全新目录（归档无顶层目录）
python3 p2/apply.py /opt/lwlab/src/linux-p2-clean
p2/build-kernel.sh /opt/lwlab/src/linux-p2-clean /opt/lwlab/build/p2-kernel
p2/package.sh /opt/lwlab/src/linux-p2-clean /opt/lwlab/build/p2-kernel /opt/lwlab/build/p2-package
```

`verify-layout.py` 独立检查打包后的资产哈希、不重叠地址、ACPI 校验和、HOB 资源与保留区域。UEFI 使用 handoff v2（96 字节）和 mailbox（128 字节），不能与 P1 固件/内核混用。

## 安装与运行

仅在 `lwlab-boot` 内执行 `sudo sh p2/install-guest.sh /tmp/p2-install`；目录包含内核、配置、System.map、模块包和 partition.bin。安装保留 P1/stock 内核，但 GRUB 全局命令行已改为 P2；回退 P1 时需恢复 P1 的 `zdu_pool=16M@0x180000000`。

主机执行：

```sh
python3 p2/run-matrix.py --output /data/linux-window-lab/artifacts/p2/validation
```

默认十次冷启动，第一轮在 EFI 完成后持续 300 秒，其余每轮 30 秒。每轮先建立 TCP 连接，再异步启动 AP；Linux 每秒 fsync 和读回文件、经同一 TCP 连接报告结果。记录启动 ID、心跳、最大消息间隔、ping、taint 与 dmesg。启动失败后不回收分区，正常关机再启动实验 VM。

九项 EFI 检查对应 `checks=0x1ff`：CPU/镜像位置、ACPI、内存与越界拒绝、文件、子镜像、定时事件、变量、ExitBootServices、虚拟地址转换后的变量读写。`stage=2 phase=9` 表示全部通过；`stage=255` 的 `failed_case` 定位源代码检查点；未分配的外部中断报告 `0x280+vector`。定时自检等待 100 次周期事件，覆盖约两秒的中断运行窗口。内核需同时验证 generation/APIC/CR3/初始栈/检查位才接受成功。`error` 是最近一次控制命令的 errno；拒绝重复启动测试后它为 `-16`，与仍为零的 `payload_error` 含义不同。

虚拟地址测试保留身份映射，并确认转换后的 GetVariable 函数指针位于 `+4 GiB` 别名范围。它验证真实 runtime relocation 与调用，不证明撤销全部物理别名后仍无残留引用。完整页表切换与 Windows runtime 策略留待 P3。
