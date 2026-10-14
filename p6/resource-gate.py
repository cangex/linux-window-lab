#!/usr/bin/env python3
"""Read-only admission check on the Linux host; no VM or host mutations."""
import argparse,json,time
from pathlib import Path

def assess(sample):
 reasons=[]
 for key,limit in [('available_gib',128),('free_gib',64),('disk_free_gib',80)]:
  if sample[key]<limit:reasons.append(key)
 if sample['psi_some_avg10']>=1:reasons.append('memory_psi')
 if min(sample['node_free_gib'].values(),default=0)<4:reasons.append('node_free_gib')
 return reasons

def stable(history,now,seconds=600):
 recent=[x for x in history if 0<=now-x['time']<=seconds+90]
 # Include the closest sample at/before the window boundary, not every older
 # sample in the lookback allowance. Otherwise a failure outside the required
 # window incorrectly delays admission by another sampling interval.
 anchors=[i for i,x in enumerate(recent) if now-x['time']>=seconds]
 if not anchors:return False
 recent=recent[anchors[-1]:]
 if now-recent[-1]['time']>90:return False
 return all(not x['reasons'] for x in recent) and all(0<b['time']-a['time']<=90 for a,b in zip(recent,recent[1:]))

def main():
 import shutil
 p=argparse.ArgumentParser();p.add_argument('--history',type=Path,required=True);p.add_argument('--disk',type=Path,default=Path('/data/linux-window-lab'));a=p.parse_args()
 m={x.split(':')[0]:int(x.split()[1])/1048576 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith(('MemAvailable:','MemFree:'))}
 psi=Path('/proc/pressure/memory').read_text().splitlines()[0]
 nodes={x.parent.name:float(next(l.split()[3] for l in x.read_text().splitlines() if 'MemFree:' in l))/1048576 for x in Path('/sys/devices/system/node').glob('node*/meminfo')}
 row=dict(time=time.time(),available_gib=m['MemAvailable'],free_gib=m['MemFree'],psi_some_avg10=float(psi.split()[1].split('=')[1]),node_free_gib=nodes,disk_free_gib=shutil.disk_usage(a.disk).free/2**30)
 row['reasons']=assess(row)
 history=[json.loads(x) for x in a.history.read_text().splitlines()] if a.history.exists() else []
 history=[x for x in history if 0<=row['time']-x['time']<=900]+[row]
 row['admit']=stable(history,row['time'])
 a.history.parent.mkdir(parents=True,exist_ok=True)
 a.history.write_text(''.join(json.dumps(x)+'\n' for x in history))
 print(json.dumps(row),flush=True)
 raise SystemExit(0 if row['admit'] else 75)
if __name__=='__main__':main()
