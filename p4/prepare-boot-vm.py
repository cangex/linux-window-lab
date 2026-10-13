#!/usr/bin/env python3
"""Cold-save the working P3 disk/firmware before installing the P4 kernel."""
import argparse,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('/data/linux-window-lab'));a=p.parse_args()
r=a.root;k=r/'keys/guest_ed25519';target='lab@192.168.231.11'
def run(*cmd,**kw):return subprocess.run(list(map(str,cmd)),check=True,capture_output=True,text=True,**kw)
def guest(cmd):return run('ssh','-i',k,'-o','ConnectTimeout=4',target,cmd).stdout
def virsh(*args):return run('sudo','-n','virsh',*args).stdout.strip()
def wait(predicate,n=120):
 end=time.monotonic()+n
 while time.monotonic()<end:
  try:
   if predicate():return
  except subprocess.CalledProcessError:pass
  time.sleep(2)
 raise TimeoutError('VM transition timed out; no forced reset')
assert guest('uname -r').strip()=='6.18.0-rc3-lwlab-p3'
b=r/'baselines/pre-p4';assert not b.exists();b.mkdir()
(b/'domain.xml').write_text(virsh('dumpxml','--inactive','lwlab-boot'))
subprocess.run(['ssh','-i',str(k),target,'sudo poweroff'],capture_output=True)
wait(lambda:virsh('domstate','lwlab-boot')=='shut off')
for f in ('linux.qcow2','OVMF_VARS.fd'):run('sudo','-n','cp','--reflink=auto','--sparse=always',r/'state-p1'/f,b/f)
virsh('start','lwlab-boot');wait(lambda:guest('true')=='')
package=r/'artifacts/p4/package'
run('sha256sum','-c','SHA256SUMS',cwd=package)
guest('mkdir -p /tmp/p4-install')
run('scp','-i',k,*sorted(package.iterdir()),r/'artifacts/p4/tools/install-guest.sh',target+':/tmp/p4-install/')
guest('cd /tmp/p4-install && sha256sum -c SHA256SUMS && sudo sh ./install-guest.sh /tmp/p4-install')
run('scp','-i',k,r/'artifacts/p4/reader',target+':/tmp/p4-install/reader')
guest('sudo install -D -m 755 /tmp/p4-install/reader /opt/lwlab/bin/lwreader')
subprocess.run(['ssh','-i',str(k),target,'sudo poweroff'],capture_output=True)
wait(lambda:virsh('domstate','lwlab-boot')=='shut off')
virsh('start','lwlab-boot');wait(lambda:guest('true')=='')
assert guest('uname -r').strip()=='6.18.0-rc3-lwlab-p4'
assert guest('cat /sys/kernel/lwlab/status').startswith('state=idle ')
print(guest('ls -l /dev/lwobserve'))
