# Windows 11 x64 WinPE 制作

P3 已从微软官方 add-on 构建并验证 WinPE，实际 WIM 系统版本为 **10.0.26100.1（amd64，en-US）**。项目同时保存 Windows 官方制作流程与本轮 Linux 实验装配流程。结果见 [P3 报告](2026-10-14-p3.md)。

## 固定版本

本项目固定 ADK **10.1.26100.9457（2026 年 9 月）**及对应 WinPE add-on，架构为 `amd64`。这是 2026-10-13 核对微软下载页后选定的基线；安装后应记录实际 WinPE build 和补丁版本。ADK 安装包与 WinPE add-on 是两个下载项。

[微软 ADK 与 WinPE add-on 下载页](https://learn.microsoft.com/en-us/windows-hardware/get-started/adk-install)

## 制作 ISO

1. 安装 ADK 的 Deployment Tools，再安装相同版本的 WinPE add-on。
2. 以管理员身份打开 **Deployment and Imaging Tools Environment**。
3. 在尚不存在的工作目录创建最小 x64 镜像：

```bat
copype amd64 C:\lwlab-winpe-amd64
MakeWinPEMedia /ISO C:\lwlab-winpe-amd64 C:\lwlab-winpe-amd64\lwlab-winpe-amd64.iso /bootex
Dism /Get-WimInfo /WimFile:C:\lwlab-winpe-amd64\media\sources\boot.wim /index:1
certutil -hashfile C:\lwlab-winpe-amd64\lwlab-winpe-amd64.iso SHA256
certutil -hashfile C:\lwlab-winpe-amd64\media\sources\boot.wim SHA256
```

`/bootex` 选择 Windows UEFI 2023 CA 签名的启动文件；本实验初期的 OVMF 配置关闭 Secure Boot。保留标准 `wpeinit` 和命令提示符，暂不加入业务程序或第三方驱动。

[微软 WinPE 启动介质制作说明](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/winpe-create-usb-bootable-drive?view=windows-11)

## 交付给实验环境

通过既有 SSH 连接把 ISO、SHA256 和 DISM 输出放入宿主机 `/data/linux-window-lab/images/winpe/`。同时记录 ADK/add-on 安装版本、应用的更新、架构和制作时间。镜像和微软二进制文件不提交到 Git 仓库。

首次验证应另建一次性 WinPE 基线 VM，确认镜像能在标准 OVMF 平台启动。不要直接改变正在运行的 `lwlab-dev` 的启动顺序。随后才验证 Linux 持续运行时的分区引导环境；普通 WinPE VM 启动不等于双系统共存成功。

## P3 实际采用的 Linux 装配流程

因为初始没有 Windows 制作机或现成镜像，本轮从上述微软下载站获取固定版本的 MSI/CAB，在 `lwlab-dev` 使用 `msiextract`、`wimlib-imagex` 和 `mtools` 装配实验副本。没有运行 Windows 专用的 copype/DISM，也不把这个流程称为微软官方制作工具的等价实现。

```sh
python3 p3/fetch-media.py /opt/lwlab/build/p3-adk
python3 p3/make-media.py /opt/lwlab/build/p3-adk /opt/lwlab/build/p3-media
python3 p3/wrap-gpt.py /opt/lwlab/build/p3-media/winpe-fat.img /opt/lwlab/build/winpe-gpt.img
```

`p3/media-source.json` 固定下载 URL、Burn 清单中的大小/SHA1、安装器与清单 SHA256；下载后另外记录全部文件的 SHA256。`make-media.py` 再次核对输入，保留原始 WIM，记录每个输出文件、测试程序和 FAT 的 SHA256。

实际修改仅包括：从原始 WIM 提取微软 `bootmgfw_EX.efi`，复制为介质中的启动管理器；加入仓库编译的 `lwprobe.exe`；修改 `startnet.cmd`，在 `wpeinit` 后启动测试程序。Windows 内核和系统驱动保持微软原始二进制。镜像为 512 MiB FAT32 ESP，加 GPT 后总大小为 514 MiB；与分区内只读 RAM disk 直接配合，无需 ISO 设备驱动。

本次输入和输出哈希见 [固定介质清单](p3-media-manifest.json)。ADK 安装包的 `10.1.26100.9457` 不能当作运行中 Windows 的 build：解出的 WIM 报告 `10.0.26100.1`，未另外注入系统累积更新。`media.json` 是构建记录，其初始 `baseline_boot_passed=false`、`coexistence_passed=false` 不会在运行时改写；实际验收另存于报告和验证 JSON。

普通 `lwlab-winpe-visual` 基线验证最终镜像能到达命令行并运行同一个探针；正式共存测试在 `lwlab-boot` 的 AP 分区中执行。没有将两个独立 VM 的运行混作同机共存。
