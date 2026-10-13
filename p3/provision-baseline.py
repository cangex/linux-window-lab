#!/usr/bin/env python3
"""Create a fresh ordinary OVMF WinPE control VM, never a coexistence result."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from xml.sax.saxutils import escape

def virsh(*args, capture=False):
    return subprocess.run(['sudo', '-n', 'virsh', '-c', 'qemu:///system', *map(str, args)],
                          check=True, text=True, capture_output=capture)

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=Path('/data/linux-window-lab'))
    p.add_argument('--name', default='lwlab-winpe-baseline')
    p.add_argument('--image', type=Path)
    a = p.parse_args()
    root = a.root.resolve()
    name = a.name
    assert name.startswith('lwlab-winpe-') and name.replace('-', '').isalnum()
    state = root / ('state-' + name)
    image = (a.image or root / 'images/winpe/winpe-gpt.img').resolve()
    if not image.is_file():
        p.error('WinPE FAT image missing')
    if state.exists() or name in virsh('list', '--all', '--name', capture=True).stdout.splitlines():
        p.error('Baseline state or VM exists; refusing to overwrite')
    state.mkdir()
    logs = root / 'artifacts/p3' / name
    logs.mkdir(parents=True, exist_ok=True)
    shutil.copyfile('/usr/share/OVMF/OVMF_VARS_4M.fd', state / 'OVMF_VARS.fd')
    overlay = state / 'winpe.qcow2'
    subprocess.run(['qemu-img', 'create', '-f', 'qcow2', '-F', 'raw', '-b', str(image), str(overlay)], check=True)
    q = lambda s: escape(str(s), {"'": '&apos;'})
    xml = f"""<domain type='kvm'>
 <name>{name}</name><memory unit='MiB'>4096</memory><vcpu>1</vcpu>
 <os><type arch='x86_64' machine='pc-q35-8.2'>hvm</type>
  <loader readonly='yes' secure='no' type='pflash'>/usr/share/OVMF/OVMF_CODE_4M.fd</loader>
  <nvram>{q(state / 'OVMF_VARS.fd')}</nvram><boot dev='hd'/></os>
 <features><acpi/><apic/></features><cpu mode='host-passthrough' migratable='off'/>
 <clock offset='utc'><timer name='hpet' present='no'/></clock>
 <on_poweroff>destroy</on_poweroff><on_reboot>restart</on_reboot><on_crash>preserve</on_crash>
 <devices><emulator>/usr/bin/qemu-system-x86_64</emulator>
  <disk type='file' device='disk'><driver name='qemu' type='qcow2'/>
   <source file='{q(overlay)}'/><target dev='sda' bus='sata'/></disk>
  <serial type='pty'><target type='isa-serial' port='0'/>
   <log file='{q(logs / 'serial0.log')}' append='on'/></serial>
  <serial type='pty'><target type='isa-serial' port='1'/>
   <log file='{q(logs / 'serial1.log')}' append='on'/></serial>
  <graphics type='vnc' autoport='yes' listen='127.0.0.1'/>
  <video><model type='vga'/></video><memballoon model='none'/>
 </devices></domain>"""
    config = root / 'config' / (name + '.xml')
    config.write_text(xml)
    subprocess.run(['sudo', '-n', 'chown', '-R', 'libvirt-qemu:kvm', str(state)], check=True)
    virsh('define', config)
    virsh('start', name)
    (logs / 'provision.json').write_text(json.dumps(dict(domain=name, cpus=1,
        memory_mib=4096, ordinary_vm=True, coexistence=False), indent=2) + '\n')

if __name__ == '__main__':
    main()
