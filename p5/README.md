# P5：完整 Windows、独占 NVMe 和外部语义解析

本阶段固定 QEMU 8.2 Q35、P3 的 Linux/EDK2 源码、Windows 11 Enterprise
LTSC 2024 Evaluation x64 **26100.1742**。外层 QEMU 是实验机器；其内部由
主 Linux 与单 AP Windows 直接分别运行，没有新增内层 Windows 虚拟机。

## 平台与所有权

Linux 保留 CPU 0–3，Windows 使用 APIC 4，CPU 5–7 停驻。Windows RAM 为
原 P3 的三段 RAM 加 `0x280000000..0x3ffffffff` 的 6 GiB；后者通过
`memmap=6G$10G` 排除出 Linux 分配器，再核对原始 e820 类型并建立 WB 映射。
新增 RAM 的启动映射使用 1 GiB 页，启动前检查 CPU 的相应能力。

`pxb-pcie` 建立独占 PCI 子树：总线 128 上的根端口、总线 129 的 NVMe
端点。Linux 早期绑定 `pci-stub`，在启动 Windows 前解除该根端口的
`pcieport` 服务驱动，并核对实际 BAR 和桥窗口。UEFI 用 ECAM 直接访问
这一个端点，提供有限的 PCI I/O 协议，交给未修改的 EDK2 NvmExpressDxe。
不扫描 Linux 的其他 PCI 总线，也不通过 Linux 文件或块设备接口代理 I/O。

ACPI 中 `_BBN`、`_CRS`、MCFG、根端口当前窗口与设备 BAR 必须一致。
特别是根端口的 `0x383000000000..0x3837ffffffff` 预取窗口虽然没有当前
NVMe BAR 落在其中，仍是该独占桥的资源，必须描述。遗漏它会使 Windows
根端口发生资源冲突、阻断子设备枚举并报 `INACCESSIBLE_BOOT_DEVICE`。
这段地址是 PCI MMIO 窗口，不是额外分配了 32 GiB RAM。

P5 保留 P3 的 IOAPIC/HPET/COM1/COM2 协调、RAM GOP 和 ABI 3 loader。
正式 Windows 系统盘在 64 GiB 专属 NVMe 上；RAM WinPE 仅用于平台冒烟。
`stage.py --ram-smoke` 显式选择 RAM 介质，默认从 NVMe ESP 启动。
所有固件构建先清理平台对象，避免复制不同覆盖层时源文件旧 mtime 导致
错误复用另一种启动变体的对象文件。

## 解析与真值

`observer.py` 只经主 Linux 的 `/dev/lwobserve` 读取 Windows RAM。
P5 后端 ABI 2 返回四段 RAM；generation、范围及只读限制沿用 P4。

1. 扫描匹配版本的驻留内核 PE，再寻找 System EPROCESS 候选。
2. 验证候选 CR3 的页表、内核虚拟地址映射、PDB RSDS GUID/age，及
   `PsInitialSystemProcess` 指针与物理对象的关联；辅助程序不提供启动定位。
3. 遍历进程链表和内核模块链表；对选定原生 x64 测试进程，经 PEB/Ldr
   遍历用户模块。使用 generation、PID、CreateTime 和 EPROCESS 地址标记身份。
4. 页表处理 4 KiB、2 MiB、1 GiB 页，跨页分段读取；读取后复查页表项。
   链表检查前后链接和遍历后链接。不驻留、链表变化或身份变化返回不可用，
   不补造对象，也不宣称跨对象原子快照。进程短名保留 EPROCESS 的 15 字节限制。

`profile.py` 从匹配微软 PDB 的类型和公共符号生成偏移。公共符号 PDB 的
Info age 可能因剥离变化，因此同时记录它，匹配时核对 **GUID 与 DBI age**
对应可执行文件 RSDS。提交的 profile 包含 PE/PDB 哈希、GUID、类型来源、
工具版本及微软符号 URL，不提交 Windows 二进制或 PDB。

`truth.c` 在 SYSTEM 测试进程中核对已知 PID/CreateTime、内核基址、测试
子进程及 DLL 地址，另外循环执行文件写入、FlushFileBuffers 和读回校验。
已知真值页在 90 秒后撤销并释放。新的 Linux 观察进程随后重新扫描和启动
解析，不读取辅助页、不接收之前的 CR3/对象地址；测试进程继续创建/退出
`lwchild.exe`，并装卸 `lwlifecycle.dll`。这里验证的是选定对象，不把输出
完整进程/驱动列表等同于所有字段均已获得独立真值验证。

## 构建与复现

在已有 P3/P4 构建环境上执行，所有输出目录使用新名称：

