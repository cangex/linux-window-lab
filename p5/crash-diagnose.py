#!/usr/bin/env python3
"""Host QMP post-stop diagnostics only. Never used as acceptance observation.

Requires the AP parked in failed state; bounded physical reads remain within
Windows RAM. Page caching is appropriate only while that Windows CPU is stopped.
"""
import argparse,json,re,struct,subprocess
from pathlib import Path
from observer import Virtual,modules
p=argparse.ArgumentParser();p.add_argument('profile',type=Path);p.add_argument('bootstrap',type=Path);a=p.parse_args()
profile=json.loads(a.profile.read_text());boot=json.loads(a.bootstrap.read_text().splitlines()[0])
status=subprocess.check_output(['ssh','-i','/data/linux-window-lab/keys/guest_ed25519','lab@192.168.231.11','cat /sys/kernel/lwlab/status'],text=True)
s=dict(x.split('=',1) for x in status.split());assert s['stage']=='255' and int(s['generation'])==boot['generation']
class Frozen:
 def __init__(self):self.cache={};self.generation=boot['generation']
 def owns(self,a,n):return any(a>=b and a+n<=b+z for b,z in [(0x10000000,0x60000000),(0x100000,0xf00000),(0x50000,0x20000),(0x280000000,0x180000000)])
 def read(self,a,n):
  assert self.owns(a,n)
  page=a&~4095
  if n>4096-(a&4095):
   take=4096-(a&4095);return self.read(a,take)+self.read(a+take,n-take)
  if page not in self.cache:
   text=subprocess.check_output(['sudo','-n','virsh','qemu-monitor-command','lwlab-boot','--hmp',f'xp /4096bx 0x{page:x}'],text=True)
   data=bytes(int(x,16) for x in re.findall(r'0x([0-9a-fA-F]{2})\b',text));assert len(data)==4096
   self.cache[page]=data
  return self.cache[page][a-page:a-page+n]
 def u64(self,a):return struct.unpack('<Q',self.read(a,8))[0]
memory=Frozen();v=Virtual(memory,boot['cr3'])
bug=struct.unpack('<5Q',v.read(boot['kernel']+profile['symbols']['KiBugCheckData'],40))
print(json.dumps(dict(event='bugcheck',parameters=[hex(x) for x in bug],source='QMP post-stop diagnostics only')),flush=True)
try:print(json.dumps(dict(event='boot_device',name=v.string(bug[1]))),flush=True)
except Exception as e:print(json.dumps(dict(event='boot_device',error=str(e))))
print(json.dumps(dict(event='modules',names=[x['name'] for x in modules(memory,profile,boot)])),flush=True)
offset=profile['types']['_DEVICE_NODE']['fields'];root=v.u64(boot['kernel']+profile['symbols']['IopRootDeviceNode']);pending=[root];seen=set()
while pending:
 node=pending.pop()
 if not node or node in seen:continue
 assert len(seen)<512;seen.add(node)
 row=dict(event='device',address=hex(node))
 for name in ('InstancePath','ServiceName'):
  try:row[name]=v.string(node+offset[name])
  except Exception as e:row[name]=str(e)
 for name in ('State','Problem','ProblemStatus'):
  if name in offset:row[name]=hex(v.u32(node+offset[name]))
 print(json.dumps(row),flush=True)
 pending += [v.u64(node+offset['Child']),v.u64(node+offset['Sibling'])]
