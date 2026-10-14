#!/usr/bin/env python3
"""One experimental partition restart. Run only inside lwlab-boot with P6 r5.

Never power-cycle the outer VM. Failed quiescence aborts without preparing RAM.
"""
import argparse,errno,fcntl,json,os,socket,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'p5'))
from observer import Physical,bootstrap,Unavailable
p=argparse.ArgumentParser();p.add_argument('profile',type=Path);a=p.parse_args()
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
profile=json.loads(a.profile.read_text());bootid=Path('/proc/sys/kernel/random/boot_id').read_text()
old=Physical();before=bootstrap(old,profile);previous=state();report('before',state=previous,bootstrap=before,linux_boot_id=bootid.strip())
command('stop');stopped=state();report('stop',state=stopped)
assert stopped['state']=='stopped' and stopped['started']=='0'
assert stale(old.fd)
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
assert state()['state']=='loaded';assert stale(old.fd)
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
assert Path('/proc/sys/kernel/random/boot_id').read_text()==bootid
report('result',partition_bootstrap_passed=True,linux_boot_id=bootid.strip(),old_generation=old.generation,new_generation=generation,bootstrap=after,
 formal_lifecycle_acceptance=False,note='Requires independent CPU/workload/network evidence and repeated fault matrix')
os.close(old.fd);os.close(current.fd)
