#!/usr/bin/env python3
"""Observe Windows PRCB CPU identity and time counters through Linux only."""
import argparse,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'p5'))
from observer import Physical,Virtual,bootstrap
p=argparse.ArgumentParser();p.add_argument('profile',type=Path);p.add_argument('--cpus',type=int,choices=(1,2,4),required=True);p.add_argument('--seconds',type=int,default=30);a=p.parse_args()
c=json.loads(a.profile.read_text());memory=Physical();boot=bootstrap(memory,c);v=Virtual(memory,boot['cr3']);kernel=boot['kernel'];off=c['types']['_KPRCB']['fields']
assert v.u32(kernel+c['symbols']['KeNumberProcessors'])==a.cpus
print(json.dumps(dict(event='bootstrap',**boot,address_helper_used=False)),flush=True)
first=None;last=None;end=time.monotonic()+a.seconds
while time.monotonic()<end:
 rows=[]
 for i in range(a.cpus):
  prcb=v.u64(kernel+c['symbols']['KiProcessorBlock']+i*8)
  row={k:(v.u64 if k in ('CurrentThread','CycleTime') else v.u32)(prcb+o) for k,o in off.items()}
  assert row['Number']==i and row['InitialApicId']==i+4
  rows.append(row)
 first=first or rows;last=rows
 print(json.dumps(dict(event='cpus',generation=memory.generation,monotonic=time.monotonic(),rows=rows)),flush=True);time.sleep(1)
assert all(b['KernelTime']+b['UserTime']>x['KernelTime']+x['UserTime'] for x,b in zip(first,last))
print(json.dumps(dict(event='result',passed=True,cpus=a.cpus,generation=memory.generation,per_cpu_time_advanced=True)),flush=True)
