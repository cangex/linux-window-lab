#!/usr/bin/env python3
"""Create the disposable P1 boot target from the verified cold baseline."""
from pathlib import Path
import subprocess
import shutil
import xml.etree.ElementTree as ET

root = Path('/data/linux-window-lab')
def run(*args):
    return subprocess.check_output(args, text=True)
def virsh(*args):
    return run('sudo', '-n', 'virsh', '-c', 'qemu:///system', *args)
assert 'lwlab-boot' not in virsh('list', '--all', '--name').splitlines()
state = root / 'state-p1'
assert not state.exists(), 'P1 state already exists'
state.mkdir()
(root / 'artifacts/p1').mkdir(exist_ok=True)
run('qemu-img', 'create', '-f', 'qcow2', '-F', 'qcow2', '-b',
    str(root / 'baselines/pre-multikernel/linux.qcow2'), str(state / 'linux.qcow2'))
shutil.copyfile(root / 'baselines/pre-multikernel/OVMF_VARS.fd', state / 'OVMF_VARS.fd')
public = (root / 'keys/guest_ed25519.pub').read_text().strip()
(state / 'user-data').write_text(f'''#cloud-config
hostname: lwlab-boot
manage_etc_hosts: true
users:
  - name: lab
    groups: [adm, sudo]
    shell: /bin/bash
    sudo: ALL=(ALL) NOPASSWD:ALL
    lock_passwd: true
    ssh_authorized_keys:
      - {public}
ssh_pwauth: false
package_update: false
package_upgrade: false
''')
(state / 'meta-data').write_text('instance-id: lwlab-boot-p1-001\nlocal-hostname: lwlab-boot\n')
run('cloud-localds', str(state/'seed.iso'), str(state/'user-data'), str(state/'meta-data'))
domain = ET.fromstring(virsh('dumpxml', 'lwlab-dev', '--inactive'))
domain.find('name').text = 'lwlab-boot'
domain.remove(domain.find('uuid'))
domain.find('os/nvram').text = str(state/'OVMF_VARS.fd')
# Keep each virtual LLC/package within one NUMA node.
domain.find('cpu/topology').set('sockets', '2')
domain.find('cpu/topology').set('cores', '4')
disks = domain.findall('devices/disk')
assert len(disks) == 2
assert sorted(d.get('device') for d in disks) == ['cdrom', 'disk']
for disk in disks:
    disk.find('source').set('file', str(state/('linux.qcow2' if disk.get('device') == 'disk' else 'seed.iso')))
domain.find('devices/interface/mac').set('address', '52:54:00:4c:57:11')
for node in domain.findall('devices/serial') + domain.findall('devices/console'):
    port = node.find('target').get('port')
    node.find('log').set('file', str(root/f'artifacts/p1/serial{port}.log'))
domain.find('devices/graphics').set('port', '-1')
watchdog = domain.find('devices/watchdog')
if watchdog is not None:
    domain.find('devices').remove(watchdog)
ET.indent(domain)
path = root/'config/p1-boot.xml'
ET.ElementTree(domain).write(path, encoding='unicode')
run('sudo', '-n', 'chown', '-R', 'libvirt-qemu:kvm', str(state))
print(virsh('net-update', 'lwlab-net', 'add-last', 'ip-dhcp-host',
            "<host mac='52:54:00:4c:57:11' name='lwlab-boot' ip='192.168.231.11'/>", '--live', '--config'))
print(virsh('define', str(path)))
print(virsh('start', 'lwlab-boot'))
