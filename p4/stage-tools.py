#!/usr/bin/env python3
"""Materialize the P3 coexistence harness plus the P4 Linux reader workload."""
import argparse,shutil
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args()
here=Path(__file__).resolve().parent
assert not a.output.exists();a.output.mkdir(parents=True)
for name in ('run-attempt.py','guest-probe.py','observe-winpe.py','visual_heartbeat.py','verify-attempt.py','install-guest.sh'):
 s=(here.parent/'p3'/name).read_text().replace('6.18.0-rc3-lwlab-p3','6.18.0-rc3-lwlab-p4').replace('artifacts/p3','artifacts/p4').replace('/opt/lwlab/results/p3','/opt/lwlab/results/p4')
 if name=='guest-probe.py':
  s=s.replace('import threading','import threading\nimport subprocess')
  s=s.replace('errors = []','errors = []\nreader = None\nreader_log = None')
  needle="            sample = dict(kind='sample'"
  replacement='''            if reader is None and current.get('stage') == '3':
                reader_log = (output / f'{generation}-reader.jsonl').open('w')
                reader = subprocess.Popen(['/opt/lwlab/bin/lwreader', '65'], stdout=reader_log, stderr=reader_log)
            sample = dict(kind='sample' '''
  s=s.replace(needle,replacement)
  s=s.replace("        taint = int", "        reader_exit = reader.poll() if reader else None\n        if reader and reader_exit is None:\n            reader.terminate(); reader_exit = reader.wait(timeout=5)\n        if reader_log: reader_log.close()\n        taint = int")
  s=s.replace('pass_=taint == 0,','pass_=taint == 0 and reader_exit == 0, reader_exit=reader_exit,')
 if name=='run-attempt.py':
  needle="(out / 'metadata.json').write_text"
  s=s.replace(needle,"run(['scp', '-i', key, 'lab@192.168.231.11:/opt/lwlab/results/p4/*-reader.jsonl', str(out)])\n"+needle)
 (a.output/name).write_text(s)
