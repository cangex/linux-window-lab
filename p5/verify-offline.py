#!/usr/bin/env python3
"""Compare helper-free samples with subsequently recovered cold-disk truth.

Clock alignment is required. A two-second margin covers traversal duration and
cross-OS timestamp uncertainty. Windows truth must remain unchanged across that
whole window; transition windows are excluded, not called matches.
"""
import argparse,bisect,json
from pathlib import Path

def verify(root):
 def rows(path):return [json.loads(x) for x in path.read_text().splitlines()]
 comparison=rows(root/'semantics/comparison.jsonl')
 nonces={f"{x['truth']['nonce']:016x}" for x in comparison if x.get('matches')}
 assert len(nonces)==1,'ambiguous Windows boot'
 truth=[x for x in rows(root/'offline-truth.jsonl') if x['nonce'] in nonces]
 assert len(truth)>100 and all(x['errors']==0 for x in truth)
 times=[x['time']/10_000_000-11644473600 for x in truth]
 assert all(b>a for a,b in zip(times,times[1:])), 'Windows wall clock changed'
 samples=[x for x in rows(root/'semantics/independent.jsonl') if x['event']=='sample']
 matched=0;excluded=0;mismatches=[];loaded=False;unloaded=False;children=set();absent=False
 keys=('pid','created','kernel','child','module','helper')
 for sample in samples:
  assert 'truth' not in sample,'independent phase contains helper data'
  lo=bisect.bisect_right(times,sample['time']-2)-1
  hi=bisect.bisect_left(times,sample['time']+2)
  if lo<0 or hi==len(times):excluded+=1;continue
  window=truth[lo:hi+1];a=window[0]
  if (any(times[j+1]-times[j]>2 for j in range(lo,hi)) or
      any(b['helper'] or any(a[k]!=b[k] for k in keys) for b in window)):
   excluded+=1;continue
  targets=[p for p in sample['processes'] if p['name'].lower()=='lwtruth.exe']
  live=[p['pid'] for p in sample['processes'] if p['name'].lower()=='lwchild.exe']
  modules=[m['base'] for m in sample['target_modules'] if m['name'].lower()=='lwlifecycle.dll']
  kernels=[m['base'] for m in sample['kernel_modules'] if m['name'].lower()=='ntoskrnl.exe']
  good=(len(targets)==1 and targets[0]['pid']==a['pid'] and targets[0]['created']==a['created']
   and live==([a['child']] if a['child'] else [])
   and modules==([int(a['module'],16)] if int(a['module'],16) else [])
   and kernels==[int(a['kernel'],16)])
  if not good:mismatches.append(dict(time=sample['time'],truth_seconds=a['seconds']));continue
  matched+=1;loaded|=bool(modules);unloaded|=not modules;children.update(live);absent|=not live
 assert matched>=20 and not mismatches,(matched,mismatches)
 assert loaded and unloaded and len(children)>=2 and absent
 return dict(passed=True,nonce=next(iter(nonces)),independent_candidates=len(samples),
  stable_matched=matched,transition_or_time_excluded=excluded,stable_mismatches=mismatches,
  truth_records=len(truth),last_truth_seconds=truth[-1]['seconds'],io_count=truth[-1]['io'],
  io_errors=0,helper_absent_for_matched_samples=True,child_pids=sorted(children),
  module_loaded_and_unloaded=True,process_absence_observed=True,
  consistency='stable truth across sample time +/- 2 seconds, log gaps <= 2 seconds; not atomic snapshots')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('attempt',type=Path);a=p.parse_args()
 result=verify(a.attempt)
 (a.attempt/'offline-result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result,indent=2))
