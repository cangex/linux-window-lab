# Linux–Windows multikernel lab

目标：Linux 持续运行，在划分的 CPU、内存和设备资源上启动 Windows，并由 Linux 从外部读取和解析 Windows 数据。项目不以两系统间的安全隔离为验收目标。

当前阶段是 **QEMU/KVM + OVMF 实验环境准备**。现有脚本创建普通 Ubuntu 开发 VM；尚未实现分区 UEFI、Windows 并行启动或 Windows 数据读取。

2026-10-13 的服务器环境已通过 P0 验收，详见 [准备结果](docs/2026-10-13-preparation.md)。

## 实验环境

| 项目 | 配置 |
| --- | --- |
| VM | `lwlab-dev`，x86-64 Q35 8.2，KVM |
| 固件 | OVMF 4 MiB，独立 NVRAM，Secure Boot 关闭 |
| CPU / 内存 | 8 vCPU，16 GiB，两个虚拟 NUMA 节点，各 4 vCPU / 8 GiB |
| 系统 | Ubuntu 24.04 cloud image，UEFI 启动 |
| 存储 | 80 GiB Linux qcow2 overlay；64 GiB Windows 空白盘预留，暂不挂接 |
| 网络 | `lwlab-net` NAT，`192.168.231.0/24`，VM `192.168.231.10` |
| 控制台 | 两个串口；VNC 仅监听宿主机回环地址 |
| 数据目录 | 宿主机 `/data/linux-window-lab` |

虚拟 NUMA 拓扑用于早期功能实验，尚未设置宿主机 CPU 独占或 NUMA 内存绑定，因此不能直接用于性能结论。当前 Linux 可见全部 VM 资源；4+4 核只是后续划分候选方案。

## 在 Ubuntu 24.04 x86-64 宿主机准备

需要 sudo、`/dev/kvm`、可用存储和未占用的上述子网。初次安装：

```sh
sudo apt-get update
sudo apt-get install --no-install-recommends qemu-system-x86 qemu-utils \
  libvirt-daemon-system libvirt-clients ovmf cloud-image-utils dnsmasq-base
sudo install -d -o "$(id -un)" -g "$(id -gn)" -m 755 /data/linux-window-lab
sh scripts/fetch-ubuntu.sh
python3 scripts/provision.py
```

脚本校验镜像 SHA256，发现已有 VM、网络或 state 目录会停止，避免覆盖。Ubuntu 上安装 libvirt 可能同时建立默认 NAT 网络；实验 VM 使用独立的 `lwlab-net`。脚本不设置 VM 开机自启，仅设置实验网络自启。镜像 `current` URL 会变化，每次实验以已保存的 SHA256 为准；不得替换被 overlay 引用的基础镜像。

## 登录与验收

先登录宿主机，再执行：

```sh
ssh -i /data/linux-window-lab/keys/guest_ed25519 lab@192.168.231.10
sudo cloud-init status --wait
```

首次核对 VM 的 SSH 主机指纹（可从宿主机串口日志查看）。实验密钥只保存在宿主机 `keys/`，不进入 Git。

将 `scripts/guest-readiness.py` 复制进 VM，运行并保存输出。检查 UEFI、8 CPU、双 NUMA、cloud-init、构建工具、guest agent、编译运行和文件写入回读。成功仅表示开发环境准备完成。

宿主机控制命令：

```sh
sudo virsh -c qemu:///system dominfo lwlab-dev
sudo virsh -c qemu:///system console lwlab-dev
sudo virsh -c qemu:///system console lwlab-dev serial1
sudo virsh -c qemu:///system domdisplay lwlab-dev
```

串口退出按 `Ctrl+]`。VNC 经 SSH 隧道访问，不向公网开放。配置和日志分别在 `config/`、`artifacts/`。开发 VM 的 `/opt/lwlab/{src,build,results}` 留作源码、构建和结果目录。

验收通过后，`sh scripts/cold-baseline.sh` 会正常关闭本实验 VM，复制系统盘、预留盘和 NVRAM 到 `baselines/pre-multikernel/`，随后重新启动 VM。关闭超时会停止，不执行强制断电。此恢复点仍依赖原始 Ubuntu backing image；恢复时应在 VM 关闭状态下成套处理磁盘和 NVRAM。实验 VM 的销毁、磁盘删除和恢复覆盖都不包含在准备脚本中。

## 后续验收顺序

| 阶段 | 必须取得的证据 |
| --- | --- |
| P0 开发环境 | UEFI Linux 启动、工具链、网络和磁盘可用 |
| P1 AP 独立 payload | 在 VM 内离线指定 CPU，运行测试 payload；Linux 心跳和 I/O 持续正常 |
| P2 分区 UEFI | 独立 EFI 应用验证资源描述、内存分配和服务退出；Linux 保持运行 |
| P3 WinPE | `bootmgfw.efi → winload.efi → WinPE` 在分区内启动；Linux 连续性同时通过 |
| P4 数据观察 | 对带序号和校验值的测试数据进行 Linux 外部读取和一致性验证 |

外层 OVMF 负责首次启动 Linux。分区 UEFI 是另外需要实现的 payload，不能把完整 OVMF 固件当成现成的 multikernel kexec 镜像。现有 Linux AP trampoline 的 `boot_params` 约定也需要适配。资源描述应覆盖 ACPI、APIC、PCI、低端 trampoline 内存和固件运行时状态。

Windows 11 x64 WinPE 的制作步骤见 [docs/winpe.md](docs/winpe.md)。当前没有 WinPE 镜像，Windows 启动阶段尚未开始。

## 本地固件检查

`lab.py` 与 `config.json` 是 Apple Silicon 上的 x86 TCG 固件冒烟检查，独立于服务器 VM。它只确认 UEFI Shell 可达，不启动 Linux 或 Windows：

```sh
python3 lab.py preflight
python3 lab.py firmware-smoke --seconds 20
```

本仓库只保存脚本、说明和经过筛选的结果摘要。密码、SSH 私钥、磁盘、固件副本、完整服务器信息和运行日志不提交。
