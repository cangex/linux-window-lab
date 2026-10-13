#!/usr/bin/env python3
"""Run on the libvirt host. All lifecycle operations target lwlab-boot."""
import argparse
import json
from pathlib import Path
import subprocess
import time

p = argparse.ArgumentParser()
p.add_argument('--output', type=Path, required=True)
p.add_argument('--key', default='/data/linux-window-lab/keys/guest_ed25519')
p.add_argument('--ip', default='192.168.231.11')
p.add_argument('--short-seconds', type=int, default=30)
p.add_argument('--long-seconds', type=int, default=1800)
p.add_argument('--cycles', type=int, default=10)
a = p.parse_args()
here = Path(__file__).resolve().parent
ssh = ['ssh', '-i', a.key, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', f'lab@{a.ip}']
a.output.mkdir(parents=True, exist_ok=False)

def remote(command, **kwargs):
    return subprocess.run(ssh+[command], **kwargs)

def domain_state():
    return subprocess.check_output(['sudo', 'virsh', 'domstate', 'lwlab-boot'], text=True).strip()

def cold_boot():
    if domain_state() == 'running':
        remote('sudo systemctl poweroff', stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic()+90
        while domain_state() != 'shut off':
            if time.monotonic() > deadline:
                raise RuntimeError('Guest did not power off; do not automatically force-destroy it')
            time.sleep(1)
    assert domain_state() == 'shut off'
    subprocess.run(['sudo', 'virsh', 'start', 'lwlab-boot'], check=True)
    deadline = time.monotonic()+180
    while True:
        ready = remote('test -r /sys/kernel/lwlab/status && test "$(uname -r)" = 6.18.0-rc3-lwlab-p1',
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if ready.returncode == 0:
            return
        if time.monotonic() > deadline:
            raise RuntimeError('P1 kernel did not become reachable')
        time.sleep(2)

runs = [(f'cold-{i+1:02}', a.long_seconds if i == 0 else a.short_seconds, 0)
        for i in range(a.cycles)]
runs += [('timeout', a.short_seconds, 1), ('exception', a.short_seconds, 2)]
boot_ids, summaries = set(), []
for name, seconds, flags in runs:
    print(f'START {name} duration={seconds} flags={flags}', flush=True)
    cold_boot()
    subprocess.run(['scp', '-i', a.key, str(here/'guest-probe.py'), f'lab@{a.ip}:/opt/lwlab/guest-probe.py'], check=True)
    log = (a.output/f'{name}-guest.log').open('w')
    guest = subprocess.Popen(ssh+[f'sudo python3 /opt/lwlab/guest-probe.py --seconds {seconds} --flags {flags}'], stdout=log, stderr=subprocess.STDOUT)
    try:
        observed = subprocess.run(['python3', str(here/'host-observe.py'), '--ip', a.ip,
                                   '--output', str(a.output/name)])
        guest_status = guest.wait(timeout=20)
        assert guest_status == 0, f'{name}: guest failed (see guest log)'
        assert observed.returncode == 0, f'{name}: observer failed'
    finally:
        if guest.poll() is None:
            guest.terminate()
        log.close()
        with (a.output/f'{name}-dmesg.log').open('w') as kernel_log:
            remote('sudo dmesg', stdout=kernel_log, stderr=subprocess.STDOUT)
    result = json.loads((a.output/name/'result.json').read_text())
    assert result['boot_id'] not in boot_ids, 'Not a new Linux boot'
    boot_ids.add(result['boot_id'])
    summaries.append({'name': name, **result})
    (a.output/'progress.json').write_text(json.dumps(summaries, indent=2)+'\n')
    print(f'PASS {name}', flush=True)
(a.output/'matrix.json').write_text(json.dumps({'pass': True, 'runs': summaries}, indent=2)+'\n')
print('MATRIX PASS', flush=True)
