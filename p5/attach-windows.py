#!/usr/bin/env python3
"""Clone the cold installed baseline into the exclusive coexistence controller."""
import argparse,subprocess,time,xml.etree.ElementTree as ET
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('/data/linux-window-lab'));a=p.parse_args();r=a.root
def run(*x,**kw):return subprocess.run(list(map(str,x)),check=True,text=True,capture_output=True,**kw)
def virsh(*x):return run('sudo','-n','virsh',*x).stdout.strip()
assert virsh('domstate','lwlab-windows-install')=='shut off'
baseline=r/'state-p5-install/windows.qcow2';disk=r/'state-p5/windows.qcow2';assert not disk.exists()
run('sudo','-n','qemu-img','create','-f','qcow2','-F','qcow2','-b',baseline,disk)
run('sudo','-n','chown','libvirt-qemu:kvm',disk)
key=r/'keys/guest_ed25519'
subprocess.run(['ssh','-i',str(key),'lab@192.168.231.11','sudo poweroff'],capture_output=True)
for _ in range(90):
 if virsh('domstate','lwlab-boot')=='shut off':break
 time.sleep(2)
else:raise TimeoutError('Linux did not power off')
xml=virsh('dumpxml','--inactive','lwlab-boot');t=ET.fromstring(xml)
found=False
for arg in t.findall('{http://libvirt.org/schemas/domain/qemu/1.0}commandline/{http://libvirt.org/schemas/domain/qemu/1.0}arg'):
 v=arg.get('value','')
 if v.startswith('file='+str(r/'state-p5/probe.qcow2')+','):
  arg.set('value',v.replace(str(r/'state-p5/probe.qcow2'),str(disk)));found=True
assert found
config=r/'config/p5-coexistence.xml';ET.ElementTree(t).write(config,encoding='unicode')
virsh('define',config);virsh('start','lwlab-boot')
print('Installed Windows clone attached; original baseline remains shut down.')
