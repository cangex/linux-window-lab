#!/usr/bin/env python3
"""Ordinary OVMF control VM for deployment, never a coexistence result."""
import argparse,json,shutil,subprocess
from pathlib import Path
from xml.sax.saxutils import escape
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('/data/linux-window-lab'));a=p.parse_args()
r=a.root;name='lwlab-windows-install';state=r/'state-p5-install';assert not state.exists()
iso=r/'images/windows-ltsc/windows11-ltsc-eval.iso';media=r/'artifacts/p5/installer/installer-gpt.img'
assert iso.is_file() and media.is_file()
run=lambda *x:subprocess.run(list(map(str,x)),check=True,text=True,capture_output=True)
assert name not in run('sudo','-n','virsh','list','--all','--name').stdout.splitlines()
state.mkdir();shutil.copyfile('/usr/share/OVMF/OVMF_VARS_4M.fd',state/'OVMF_VARS.fd')
installer=state/'installer.qcow2';run('qemu-img','create','-f','qcow2','-F','raw','-b',media,installer)
disk=state/'windows.qcow2';run('qemu-img','create','-f','qcow2',disk,'64G')
q=lambda x:escape(str(x),{"'":'&apos;'})
xml=f'''<domain type='kvm' xmlns:qemu='http://libvirt.org/schemas/domain/qemu/1.0'>
<name>{name}</name><memory unit='MiB'>8192</memory><vcpu>4</vcpu>
<os><type arch='x86_64' machine='pc-q35-8.2'>hvm</type><loader readonly='yes' secure='no' type='pflash'>/usr/share/OVMF/OVMF_CODE_4M.fd</loader><nvram>{q(state/'OVMF_VARS.fd')}</nvram><boot dev='hd'/></os>
<features><acpi/><apic/></features><cpu mode='host-passthrough' migratable='off'/><clock offset='utc'/>
<on_poweroff>destroy</on_poweroff><on_reboot>restart</on_reboot><on_crash>preserve</on_crash>
<seclabel type='none' model='apparmor'/>
<devices><emulator>/usr/bin/qemu-system-x86_64</emulator>
<disk type='file' device='disk'><driver name='qemu' type='qcow2'/><source file='{q(installer)}'/><target dev='sda' bus='sata'/></disk>
<disk type='file' device='cdrom'><driver name='qemu' type='raw'/><source file='{q(iso)}'/><target dev='sdb' bus='sata'/><readonly/></disk>
<graphics type='vnc' autoport='yes' listen='127.0.0.1'/><video><model type='vga'/></video><memballoon model='none'/>
</devices>
<qemu:commandline><qemu:arg value='-drive'/><qemu:arg value='file={q(disk)},if=none,id=windisk,format=qcow2,cache=none'/><qemu:arg value='-device'/><qemu:arg value='nvme,bus=pcie.0,addr=0x7,drive=windisk,serial=LWLABP5INSTALL,bootindex=2'/></qemu:commandline>
</domain>'''
config=r/'config/p5-installer.xml';config.write_text(xml)
run('sudo','-n','chown','-R','libvirt-qemu:kvm',state)
run('sudo','-n','virsh','define',config);run('sudo','-n','virsh','start',name)
print(json.dumps(dict(domain=name,ordinary_vm=True,coexistence=False)))
