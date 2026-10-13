#!/usr/bin/env python3
"""Run on the lab host; capture only the two project guests and their toolchain."""
import argparse
import json
from pathlib import Path
import subprocess

p = argparse.ArgumentParser()
p.add_argument('--output', type=Path, required=True)
p.add_argument('--key', default='/data/linux-window-lab/keys/guest_ed25519')
a = p.parse_args()
if a.output.exists():
    raise SystemExit('Output already exists')

def capture(command):
    r = subprocess.run(command, text=True, capture_output=True, check=True)
    return r.stdout.strip()

def guest(ip, command):
    return capture(['ssh', '-i', a.key, '-o', 'BatchMode=yes', f'lab@{ip}', command])

report = {'qemu': capture(['qemu-system-x86_64','--version']),
          'packages': capture(['dpkg-query','-W','ovmf','libvirt-daemon-system']),
          'domain_xml': capture(['sudo','virsh','dumpxml','lwlab-boot','--inactive']),
          'builder': {}, 'boot_guest': {}}
for name, command in {
    'compiler': 'gcc --version', 'assembler': 'nasm -v', 'linker': 'ld --version', 'make': 'make --version',
    'build_hashes': 'cat /opt/lwlab/build/p1/SHA256SUMS',
    'overlay_hashes': 'cd /opt/lwlab/src/linux-p1 && sha256sum arch/x86/kernel/smpboot.c kernel/Makefile kernel/zdu/Kconfig kernel/lwlab.c',
}.items():
    report['builder'][name] = guest('192.168.231.10', command)
for name, command in {
    'kernel': 'uname -a', 'cmdline': 'cat /proc/cmdline', 'cpu': 'lscpu -e',
    'cpuinfo': 'cat /proc/cpuinfo', 'iomem': 'sudo cat /proc/iomem',
    'status': 'cat /sys/kernel/lwlab/status', 'tainted': 'cat /proc/sys/kernel/tainted',
    'uefi': 'test -d /sys/firmware/efi && echo yes',
    'artifact_hashes': 'sha256sum /boot/vmlinuz-6.18.0-rc3-lwlab-p1 /boot/config-6.18.0-rc3-lwlab-p1 /lib/firmware/lwlab/ap-probe.bin',
}.items():
    report['boot_guest'][name] = guest('192.168.231.11', command)
a.output.write_text(json.dumps(report,indent=2)+'\n')
print(a.output)
