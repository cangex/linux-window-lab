#!/usr/bin/env python3
"""One experimental partition restart. Run only inside lwlab-boot with P6 r5.

Never power-cycle the outer VM. Failed quiescence aborts without preparing RAM.
"""
import argparse,ctypes,errno,fcntl,json,os,socket,struct,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'p5'))
from observer import Physical,Virtual,bootstrap,processes,Unavailable
from windows_clock import SHARED_USER_DATA,read_clock
p=argparse.ArgumentParser();p.add_argument('profile',type=Path)
p.add_argument('--require-no-shorthand',action='store_true');a=p.parse_args()
assert socket.gethostname()=='lwlab-boot'
assert os.uname().release=='6.18.0-rc3-lwlab-p6'
status=Path('/sys/kernel/lwlab/status');control=Path('/sys/kernel/lwlab/control')
def state():return dict(x.split('=',1) for x in status.read_text().split())
def command(text):
 fd=os.open(control,os.O_WRONLY)
 try:assert os.write(fd,(text+'\n').encode())==len(text)+1
 finally:os.close(fd)
def report(event,**kw):print(json.dumps(dict(event=event,monotonic=time.monotonic(),**kw)),flush=True)
def stale(fd):
 try:fcntl.ioctl(fd,0x80605740,bytearray(96),True)
 except OSError as e:
  assert e.errno==errno.ESTALE,e;return True
 raise AssertionError('revoked handle still readable')
def stale_read(memory):
 buffer=ctypes.create_string_buffer(8)
 request=struct.pack('<4Q',memory.generation,memory.extents[0][0],8,ctypes.addressof(buffer))
 try:fcntl.ioctl(memory.fd,0x40205741,request)
 except OSError as e:
  assert e.errno==errno.ESTALE,e;return True
 raise AssertionError('revoked handle accepted physical read')
def running(memory,boot):
 v=Virtual(memory,boot['cr3']);kernel=boot['kernel'];off=profile['types']['_KPRCB']['fields']
 count=v.u32(kernel+profile['symbols']['KeNumberProcessors']);assert count==4
 cpus=[]
 for i in range(count):
  prcb=v.u64(kernel+profile['symbols']['KiProcessorBlock']+8*i)
  row={k:(v.u64 if k in ('CurrentThread','CycleTime') else v.u32)(prcb+o) for k,o in off.items()}
  assert row['Number']==i and row['InitialApicId']==4+i
  cpus.append(row)
 target=next((x for x in processes(memory,profile,boot) if x['name'].lower()=='lwtruth.exe'),None)
 if target is None:raise Unavailable('workload not running yet')
 cv=Virtual(memory,target['cr3']);shared=profile['types']['_KUSER_SHARED_DATA']['fields']
 uptime=read_clock(cv,profile,boot['build'],'InterruptTime')
 boot_id=cv.u32(SHARED_USER_DATA+shared['BootId'])
 no_shorthand=None
 if a.require_no_shorthand:
  assert boot['pdb'].upper()=='953A8DE880B0818C32DA2DEC1D79C2D91'
  no_shorthand=v.read(kernel+0xe0fc1c,1)[0]
  assert no_shorthand==1,'HAL NoShorthand was not retained across recovery'
 return dict(target=target,cpus=cpus,windows_boot_id=boot_id,interrupt_time_100ns=uptime,hal_no_shorthand=no_shorthand)
profile=json.loads(a.profile.read_text());bootid=Path('/proc/sys/kernel/random/boot_id').read_text()
old=Physical();before=bootstrap(old,profile);old_running=running(old,before);previous=state();report('before',state=previous,bootstrap=before,running=old_running,linux_boot_id=bootid.strip())
command('stop');stopped=state();report('stop',state=stopped)
assert stopped['state']=='stopped' and stopped['started']=='0'
assert stale(old.fd) and stale_read(old)
# Read only the owned endpoint's PCI command register after the kernel stop
# path has checked parking nonces, NVMe RDY=0, pending transactions and reset.
config=Path('/sys/bus/pci/devices/0000:81:00.0/config')
with config.open('rb') as f:
 f.seek(4);command_bytes=f.read(2);assert len(command_bytes)==2;pci_command=int.from_bytes(command_bytes,'little')
assert not pci_command&4,'NVMe bus mastering still enabled'
report('quiescence',pci_command=pci_command,bus_master_disabled=True,
 kernel_log=subprocess.check_output(['dmesg'],text=True).splitlines()[-25:])
try:fresh=Physical()
except OSError as e:assert e.errno==errno.EAGAIN,e
else:os.close(fresh.fd);raise AssertionError('open accepted while stopped')
# Prove reuse is rejected BEFORE an authorized new generation may clear RAM.
try:command(f"prepare 3 4 10000000 60000000 10010000 {old.generation} 0")
except OSError as e:assert e.errno==errno.EINVAL,e
else:raise AssertionError('generation reuse accepted')
assert state()['state']=='stopped'
generation=max(time.time_ns(),old.generation+1)
command(f'prepare 3 4 10000000 60000000 10010000 {generation} 0')
assert state()['state']=='loaded';assert stale(old.fd) and stale_read(old)
command('start');deadline=time.monotonic()+240
while True:
 try:
  current=Physical()
  try:after=bootstrap(current,profile)
  except BaseException:os.close(current.fd);raise
  break
 except (OSError,Unavailable):
  if time.monotonic()>deadline:raise
  time.sleep(2)
assert current.generation==generation and stale(old.fd)
while True:
 try:
  first=running(current,after)
  break
 except Unavailable:
  if time.monotonic()>deadline:raise
  time.sleep(2)
assert first['target']['created']!=old_running['target']['created'],'old workload identity survived restart'
assert first['windows_boot_id']!=old_running['windows_boot_id'],'Windows boot ID did not change'
time.sleep(10)
last=running(current,after)
assert last['target']['created']==first['target']['created']
assert last['windows_boot_id']==first['windows_boot_id'] and last['interrupt_time_100ns']>first['interrupt_time_100ns']
assert all(b['CycleTime']>a['CycleTime'] for a,b in zip(first['cpus'],last['cpus']))
assert Path('/proc/sys/kernel/random/boot_id').read_text()==bootid
report('result',partition_bootstrap_passed=True,old_info_and_read_rejected=stale(old.fd) and stale_read(old),linux_boot_id=bootid.strip(),old_generation=old.generation,new_generation=generation,bootstrap=after,running_before=first,running_after=last,
 formal_lifecycle_acceptance=False,note='Requires independent CPU/workload/network evidence and repeated fault matrix')
os.close(old.fd);os.close(current.fd)
