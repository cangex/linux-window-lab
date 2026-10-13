# P4：已知数据外部读取

已在同一台 QEMU/KVM 实验机内通过两次冷启动验收。Windows 侧为
固定的 10.0.26100.1 WinPE；Linux 使用内建只读接口读取其预留物理 RAM。
结果和成本见 [报告](../docs/2026-10-14-p4.md)。

## 读取与发布协议

`kernel/lwobserve.inc` 复用 P3 loader 的资源范围、WB 映射、锁和 generation。
`/dev/lwobserve` 仅允许具有 `CAP_SYS_RAWIO` 的只读打开；每个 FD 固定当前
generation，每次 ioctl 再核对。仅接受三段 Windows RAM 内的单区间读取，
最大 1 MiB；没有 mmap、写入或 MMIO 接口。ABI 在 `lwobserve.h`。
这些限制用于实验正确性，不构成两个内核之间的安全隔离。

`writer.c` 在 WinPE 中用 VirtualAlloc/VirtualLock 保持 4 KiB 测试页驻留。
先发布奇数序号，写入由 nonce/epoch/序号确定的内容及 FNV 校验值，再用
内存屏障和原子交换发布偶数序号。Linux 通过扫描标记定位，按
“序号—整页—序号”读回，逐字验证确定性内容；没有使用 Windows 读取接口。
序号为奇数、跨版本、校验失败或布局异常的结果全部拒绝。

写端每轮在 10–20 秒期间插入 50 ms 半写入停顿；25 秒发布撤销状态，
保留 tombstone 3 秒后释放，再创建新 epoch。读端发现撤销后退休旧 identity，
扫描并验证替代页。此协议依赖及时观察 tombstone，不能作为任意 Windows
分配器的通用释放检测；读取端长时间暂停或写端非合作释放不在已证明范围内。

## 从冻结输入构建

先按 P3 README 准备源码、EDK2 和 `p3-media-v3`。使用新输出目录：

```sh
python3 p4/make-media.py /opt/lwlab/build/p3-media-v3 /opt/lwlab/build/p4-media
python3 p3/wrap-gpt.py /opt/lwlab/build/p4-media/winpe-fat.img /opt/lwlab/build/p4-winpe-gpt.img
python3 p3/stage.py /opt/lwlab/build/p4-stage --disk /opt/lwlab/build/p4-winpe-gpt.img
bash /opt/lwlab/build/p4-stage/build-uefi.sh /opt/lwlab/src/edk2-p3 /opt/lwlab/build/p4-firmware
# source 为从 sources.lock 的原始 archive 展开的新 Linux 目录。
python3 p4/apply.py /opt/lwlab/src/linux-p4 /opt/lwlab/build/p4-stage
sh p4/build-kernel.sh /opt/lwlab/src/linux-p4 /opt/lwlab/build/p4-kernel
sh p3/package.sh /opt/lwlab/src/linux-p4 /opt/lwlab/build/p4-kernel /opt/lwlab/build/p4-package /opt/lwlab/build/p4-firmware
gcc -O2 -Wall -Wextra -Werror p4/reader.c -o reader
gcc -O2 -Wall -Wextra -Werror p4/tests/protocol.c -o test-protocol
./test-protocol
python3 p4/stage-tools.py /opt/lwlab/build/p4-tools
```

把 package、tools、reader 放到宿主机 `artifacts/p4/` 对应目录，然后执行
`prepare-boot-vm.py` 保存 P3 冷备份并安装。该脚本只针对 `lwlab-boot`，
拒绝覆盖既有备份。继续运行生成的 `tools/run-attempt.py`，参数为
`package/partition.bin ATTEMPT --seconds 130`，最后执行
`python3 p4/verify-results.py artifacts/p4/ATTEMPT`。

`reader.c` 默认至少一百万次尝试和 40 秒；验收 harness 使用 65 秒。
延迟直方图按 `floor(log2(ns))` 分桶，包含快速拒绝、整页验证，不含撤销后
重新定位；总墙钟与 CPU 时间包含重新定位。吞吐是已接受样本字节数，
重复读取同一版本也计数，不能解释为 Windows 新数据产生率或裸机收益。

此阶段沿用 P3 ABI 3 以及 `/lib/firmware/lwlab/partition-p3.bin` 的 loader
文件名；磁盘安装包仍名为 `p3-modules.tar.gz`，其内容为实际 P4 内核模块。
