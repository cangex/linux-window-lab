#!/usr/bin/env python3
"""Collect a bounded P6 attempt in an already booted, idle r5 Linux VM.

Does not claim workload/semantic acceptance: validate recovered cold-disk truth
separately. Default cleanup shuts down the outer VM, never counts as recovery.
"""
import argparse,hashlib,importlib.util,json,shlex,subprocess,time
import xml.etree.ElementTree as ET
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('name');p.add_argument('--seconds',type=int,required=True)
p.add_argument('--cpus',type=int,choices=(1,2,4),required=True);p.add_argument('--no-observe',action='store_true')
p.add_argument('--windows-clock',action='store_true');p.add_argument('--keep-running',action='store_true')
p.add_argument('--previous-truth',type=Path);a=p.parse_args()
if a.no_observe and not a.previous_truth:p.error('observer-off runs require verified previous cold truth')
if not a.name.replace('-','').replace('_','').isalnum() or a.seconds<30:p.error('valid attempt name and >=30 seconds required')
root=Path('/data/linux-window-lab');repo=root/'repo';out=root/'artifacts/p6'/a.name
assert not out.exists();out.mkdir()
spec=importlib.util.spec_from_file_location('gate',repo/'p6/resource-gate.py');gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
def latest(admission=False):
 rows=[json.loads(x) for x in (root/'artifacts/p6/resource-history.jsonl').read_text().splitlines()]
 if not rows or not 0<=time.time()-rows[-1]['time']<=90 or rows[-1].get('policy')!=gate.POLICY or gate.assess(rows[-1]):raise RuntimeError('host resource gate unavailable/failed')
 if admission and not gate.stable(rows,time.time()):raise RuntimeError('continuous admission window incomplete')
 return rows[-1]
def run(args,**kw):return subprocess.run(list(map(str,args)),check=True,text=True,capture_output=True,timeout=120,**kw)
ssh=['ssh','-i',str(root/'keys/guest_ed25519'),'-o','BatchMode=yes','-o','ConnectTimeout=8','lab@192.168.231.11']
def guest(command):return run(ssh+[command]).stdout
processes=[];files=[];failure=None;started=False;shutdown_requested=False;domain_state=None
try:
 latest(True)
 assert guest('uname -r').strip()=='6.18.0-rc3-lwlab-p6'
 assert guest('sha256sum /boot/vmlinuz-6.18.0-rc3-lwlab-p6').split()[0]=='6309c7f909e2205f96d9d9caca5b928b6e4495b3a878826c381c42d1dc24108c'
 assert guest('cat /sys/kernel/lwlab/status').startswith('state=idle ')
 firmware=guest('sha256sum /lib/firmware/lwlab/partition-p3.bin').split()[0]
 assert firmware==json.loads((repo/'p6/firmware-sha256.json').read_text())[str(a.cpus)],'CPU-specific firmware mismatch'
 xml=run(['sudo','-n','virsh','dumpxml','lwlab-boot']).stdout
 assert '/state-p6/windows.qcow2' in xml,'dedicated P6 disk clone required'
 tuning=ET.fromstring(xml).find('numatune')
 assert tuning is not None and tuning.find('memory').get('nodeset')==gate.NODESET,'VM NUMA policy mismatch'
 assert tuning.find('memory').get('mode')=='interleave'
 assert all(x.get('nodeset')==gate.NODESET for x in tuning.findall('memnode')),'per-cell NUMA policy mismatch'
 (out/'vm.xml').write_text(xml)
 profile=root/'artifacts/p6/p6-cpu-profile.json'
 if a.windows_clock:
  assert '_KUSER_SHARED_DATA' in json.loads(profile.read_text())['types'],'regenerate clock profile first'
 guest('mkdir -p /tmp/p6-run/p5 /tmp/p6-run/p6')
 run(['cc','-shared','-fPIC','-O2',repo/'p6/clock.c','-o',out/'clock.so'])
 run(['scp','-i',root/'keys/guest_ed25519',repo/'p5/observer.py','lab@192.168.231.11:/tmp/p6-run/p5/'])
 run(['scp','-i',root/'keys/guest_ed25519',*[repo/'p6'/n for n in ('guest-probe.py','observe.py','windows_clock.py')],out/'clock.so',profile,'lab@192.168.231.11:/tmp/p6-run/p6/'])
 bootid=guest('cat /proc/sys/kernel/random/boot_id').strip()
 before=dict(boot_id=bootid,cpus=a.cpus,seconds=a.seconds,observer_enabled=not a.no_observe,windows_clock=a.windows_clock,firmware=firmware,cmdline=guest('cat /proc/cmdline'))
 if a.previous_truth:
  data=a.previous_truth.read_bytes()
  before.update(truth_nonces_before=sorted({json.loads(x)['nonce'] for x in data.decode('utf-8-sig').splitlines() if x.strip()}),previous_truth_sha256=hashlib.sha256(data).hexdigest())
 (out/'before.json').write_text(json.dumps(before))
 def launch(command,path):
  f=path.open('w');files.append(f);proc=subprocess.Popen(command,stdout=f,stderr=f);processes.append(proc);return proc
 linux=launch(ssh+[f'sudo timeout {a.seconds+400} python3 /tmp/p6-run/p6/guest-probe.py --seconds {a.seconds+240}'],out/'linux-guest.log');started=True
 stream=launch(['python3',str(repo/'p1/host-observe.py'),'--output',str(out/'linux')],out/'linux-host.log')
 observe=None
 if not a.no_observe:
  command=f'sudo timeout {a.seconds+400} python3 /tmp/p6-run/p6/observe.py /tmp/p6-run/p6/p6-cpu-profile.json --seconds {a.seconds} --cpus {a.cpus}'
  if a.windows_clock:command+=' --windows-clock'
  observe=launch(ssh+[command],out/'observations.jsonl')
 deadline=time.monotonic()+a.seconds+480;checked=0
 with (out/'resources.jsonl').open('w') as resources:
  while any(x.poll() is None for x in processes):
   if time.monotonic()>deadline:raise TimeoutError('attempt collection deadline exceeded')
   if any(x.poll() not in (None,0) for x in processes):raise RuntimeError('collector failed; inspect logs')
   if time.monotonic()-checked>=30:
    resources.write(json.dumps(latest())+'\n');resources.flush();checked=time.monotonic()
   time.sleep(2)
 assert all(x.returncode==0 for x in processes)
 assert guest('cat /proc/sys/kernel/random/boot_id').strip()==bootid
except BaseException as exc:
 failure=repr(exc)
finally:
 if started:
  for name,command in [('dmesg.txt','sudo dmesg'),('status.txt','cat /sys/kernel/lwlab/status')]:
   try:(out/name).write_text(guest(command))
   except Exception as exc:(out/(name+'.error')).write_text(repr(exc))
  if failure or not a.keep_running:
   shutdown_requested=True
   try:
    subprocess.run(ssh+['sudo poweroff'],capture_output=True,timeout=30)
    domain_state=run(['sudo','-n','virsh','domstate','lwlab-boot']).stdout.strip()
   except Exception as exc:failure=(failure or '')+'; shutdown/check failed: '+repr(exc)
 for proc in processes:
  if proc.poll() is None:proc.terminate()
 for f in files:f.close()
 (out/'collection-result.json').write_text(json.dumps(dict(collection_passed=failure is None,error=failure,
   formal_p6_acceptance=False,cold_truth_verification_required=True,outer_vm_shutdown_requested=shutdown_requested,
   outer_vm_state=domain_state),indent=2)+'\n')
if failure:raise SystemExit(failure)
print(str(out),flush=True)
