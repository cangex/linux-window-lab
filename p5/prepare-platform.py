#!/usr/bin/env python3
"""Cold preserve P4, then add an otherwise unused NVMe subtree to the lab VM."""
import argparse,subprocess,time,xml.etree.ElementTree as ET
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('/data/linux-window-lab'));a=p.parse_args()
r=a.root;k=r/'keys/guest_ed25519';target='lab@192.168.231.11'
def run(*cmd,**kw):return subprocess.run(list(map(str,cmd)),check=True,capture_output=True,text=True,**kw)
def guest(cmd):return run('ssh','-i',k,'-o','ConnectTimeout=4',target,cmd).stdout
def virsh(*args):return run('sudo','-n','virsh',*args).stdout.strip()
def wait(predicate,n=180):
 end=time.monotonic()+n
 while time.monotonic()<end:
  try:
   if predicate():return
  except subprocess.CalledProcessError:pass
  time.sleep(2)
 raise TimeoutError('VM transition failed; saved state retained')
assert guest('uname -r').strip()=='6.18.0-rc3-lwlab-p4'
b=r/'baselines/pre-p5';assert not b.exists();b.mkdir()
xml=virsh('dumpxml','--inactive','lwlab-boot');(b/'domain.xml').write_text(xml)
subprocess.run(['ssh','-i',str(k),target,'sudo poweroff'],capture_output=True)
wait(lambda:virsh('domstate','lwlab-boot')=='shut off')
for f in ('linux.qcow2','OVMF_VARS.fd'):run('sudo','-n','cp','--reflink=auto','--sparse=always',r/'state-p1'/f,b/f)
state=r/'state-p5';state.mkdir()
disk=state/'probe.qcow2';run('qemu-img','create','-f','qcow2',disk,'64G')
run('sudo','-n','chown','-R','libvirt-qemu:kvm',state)
ns='http://libvirt.org/schemas/domain/qemu/1.0';ET.register_namespace('qemu',ns)
t=ET.fromstring(xml);assert t.find('{'+ns+'}commandline') is None
args=ET.SubElement(t,'{'+ns+'}commandline')
for arg in ('-device','pxb-pcie,id=p5root,bus=pcie.0,addr=0x3,bus_nr=128,numa_node=1',
 '-device','pcie-root-port,id=p5port,bus=p5root,addr=0,chassis=128,slot=0',
 '-drive',f'file={disk},if=none,id=p5disk,format=qcow2,cache=none',
 '-device','nvme,id=p5nvme,bus=p5port,addr=0,drive=p5disk,serial=LWLABP5INSTALL'):
 ET.SubElement(args,'{'+ns+'}arg',{'value':arg})
ET.SubElement(t,'seclabel',{'type':'none','model':'apparmor'})
config=r/'config/p5-platform.xml';ET.ElementTree(t).write(config,encoding='unicode')
virsh('define',config);virsh('start','lwlab-boot');wait(lambda:guest('true')=='')
out=r/'artifacts/p5';out.mkdir(exist_ok=True)
(out/'platform-pci.txt').write_text(guest('sudo lspci -nnvv; sudo cat /proc/iomem'))
print(guest('sudo lspci -s 81:00.0 -nnvv'))
