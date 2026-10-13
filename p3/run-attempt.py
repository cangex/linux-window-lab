#!/usr/bin/env python3
"""One cold AP attempt with preserved failure evidence and independent Linux and WinPE userspace telemetry."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

p = argparse.ArgumentParser()
p.add_argument('firmware', type=Path)
p.add_argument('name')
p.add_argument('--seconds', type=int, default=60)
p.add_argument('--minimum-seconds', type=int, default=30)
p.add_argument('--root', type=Path, default=Path('/data/linux-window-lab'))
a = p.parse_args()
assert a.name.replace('-', '').replace('_', '').isalnum()
root = a.root.resolve()
out = root / 'artifacts/p3' / a.name
assert not out.exists()
key = root / 'keys/guest_ed25519'
ssh = ['ssh', '-i', str(key), '-o', 'ConnectTimeout=4', '-o', 'BatchMode=yes', 'lab@192.168.231.11']
def run(args, **kw):
    return subprocess.run(list(map(str, args)), check=True, text=True, capture_output=True, **kw)
def guest(command): return run(ssh + [command]).stdout
def virsh(*args): return run(['sudo', '-n', 'virsh', *args]).stdout
assert guest('hostname').strip() == 'lwlab-boot'
assert guest('uname -r').strip() == '6.18.0-rc3-lwlab-p3'
oldboot = guest('cat /proc/sys/kernel/random/boot_id').strip()
guest('mkdir -p /tmp/p3-attempt')
run(['scp', '-i', key, a.firmware, 'lab@192.168.231.11:/tmp/p3-attempt/firmware.bin'])
digest = hashlib.file_digest(a.firmware.open('rb'), 'sha256').hexdigest()
assert guest('sha256sum /tmp/p3-attempt/firmware.bin').split()[0] == digest
guest('sudo install -m 644 /tmp/p3-attempt/firmware.bin /lib/firmware/lwlab/partition-p3.bin')
subprocess.run(ssh + ['sudo poweroff'], capture_output=True)
deadline = time.monotonic() + 90
while virsh('domstate', 'lwlab-boot').strip() != 'shut off':
    if time.monotonic() > deadline: raise TimeoutError('Poweroff failed; no forced reset')
    time.sleep(2)
virsh('start', 'lwlab-boot')
deadline = time.monotonic() + 180
while True:
    response = subprocess.run(ssh + ['cat /proc/sys/kernel/random/boot_id'], capture_output=True, text=True)
    if response.returncode == 0 and response.stdout.strip() != oldboot: break
    if time.monotonic() > deadline: raise TimeoutError('Cold boot did not return')
    time.sleep(2)
assert guest('cat /sys/kernel/lwlab/status').startswith('state=idle ')
guest('mkdir -p /tmp/p3-attempt')
before_interrupts = guest('cat /proc/interrupts')
offset = int(run(['sudo', '-n', 'stat', '-c', '%s', root / 'artifacts/p1/serial1.log']).stdout)
run(['scp', '-i', key, Path(__file__).with_name('guest-probe.py'), 'lab@192.168.231.11:/tmp/p3-attempt/guest-probe.py'])
with (out.with_suffix('.guest.log')).open('w') as log:
    proc = subprocess.Popen(ssh + [f'sudo python3 /tmp/p3-attempt/guest-probe.py --seconds {a.seconds}'], stdout=log, stderr=log)
    windows = subprocess.Popen(['python3', str(Path(__file__).with_name('observe-winpe.py')), str(out), '--seconds', str(a.seconds + 180)])
    try:
        observed = subprocess.run(['python3', str(root / 'repo/p1/host-observe.py'), '--output', str(out)], timeout=a.seconds+150)
    finally:
        out.mkdir(exist_ok=True)
        (out / 'windows.stop').touch()
        try: windows_exit = windows.wait(timeout=25)
        except subprocess.TimeoutExpired:
            windows.terminate(); windows_exit = windows.wait(timeout=5)
    try:
        guest_result = proc.wait(timeout=45)
    except subprocess.TimeoutExpired:
        proc.terminate(); guest_result = None
out.mkdir(exist_ok=True)
serial = subprocess.run(['sudo', '-n', 'tail', '-c', f'+{offset+1}', str(root / 'artifacts/p1/serial1.log')], check=True, capture_output=True).stdout
(out / 'uefi.log').write_bytes(serial)
(out / 'dmesg.txt').write_text(guest('sudo dmesg'))
(out / 'vm.xml').write_text(virsh('dumpxml', 'lwlab-boot'))
(out / 'registers.txt').write_text(virsh('qemu-monitor-command', 'lwlab-boot', '--hmp', 'info registers -a'))
(out / 'interrupts-before.txt').write_text(before_interrupts)
(out / 'interrupts-after.txt').write_text(guest('cat /proc/interrupts'))
(out / 'metadata.json').write_text(json.dumps(dict(firmware_sha256=digest,
    kernel=guest('uname -r').strip(),
    kernel_sha256=guest('sha256sum /boot/vmlinuz-6.18.0-rc3-lwlab-p3').split()[0],
    config_sha256=guest('sha256sum /boot/config-6.18.0-rc3-lwlab-p3').split()[0],
    boot_id=guest('cat /proc/sys/kernel/random/boot_id').strip(),
    windows_observer_exit=windows_exit, cmdline=guest('cat /proc/cmdline').strip(),
    guest_exit=guest_result, observer_exit=observed.returncode,
    windows_userspace_confirmed=False, coexistence_passed=False), indent=2) + '\n')

raise SystemExit(subprocess.run(['python3', str(Path(__file__).with_name('verify-attempt.py')), str(out), '--minimum-seconds', str(a.minimum_seconds)]).returncode)
