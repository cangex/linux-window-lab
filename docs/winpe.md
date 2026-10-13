# Windows 11 x64 WinPE 制作

当前未提供 WinPE 镜像。以下步骤在 Windows 制作机执行；Linux 实验 VM 用于开发和后续启动实验。

## 固定版本

本项目拟采用 ADK **10.1.26100.9457（2026 年 9 月）**及对应 WinPE add-on，架构为 `amd64`。这是 2026-10-13 核对微软下载页后选定的基线；安装后应记录实际 WinPE build 和补丁版本。ADK 安装包与 WinPE add-on 是两个下载项。

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
