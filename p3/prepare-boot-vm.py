#!/usr/bin/env python3
"""Cold-save idle P2 VM and install P3; host stays running."""
import argparse
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET

p = argparse.ArgumentParser()
p.add_argument('--root', type=Path, default=Path('/data/linux-window-lab'))
p.add_argument('--resume-saved-p2', action='store_true')
a = p.parse_args()
root = a.root.resolve()
key = root / 'keys/guest_ed25519'
target = 'lab@192.168.231.11'
domain = 'lwlab-boot'
def run(*args, check=True):
    return subprocess.run(list(map(str, args)), capture_output=True, text=True, check=check)
def virsh(*args):
    return run('sudo', '-n', 'virsh', *args).stdout.strip()
def ssh(command, check=True):
    return run('ssh', '-i', key, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=4',
               target, command, check=check)
def wait_for(predicate, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate(): return
        time.sleep(2)
    raise TimeoutError('VM transition timed out; state preserved for inspection')
backup = root / 'baselines/pre-p3'
if backup.exists() and not a.resume_saved_p2:
    p.error('pre-p3 backup already exists; refusing to repeat preparation')
assert ssh('uname -r').stdout.strip() == '6.18.0-rc3-lwlab-p2'
assert ssh('cat /sys/kernel/lwlab/status').stdout.startswith('state=idle ')
package = root / 'artifacts/p3/package'
subprocess.run(['sha256sum', '-c', 'SHA256SUMS'], cwd=package, check=True)
if not a.resume_saved_p2:
    backup.mkdir()
    xml = virsh('dumpxml', '--inactive', domain)
    (backup / 'domain.xml').write_text(xml)
else:
    assert (backup / 'linux.qcow2').is_file() and (backup / 'OVMF_VARS.fd').is_file()
    xml = (backup / 'domain.xml').read_text()
ssh('sudo poweroff', check=False)
wait_for(lambda: virsh('domstate', domain) == 'shut off', 90)
if not a.resume_saved_p2:
    for name in ('linux.qcow2', 'OVMF_VARS.fd'):
        run('sudo', '-n', 'cp', '--reflink=auto', '--sparse=always',
            root / 'state-p1' / name, backup / name)
print('Cold P2 backup saved', flush=True)
ET.register_namespace('qemu', 'http://libvirt.org/schemas/domain/qemu/1.0')
tree = ET.fromstring(xml)
ns = '{http://libvirt.org/schemas/domain/qemu/1.0}'
assert tree.find(ns + 'commandline') is None
clock = tree.find('clock')
assert clock is not None
hpet = clock.find("timer[@name='hpet']")
if hpet is None: hpet = ET.SubElement(clock, 'timer', {'name': 'hpet'})
hpet.set('present', 'yes')
config = root / 'config/p3-boot.xml'
ET.ElementTree(tree).write(config, encoding='unicode')
virsh('define', config)
virsh('start', domain)
wait_for(lambda: ssh('true', check=False).returncode == 0, 180)
memory = ssh('sudo cat /proc/iomem').stdout
(root / 'artifacts/p3/p3-before-install-iomem.txt').write_text(memory)
# Pre-reservation view must show ordinary RAM for all three owned extents.
for lo, hi in ((0x10000000, 0x6fffffff), (0x100000, 0xffffff), (0x50000, 0x6ffff)):
    assert any(int(line.split('-')[0],16) <= lo and
               int(line.split('-')[1].split()[0],16) >= hi
               for line in memory.splitlines() if not line.startswith(' ') and line.endswith(': System RAM'))
ssh('mkdir -p /tmp/p3-install')
run('scp', '-i', key, *sorted(package.iterdir()), str(Path(__file__).with_name('install-guest.sh')),
    target + ':/tmp/p3-install/')
ssh('cd /tmp/p3-install && sha256sum -c SHA256SUMS && sudo sh ./install-guest.sh /tmp/p3-install')
ssh('sudo poweroff', check=False)
wait_for(lambda: virsh('domstate', domain) == 'shut off', 90)
virsh('start', domain)
wait_for(lambda: ssh('true', check=False).returncode == 0, 180)
assert ssh('uname -r').stdout.strip() == '6.18.0-rc3-lwlab-p3'
status = ssh('cat /sys/kernel/lwlab/status').stdout
assert status.startswith('state=idle ') and 'bytes=0x60000000' in status
print(status, flush=True)
