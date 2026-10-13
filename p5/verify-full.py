#!/usr/bin/env python3
"""Fail closed when full Windows, truth, independent discovery or lifecycle is absent."""
import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('attempt',type=Path);p.add_argument('--minimum-seconds',type=int,default=180);a=p.parse_args()
r=a.attempt
linux=json.loads((r/'result.json').read_text());meta=json.loads((r/'metadata.json').read_text())
assert linux['pass'] and linux['elapsed']>=a.minimum_seconds and linux['guest']['kernel_taint']==0
assert not linux['guest']['start_errors'] and meta['windows_observer_exit']==0
assert meta['guest_exit']==0 and meta['observer_exit']==0 and meta['boot_id']==linux['boot_id']
gen=linux['guest']['generation']
guard=json.loads((r/'semantics/generation-guard.json').read_text())
assert guard['current']==gen and guard['previous']!=gen and guard['errno']=='ESTALE'
def load(name):return [json.loads(x) for x in (r/'semantics'/name).read_text().splitlines()]
compare=load('comparison.jsonl');independent=load('independent.jsonl')
for rows in (compare,independent):
 boot=next(x for x in rows if x['event']=='bootstrap')
 assert boot['generation']==gen and not boot['address_helper_used'] and boot['build']==26100
 assert boot['pdb']=='953A8DE880B0818C32DA2DEC1D79C2D91'
 assert rows[-1]['event']=='result' and rows[-1]['valid_samples']>0
samples=[x for x in compare if x['event']=='sample'];accepted=[x for x in samples if x['matches']]
assert len(accepted)>=10,'insufficient truth comparisons'
assert all(x['truth']['errors']==0 for x in accepted)
standalone=[x for x in independent if x['event']=='sample'];assert len(standalone)>=30
assert all('truth' not in x for x in standalone)
children=set();absent=False;loaded=False;unloaded=False;full=False
for x in standalone:
 assert x['generation']==gen
 ps=x['processes'];names={i['name'].lower() for i in ps}
 assert 'lwtruth.exe' in names and 'winpeshl.exe' not in names
 full|='explorer.exe' in names
 live=[i for i in ps if i['name'].lower()=='lwchild.exe']
 children.update((i['pid'],i['created'],i['address']) for i in live);absent|=not live
 has=any(i['name'].lower()=='lwlifecycle.dll' for i in x['target_modules']);loaded|=has;unloaded|=not has
 assert any(i['name'].lower()=='ntoskrnl.exe' for i in x['kernel_modules'])
assert full and len(children)>=2 and absent and loaded and unloaded
# P3's inherited launcher has unpopulated WinPE-only status placeholders.
# Preserve raw metadata on disk, but do not present them as P5 conclusions.
meta={k:v for k,v in meta.items() if k not in ('windows_userspace_confirmed','coexistence_passed')}
out=dict(passed=True,scope='same-VM Linux and full Windows, one Windows CPU',generation=gen,
 boot_id=linux['boot_id'],linux_seconds=linux['elapsed'],ping_failures=linux['ping_failures'],
 generation_guard=guard,matched_samples=len(accepted),comparison_candidates=len(samples),
 temporally_unmatched_samples=len(samples)-len(accepted),independent_samples=len(standalone),
 child_identities=[list(x) for x in sorted(children)],process_absence_observed=absent,
 module_load_observed=loaded,module_unload_observed=unloaded,full_desktop_process_observed=full,
 independent_bootstrap=next(x for x in independent if x['event']=='bootstrap'),metadata=meta)
(r/'p5-result.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
