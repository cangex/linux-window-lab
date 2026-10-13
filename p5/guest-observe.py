#!/usr/bin/env python3
"""Two independent observer processes, with no bootstrap state passed between."""
import argparse,json,subprocess,time,errno,fcntl,struct
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('profile');p.add_argument('output',type=Path);p.add_argument('--reject-generation',type=int,required=True);a=p.parse_args()
a.output.mkdir(parents=True,exist_ok=False);here=Path(__file__).resolve().parent
end=time.monotonic()+150
while time.monotonic()<end:
 s=dict(x.split('=',1) for x in Path('/sys/kernel/lwlab/status').read_text().split())
 if s.get('stage')=='3':break
 time.sleep(1)
else:raise TimeoutError('ExitBootServices not reached')
from observer import Physical
memory=Physical()
assert memory.generation!=a.reject_generation
try:
 fcntl.ioctl(memory.fd,0x40205741,struct.pack('<4Q',a.reject_generation,memory.extents[0][0],8,0))
except OSError as error:
 assert error.errno==errno.ESTALE
else:raise AssertionError('previous boot generation was accepted')
(a.output/'generation-guard.json').write_text(json.dumps(dict(previous=a.reject_generation,current=memory.generation,errno='ESTALE'))+'\n')
with (a.output/'comparison.jsonl').open('w') as f:
 result=subprocess.run(['python3',str(here/'observer.py'),a.profile,'--seconds','75','--compare-truth'],stdout=f,stderr=f)
assert result.returncode==0
rows=[json.loads(x) for x in (a.output/'comparison.jsonl').read_text().splitlines()]
truth=[x['truth'] for x in rows if x.get('event')=='sample' and 'truth' in x]
assert truth,'no internal truth comparison'
# The truth program's 90-second channel is revoked permanently for this boot.
time.sleep(max(0,100-truth[-1]['seconds']))
with (a.output/'independent.jsonl').open('w') as f:
 result=subprocess.run(['python3',str(here/'observer.py'),a.profile,'--seconds','65'],stdout=f,stderr=f)
assert result.returncode==0
print(json.dumps(dict(completed=True,generation=s['generation'],comparison_samples=len(truth),independent_process=True)))
