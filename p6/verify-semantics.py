#!/usr/bin/env python3
"""Offline comparison using sample brackets in Windows' system clock.

Truth is read only after collection from the cold owned disk. The observer never
receives it. Stable-window comparison is not an atomic snapshot guarantee.
"""
import argparse,bisect,json,math
from pathlib import Path

def verify(truth,observations,nonce,minimum=1000,coverage=.8,margin_ms=50):
 truth=[x for x in truth if x['nonce']==nonce]
 if len(truth)<2:raise ValueError('missing truth instance')
 if any(x.get('helper') is not False or x['errors'] for x in truth):raise ValueError('helper mode or workload errors')
 times=[x['time'] for x in truth]
 if any(b<=a for a,b in zip(times,times[1:])):raise ValueError('truth clock not increasing')
 samples=[x for x in observations if x['event'] in ('sample','unavailable')]
 boot=[x for x in observations if x['event']=='bootstrap']
 if len(boot)!=1 or boot[0].get('address_helper_used') is not False:raise ValueError('independent bootstrap required')
 generation=boot[0]['generation'];matched=excluded=unavailable=0;mismatches=[];latencies=[];previous=None
 keys=('pid','created','child','module','events','helper');margin=round(margin_ms*10000)
 for index,s in enumerate(samples):
  if s['generation']!=generation:raise ValueError('mixed partition generations')
  if s['event']=='unavailable':unavailable+=1;continue
  begin,end=s.get('windows_begin'),s.get('windows_end')
  if not isinstance(begin,int) or not isinstance(end,int) or end<begin:raise ValueError('missing or invalid Windows clock bracket')
  if previous:
   elapsed=(end-previous['windows_end'])/10000000
   linux_elapsed=(s['monotonic_end']-previous['monotonic_end'])/1e9
   if elapsed<0 or abs(elapsed-linux_elapsed)>.25:raise ValueError('Windows/Linux clock progression differs; calibration invalid')
  previous=s
  lo=bisect.bisect_right(times,begin-margin)-1;hi=bisect.bisect_left(times,end+margin)
  if lo<0 or hi>=len(times):excluded+=1;continue
  window=truth[lo:hi+1];a=window[0]
  if any(times[i+1]-times[i]>20000000 for i in range(lo,hi)) or any(any(x[k]!=a[k] for k in keys) for x in window):
   excluded+=1;continue
  target=s['target'];children=[x['pid'] for x in s['children']]
  good=(target['pid']==a['pid'] and target['created']==a['created'] and target['generation']==generation
        and children==([a['child']] if a['child'] else []) and s['module']==a['module']
        and s['kernel_module']['base']==boot[0]['kernel'])
  if not good:mismatches.append(index)
  else:matched+=1
  latencies.append((s['monotonic_end']-s['monotonic_begin'])/1e6)
 if not samples:raise ValueError('no observations')
 def percentile(q):
  values=sorted(latencies);return values[max(0,math.ceil(q*len(values))-1)] if values else None
 ratio=matched/len(samples)
 return dict(passed=matched>=minimum and ratio>=coverage and not mismatches,nonce=nonce,generation=generation,
  requests=len(samples),valid_outputs=len(samples)-unavailable,stable_matched=matched,excluded=excluded,
  unavailable=unavailable,mismatches=mismatches,coverage=ratio,required_stable=minimum,required_coverage=coverage,
  clock_margin_ms=margin_ms,clock_method='Windows shared system-time brackets, pinned PDB; monotonic progression cross-check',
  sample_latency_ms=dict(p50=percentile(.5),p95=percentile(.95),p99=percentile(.99)),
  formal_p6_acceptance=False,note='Runtime clock/profile validation and remaining lifecycle/load matrix are separate requirements')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('truth',type=Path);p.add_argument('observations',type=Path);p.add_argument('--nonce',required=True)
 p.add_argument('--minimum',type=int,default=1000);p.add_argument('--coverage',type=float,default=.8);p.add_argument('--clock-margin-ms',type=float,default=50);a=p.parse_args()
 if a.minimum<1 or not 0<a.coverage<=1 or a.clock_margin_ms<0:p.error('invalid acceptance limits')
 def rows(path):return [json.loads(x) for x in path.read_text(encoding='utf-8-sig').splitlines() if x.strip()]
 result=verify(rows(a.truth),rows(a.observations),a.nonce,a.minimum,a.coverage,a.clock_margin_ms)
 print(json.dumps(result,indent=2));raise SystemExit(0 if result['passed'] else 1)
