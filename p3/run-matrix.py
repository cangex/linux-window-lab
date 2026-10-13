#!/usr/bin/env python3
"""Ten cold boots, including >= 30 minutes of simultaneous userspace evidence."""
import argparse
import json
from pathlib import Path
import subprocess

p=argparse.ArgumentParser()
p.add_argument('firmware',type=Path)
p.add_argument('--prefix',default='acceptance')
p.add_argument('--root',type=Path,default=Path('/data/linux-window-lab'))
a=p.parse_args()
assert a.prefix.replace('-','').replace('_','').isalnum()
results=[]
for n in range(1,11):
    name=f'{a.prefix}-{n:02d}'
    seconds, minimum = (1900,1800) if n==1 else (90,30)
    print(f'START {name} seconds={seconds}',flush=True)
    subprocess.run(['python3',str(Path(__file__).with_name('run-attempt.py')),str(a.firmware),name,
                    '--root',str(a.root),'--seconds',str(seconds),'--minimum-seconds',str(minimum)],check=True)
    result=json.loads((a.root/'artifacts/p3'/name/'coexistence.json').read_text())
    results.append(dict(name=name,**result))
    print(f'PASS {name}',flush=True)
assert all(r['passed'] for r in results)
assert len({r['linux']['boot_id'] for r in results})==10
assert len({r['linux']['guest']['generation'] for r in results})==10
assert len({r['windows']['nonce'] for r in results})==10
assert len({r['firmware_sha256'] for r in results})==1
assert len({r['kernel_sha256'] for r in results})==1
assert results[0]['windows']['simultaneous_seconds']>=1800
report=dict(passed=True,cold_boots=10,scope='QEMU/KVM, same VM, Linux CPU0-3 + WinPE CPU4',
    windows_smp_tested=False,bare_metal_tested=False,runs=results)
(a.root/'artifacts/p3'/f'{a.prefix}-summary.json').write_text(json.dumps(report,indent=2)+'\n')
print('P3 MATRIX PASS',flush=True)
