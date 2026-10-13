# 2026-10-13 实验准备结果

结论：**P0 开发环境验收通过**。`lwlab-dev` 已启动并保持运行，可用于后续 multikernel 启动适配开发。尚未进行 Linux–Windows 并行启动。

## 固定环境

- 宿主机：Ubuntu 24.04，AMD EPYC 7742，KVM `enabled=true`。
- QEMU：`1:8.2.2+ds-0ubuntu1.18`。
- libvirt：`10.0.0-2ubuntu8.19`。
- OVMF：`2024.02-2ubuntu0.10`，4 MiB，Secure Boot 关闭。
- 虚拟机：8 vCPU / 16 GiB，2 个虚拟 NUMA 节点，Q35 8.2。
- Guest：Ubuntu 24.04，`6.8.0-142-generic`，通过 UEFI 启动。
- Ubuntu 镜像 SHA256：`6a81c37564db9b1ee84e141922625e1d7c5b389b99bb3c572e0243607d5bb4d2`，与官方下载的 SHA256SUMS 一致。
- Linux 系统盘：80 GiB qcow2 overlay。Windows 预留盘：64 GiB qcow2，空白且未挂接。

## 已执行检查

| 检查 | 结果 |
| --- | --- |
| QEMU 使用 KVM | 通过 `query-kvm` 确认 |
| Guest UEFI | `/sys/firmware/efi` 存在 |
| CPU / NUMA | `0-7` / `0-1` |
| cloud-init | 完成，无错误 |
| SSH / NAT 外网 | 登录成功；通过 guest apt 下载构建依赖 |
| 开发工具 | GCC、Make、binutils、CMake、Ninja、NASM、IASL、DTC、pahole 等可用 |
| 编译运行 | `-Wall -Wextra -Werror` 编译 C 程序并成功运行 |
| 存储 | 写入、fsync、回读 SHA256 一致 |
| Guest agent | active |
| 正常关机与冷启动 | 完成；重启后 readiness 再次通过 |
| 防覆盖 | 再次运行 provision 拒绝覆盖已有 VM |

这些检查证明开发环境可用，不代表 EDK2 payload 或 multikernel 内核已构建通过，也不代表 Windows 能启动。

## 留存材料

宿主机 `/data/linux-window-lab/`：

- `artifacts/guest-readiness.json`：重启后的验收结果。
- `artifacts/kvm.json`、`domain-live.xml`、`domain-info.txt`、`network-info.txt`：运行配置与加速状态。
- `artifacts/serial0.log`、`serial1.log`：双串口日志，由 root 管理。
- `config/`：libvirt XML 和 cloud-init 配置。
- `baselines/pre-multikernel/`：正常关机后复制的系统盘、Windows 空盘、NVRAM、域 XML 和 SHA256。依赖原始 Ubuntu backing image。

Guest `/opt/lwlab/results/`：`acpi-baseline.txt`、`iomem-baseline.txt`、`cpu-baseline.txt`、`pci-baseline.txt`。这些平台基线在冷备份后的复验阶段采集。

## 下一阶段入口

1. 固定主 Linux multikernel 源码提交和构建配置，先跑指定 AP 的最小 payload。
2. 同步测量主 Linux 心跳、网络和磁盘连续性。
3. 构建分区 UEFI；独立验证其内存和 ACPI 描述，不复用整机 OVMF 内存状态。
4. 按 `winpe.md` 制作 Windows 11 x64 WinPE，记录实际 build、补丁和镜像 SHA256。

未设置宿主机 CPU 独占和 NUMA 绑定，尚不开展性能比较。现阶段所有 guest CPU 和 RAM 仍由 Ubuntu 管理。
