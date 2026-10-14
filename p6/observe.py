#!/usr/bin/env python3
"""Bounded long-run observer; independent bootstrap, no truth-page reads."""
import argparse,ctypes,errno,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'p5'))
from observer import Physical,Virtual,bootstrap,processes,modules,Unavailable
from windows_clock import read_clock,UnstableClock
p=argparse.ArgumentParser();p.add_argument('profile',type=Path);p.add_argument('--seconds',type=int,required=True)
p.add_argument('--cpus',type=int,choices=(1,2,4),required=True);p.add_argument('--interval',type=float,default=.5)
p.add_argument('--windows-clock',action='store_true');a=p.parse_args()
if a.seconds<=0 or a.interval<=0:p.error('positive duration and interval required')
clock=ctypes.CDLL(str(Path(__file__).with_name('clock.so')));clock.lw_tsc.restype=ctypes.c_uint64
profile=json.loads(a.profile.read_text());started=time.monotonic();boot=None
if a.windows_clock:
 for typ in ('_KUSER_SHARED_DATA','_KSYSTEM_TIME'):
  if typ not in profile['types']:raise ValueError('regenerate P6 profile with clock types')
while True:
 try:memory=Physical();break
 except OSError as error:
  if error.errno!=errno.EAGAIN or time.monotonic()-started>240:raise
  time.sleep(2)
discover_started=time.monotonic()
while boot is None:
 try:boot=bootstrap(memory,profile)
 except Unavailable:
  if time.monotonic()-discover_started>150:raise
  time.sleep(2)
print(json.dumps(dict(event='bootstrap',**boot,seconds=time.monotonic()-started,address_helper_used=False,physical_bytes=memory.bytes)),flush=True)
v=Virtual(memory,boot['cr3']);off=profile['types']['_KPRCB']['fields'];kernel=boot['kernel']
end=time.monotonic()+a.seconds;valid=unavailable=0
while time.monotonic()<end:
 begin=time.monotonic_ns();tsc_begin=clock.lw_tsc();before=memory.bytes;calls=memory.calls
 windows_begin=windows_end=None
 try:
  if a.windows_clock:
   seed=next((x for x in processes(memory,profile,boot) if x['name'].lower()=='lwtruth.exe'),None)
   if not seed:raise Unavailable('workload process absent')
   cv=Virtual(memory,seed['cr3']);windows_begin=read_clock(cv,profile,boot['build'])
  ps=processes(memory,profile,boot);target=next((x for x in ps if x['name'].lower()=='lwtruth.exe'),None)
  if not target:raise Unavailable('workload process absent')
  if a.windows_clock and any(target[k]!=seed[k] for k in ('pid','created','address','cr3')):raise Unavailable('workload identity changed')
  us=modules(memory,profile,boot,target);ks=modules(memory,profile,boot)
  assert v.u32(kernel+profile['symbols']['KeNumberProcessors'])==a.cpus
  cpu_rows=[]
  for i in range(a.cpus):
   prcb=v.u64(kernel+profile['symbols']['KiProcessorBlock']+8*i)
   cpu={k:(v.u64 if k in ('CurrentThread','CycleTime') else v.u32)(prcb+o) for k,o in off.items()}
   assert cpu['Number']==i and cpu['InitialApicId']==4+i
   cpu_rows.append(cpu)
  if a.windows_clock:
   windows_end=read_clock(cv,profile,boot['build'])
   if windows_end<windows_begin:raise UnstableClock('clock moved backward during sample')
  row=dict(event='sample',generation=memory.generation,target=target,
   children=[x for x in ps if x['name'].lower()=='lwchild.exe'],
   module=next((x['base'] for x in us if x['name'].lower()=='lwlifecycle.dll'),0),
   kernel_module=next(x for x in ks if x['name'].lower()=='ntoskrnl.exe'),
   process_count=len(ps),kernel_module_count=len(ks),cpus=cpu_rows)
  valid+=1
 except (Unavailable,UnstableClock,UnicodeError,StopIteration) as error:
  unavailable+=1;row=dict(event='unavailable',reason=str(error),generation=memory.generation)
 row.update(monotonic_begin=begin,monotonic_end=time.monotonic_ns(),tsc_begin=tsc_begin,
  tsc_end=clock.lw_tsc(),wall=time.time(),windows_begin=windows_begin,windows_end=windows_end,
  physical_calls=memory.calls-calls,physical_bytes=memory.bytes-before)
 print(json.dumps(row),flush=True)
 time.sleep(max(0,a.interval-(time.monotonic_ns()-begin)/1e9))
print(json.dumps(dict(event='result',valid_samples=valid,unavailable=unavailable,
 generation=memory.generation,address_helper_used=False)),flush=True)
if not valid:raise SystemExit(1)
