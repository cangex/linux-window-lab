#!/usr/bin/env python3
"""Combine independent Linux continuity and WinPE userspace evidence."""
import argparse
import json
from pathlib import Path
from visual_heartbeat import validate_progress
p=argparse.ArgumentParser()
p.add_argument('directory',type=Path)
p.add_argument('--minimum-seconds',type=int,default=30)
a=p.parse_args()
out=a.directory
linux=json.loads((out/'result.json').read_text())
meta=json.loads((out/'metadata.json').read_text())
stream=[json.loads(s) for s in (out/'stream.jsonl').read_text().splitlines()]
frames=[json.loads(s) for s in (out/'windows.jsonl').read_text().splitlines()]
valid=[f for f in frames if f['kind']=='sample']
win=validate_progress(valid,stream[0]['received_monotonic'],stream[-1]['received_monotonic'],a.minimum_seconds)
uefi=(out/'uefi.log').read_text(errors='replace')
errors=[]
if not linux['pass']: errors.append('Linux continuity failed')
if meta['guest_exit']!=0 or meta['observer_exit']!=0 or meta['windows_observer_exit']!=0: errors.append('Observer or guest failed')
if linux['guest']['start_errors'] or not linux['guest']['launch_finished']: errors.append('AP launch failed')
final=linux['guest']['final'] or {}
if final.get('stage')!='3' or final.get('actual_apic')!='4' or final.get('ack_generation')!=str(linux['guest']['generation']): errors.append('Final partition handshake mismatch')
if not win['passed']: errors.extend(win['errors'])
if 'LWLAB P3 ExitBootServices returned Success' not in uefi: errors.append('Successful ExitBootServices trace absent')
result=dict(passed=not errors,errors=errors,scope='same-VM single-AP WinPE/Linux coexistence',
    linux=linux,windows=win,unavailable_captures=len(frames)-len(valid),
    firmware_sha256=meta['firmware_sha256'],kernel_sha256=meta['kernel_sha256'])
(out/'coexistence.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
raise SystemExit(0 if result['passed'] else 1)
