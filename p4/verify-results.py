#!/usr/bin/env python3
"""Validate reader evidence against this boot's independently checked coexistence."""
import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('attempt',type=Path);a=p.parse_args()
root=a.attempt
linux=json.loads((root/'result.json').read_text())
co=json.loads((root/'coexistence.json').read_text())
meta=json.loads((root/'metadata.json').read_text())
gen=linux['guest']['generation']
rows=[json.loads(s) for s in (root/f'{gen}-reader.jsonl').read_text().splitlines()]
guards=next(r for r in rows if r['event']=='guards')
r=rows[-1]
assert r['event']=='result' and r['passed'] and r['generation']==gen
assert r['attempts']>=1_000_000 and r['accepted']>0 and r['bad_payload']==0
assert r['attempts']==sum(r[k] for k in ('accepted','busy','torn','revoked','invalid','bad_payload'))
assert r['busy']>0 and r['revoked']>0 and r['epochs']>=2
assert all(guards[k] for k in ('stale_generation','out_of_range','write_denied'))
assert linux['pass'] and linux['guest']['reader_exit']==0 and linux['guest']['kernel_taint']==0
assert co['passed']
assert linux['boot_id']==meta['boot_id']==co['linux']['boot_id']
assert co['linux']['guest']['generation']==gen
assert sum(r['latency_log2_ns'])==r['attempts']
def quantile(q):
 n=0
 for k,v in enumerate(r['latency_log2_ns']):
  n+=v
  if n>=r['attempts']*q:return [2**k,2**(k+1)]
out=dict(reader=r,guards=guards,boot_id=linux['boot_id'],metadata=meta,
 acceptance_fraction=r['accepted']/r['attempts'],
 cpu_core_fraction=r['cpu_seconds']/r['seconds'],
 latency_ns_bucket={str(q):quantile(q) for q in (.5,.95,.99)},
 linux_seconds=linux['elapsed'],max_tcp_gap_seconds=linux['max_tcp_gap_seconds'],
 ping_failures=linux['ping_failures'],coexistence_passed=True)
print(json.dumps(out,indent=2))
