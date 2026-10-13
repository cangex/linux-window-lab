#!/usr/bin/env python3
"""Generate the Linux continuity harness; WinPE smoke is separately identified."""
import argparse
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('--full',action='store_true');a=p.parse_args()
assert not a.output.exists();a.output.mkdir(parents=True)
here=Path(__file__).resolve().parent
for name in ('run-attempt.py','guest-probe.py','observe-winpe.py','visual_heartbeat.py','verify-attempt.py'):
 s=(here.parent/'p3'/name).read_text().replace('6.18.0-rc3-lwlab-p3','6.18.0-rc3-lwlab-p5').replace('artifacts/p3','artifacts/p5').replace('/opt/lwlab/results/p3','/opt/lwlab/results/p5')
 if name=='guest-probe.py':
  s=s.replace("generation = secrets.randbelow",'''# Remove Linux's service driver from the dedicated port before AP ownership.
endpoint = Path('/sys/bus/pci/devices/0000:81:00.0')
assert (endpoint / 'driver').resolve().name == 'pci-stub'
resources = [tuple(int(x,16) for x in line.split()[:2]) for line in Path('/sys/bus/pci/devices/0000:80:00.0/resource').read_text().splitlines()]
assert resources[0] == (0x82000000,0x82000fff)
assert resources[8] == (0x81e00000,0x81ffffff)
assert resources[9] == (0x383000000000,0x3837ffffffff)
port = Path('/sys/bus/pci/devices/0000:80:00.0/driver')
if port.exists():
    assert port.resolve().name == 'pcieport'
    write(str(port / 'unbind'), '0000:80:00.0\\n')
generation = secrets.randbelow''')
 (a.output/name).write_text(s)
if a.full:
 f=a.output/'run-attempt.py';s=f.read_text()
 old="windows = subprocess.Popen(['python3', str(Path(__file__).with_name('observe-winpe.py')), str(out), '--seconds', str(a.seconds + 180)])"
 new="""guest('mkdir -p /tmp/p5-observer')
    run(['scp','-i',key,*[Path(__file__).with_name(x) for x in ('observer.py','guest-observe.py','profile.json')],'lab@192.168.231.11:/tmp/p5-observer/'])
    remote_output='/opt/lwlab/results/p5/semantics-'+a.name
    windows = subprocess.Popen(ssh+['sudo python3 /tmp/p5-observer/guest-observe.py /tmp/p5-observer/profile.json '+remote_output+' --reject-generation '+previous_generation],stdout=log,stderr=log)"""
 assert old in s;s=s.replace(old,new)
 s=s.replace("oldboot = guest(","previous_generation=dict(x.split('=',1) for x in guest('cat /sys/kernel/lwlab/status').split())['generation']\noldboot = guest(")
 s=s.replace("virsh('start', 'lwlab-boot')", """# Preserve the previous clone and cold-start from the identical installed baseline.
disk=root/'state-p5/windows.qcow2'
previous=root/'artifacts/p5'/f'{a.name}-previous-windows.qcow2'
assert not previous.exists()
run(['sudo','-n','mv',disk,previous])
run(['sudo','-n','qemu-img','create','-f','qcow2','-F','qcow2','-b',root/'state-p5-install/windows.qcow2',disk])
run(['sudo','-n','chown','libvirt-qemu:kvm',disk])
virsh('start', 'lwlab-boot')""")
 s=s.replace("(out / 'metadata.json').write_text", "run(['scp','-r','-i',key,'lab@192.168.231.11:'+remote_output,str(out/'semantics')])\n(out / 'metadata.json').write_text")
 s=s.replace("'verify-attempt.py'","'verify-full.py'")
 f.write_text(s)
 for name in ('observer.py','guest-observe.py','verify-full.py'):
  (a.output/name).write_text((here/name).read_text())
 (a.output/'profile.json').write_text((here/'profiles/windows-26100.1742.json').read_text())