```sh
# 宿主机：固定官方评估镜像，按 range/ETag 校验并记录 SHA256。
python3 p5/fetch-media.py /data/linux-window-lab/images/windows-ltsc
# 开发 VM：以 P3 官方 ADK WinPE 加入自动部署和测试程序。
python3 p5/make-installer.py /opt/lwlab/build/p3-media-v3 /opt/lwlab/build/p5-installer
python3 p5/stage.py /opt/lwlab/build/p5-stage \
  --disk /opt/lwlab/build/p4-winpe-gpt.img --platform p5/platform.json
bash /opt/lwlab/build/p5-stage/build-uefi.sh /opt/lwlab/src/edk2-p3 /opt/lwlab/build/p5-firmware
# Linux source 从 P3 锁定的原始 archive 重新解包。
python3 p5/apply.py /opt/lwlab/src/linux-p5 /opt/lwlab/build/p5-stage
mkdir -p /opt/lwlab/build/p5-kernel
cp p2/kernel.config /opt/lwlab/build/p5-kernel/.config
/opt/lwlab/src/linux-p5/scripts/config --file /opt/lwlab/build/p5-kernel/.config \
  --set-str LOCALVERSION '-lwlab-p5' -e PCI_STUB
make -C /opt/lwlab/src/linux-p5 O=/opt/lwlab/build/p5-kernel olddefconfig
make -C /opt/lwlab/src/linux-p5 O=/opt/lwlab/build/p5-kernel -j8 bzImage modules
sh p3/package.sh /opt/lwlab/src/linux-p5 /opt/lwlab/build/p5-kernel \
  /opt/lwlab/build/p5-package /opt/lwlab/build/p5-firmware
python3 -m unittest discover -s p5 -p 'test_*.py'
```

`prepare-platform.py` 在宿主机冷保存 P4 并增加试验 PCI 子树；随后通过
`install-guest.sh` 在 `lwlab-boot` 安装 P5 包，重启核对资源。安装器必须
只接受序列号 `LWLABP5INSTALL`、容量 64 GiB、首扇区为空的唯一 NVMe。
`provision-installer.py` 建立普通 OVMF 安装 VM；部署完成关机后移除 WinPE
磁盘和 ISO，启动完整 Windows 完成首次配置，再使用 `shutdown /s /t 0`
完整关机。冷基线保持关闭，`attach-windows.py` 从其创建共存试验克隆。

自动部署文件仅在构建目录生成随机实验账户密码，不能提交该目录。
普通安装 VM 与使用 QEMU 命令行增加设备的实验 VM 单独关闭 AppArmor
域标签以允许该额外磁盘路径；没有修改宿主机全局 AppArmor 配置。
这是当前 libvirt 部署实现的限制，未来可改为显式域访问规则。

从官方 install.wim 提取 `Windows/System32/ntoskrnl.exe`，用
`python3 p5/profile.py KERNEL OUTPUT` 生成并核对对应 profile；需要
`llvm-pdbutil` 或 `llvm-pdbutil-18`。正式 harness：

```sh
python3 p5/stage-tools.py /data/linux-window-lab/artifacts/p5/full-tools --full
python3 /data/linux-window-lab/artifacts/p5/full-tools/run-attempt.py \
  FIRMWARE/partition.bin NAME --seconds 400 --minimum-seconds 300
```

每次正式尝试先归档上一份 Windows 克隆，再从同一冷基线创建新克隆。
这样既保留磁盘证据，也避免失败启动、自动恢复和未协调断电污染下一次。
这一操作只针对 `state-p5/windows.qcow2`；不能把其他工作磁盘放在该路径。

`verify-full.py` 必须同时确认 Linux 连续性、固定 Windows 内核、内部真值
匹配、独立启动解析、不同子进程身份、进程消失、DLL 加载/卸载及旧
generation 拒绝。`crash-diagnose.py` 是 AP 失败停驻后的 **QMP 诊断**，
其结果不能作为 Linux 只读观察能力的验收数据。

停机后再读取该轮磁盘上的真值日志，对独立观察进行第二次核对：

```sh
# 宿主机；DISK 必须是已停止使用的该轮克隆，RAW/LOG 使用不存在的路径。
sudo python3 p5/extract-offline.py DISK.qcow2 RAW.raw ATTEMPT/offline-truth.jsonl
sudo chown "$(id -un):$(id -gn)" ATTEMPT/offline-truth.jsonl
python3 p5/verify-offline.py ATTEMPT
```

提取时保持 QEMU 磁盘锁，不挂载或修复文件系统。核对只接受采样时间前后
两秒内真值保持稳定、日志间隔不超过两秒的窗口，以避开遍历耗时、两个
系统时钟差异和进程/DLL 转换。此附加检查要求至少 20 个稳定样本匹配、
零稳定窗口不匹配，并覆盖子进程消失、两个子进程身份和 DLL 装卸。
转换窗口如实计为排除；不能把它们算作正确样本。

## 边界

当前是单 Windows CPU、固定 build、固定 QEMU 平台的短时实验。完整 Windows
使用官方评估介质，界面显示许可证过期；没有激活或时钟绕过。P6 长时间
实验需可持续使用的系统镜像。没有实现 Windows 独立重启、动态资源回收、
任意对象一致快照、文件系统在线双写、多版本解析或裸机兼容性验证。
