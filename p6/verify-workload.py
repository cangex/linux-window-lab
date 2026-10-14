#!/usr/bin/env python3
"""Verify cold-disk workload progress; does not certify external semantics."""
import argparse,json
from pathlib import Path

def verify(rows,cpus,minimum_seconds,max_gap=60):
 if len(rows)<2:raise ValueError('at least two complete truth records required')
 first=rows[0];identity=tuple(first[k] for k in ('nonce','pid','created'))
 last_progress=[first['seconds']]*(cpus+1);worst=[0]*(cpus+1)
 child_starts=child_ends=dll_loads=dll_unloads=0
 previous=None
 for row in rows:
  if row.get('schema')!=1 or row.get('helper') is not False:raise ValueError('unsupported schema or helper mode')
  if tuple(row[k] for k in ('nonce','pid','created'))!=identity:raise ValueError('mixed workload instances')
  if row['errors'] or any(c['errors'] for c in row['cpus']):raise ValueError('workload validation error')
  if [c['cpu'] for c in row['cpus']]!=list(range(cpus)):raise ValueError('CPU worker set mismatch')
  current=[row['io']]+[c['loops'] for c in row['cpus']]
  if previous:
   if row['seconds']<=previous['seconds'] or row['time']<=previous['time']:raise ValueError('nonmonotonic truth clock')
   old=[previous['io']]+[c['loops'] for c in previous['cpus']]
   for i,(a,b) in enumerate(zip(old,current)):
    if b<a:raise ValueError('progress counter regressed')
    worst[i]=max(worst[i],row['seconds']-last_progress[i])
    if b>a:last_progress[i]=row['seconds']
   child_starts+=bool(row['child'] and row['child']!=previous['child'])
   child_ends+=bool(previous['child'] and row['child']!=previous['child'])
   dll_loads+=bool(row['module'] and not previous['module'])
   dll_unloads+=bool(previous['module'] and not row['module'])
  previous=row
 elapsed=rows[-1]['seconds']-first['seconds']
 if elapsed<minimum_seconds:raise ValueError(f'insufficient duration: {elapsed} < {minimum_seconds}')
 if max(worst)>max_gap:raise ValueError(f'progress/log gap exceeds {max_gap}s: {worst}')
 deltas=[rows[-1]['io']-first['io']]+[b['loops']-a['loops'] for a,b in zip(first['cpus'],rows[-1]['cpus'])]
 if any(x<=0 for x in deltas):raise ValueError('one or more workers made no progress')
 return dict(workload_passed=True,external_semantics_verified=False,nonce=identity[0],pid=identity[1],created=identity[2],
  seconds=elapsed,records=len(rows),io_operations=deltas[0],cpu_loops=deltas[1:],maximum_progress_gaps_seconds=worst,
  child_starts=child_starts,child_ends=child_ends,dll_loads=dll_loads,dll_unloads=dll_unloads,errors=0)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('truth',type=Path);p.add_argument('--nonce',required=True)
 p.add_argument('--cpus',type=int,choices=(1,2,4),required=True);p.add_argument('--minimum-seconds',type=int,required=True)
 p.add_argument('--max-progress-gap',type=int,default=60);a=p.parse_args()
 if a.minimum_seconds<=0 or a.max_progress_gap<=0:p.error('positive duration and gap required')
 rows=[json.loads(x) for x in a.truth.read_text(encoding='utf-8-sig').splitlines() if x.strip()]
 print(json.dumps(verify([x for x in rows if x['nonce']==a.nonce],a.cpus,a.minimum_seconds,a.max_progress_gap),indent=2))
