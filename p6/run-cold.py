#!/usr/bin/env python3
"""Start exactly one gated cold experiment; never starts another after failure."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET
from firmware import firmware as resolve_firmware

p = argparse.ArgumentParser()
p.add_argument('name')
p.add_argument('--seconds', type=int, required=True)
p.add_argument('--cpus', type=int, choices=(1, 2, 4), required=True)
p.add_argument('--keep-running', action='store_true')
p.add_argument('--no-observe', action='store_true')
p.add_argument('--previous-truth', type=Path)
p.add_argument('--firmware-mode', choices=('r5', 'hal-probe', 'hal-enforce'), default='r5')
a = p.parse_args()
assert a.name.replace('-', '').replace('_', '').isalnum() and a.seconds >= 30
root = Path('/data/linux-window-lab')
repo = root / 'repo'
control = root / 'artifacts/p6' / (a.name+'-control')
assert not (root / 'artifacts/p6' / a.name).exists()
control.mkdir(exist_ok=False)
spec = importlib.util.spec_from_file_location('gate', repo / 'p6/resource-gate.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
ssh = ['ssh', '-i', str(root / 'keys/guest_ed25519'), '-o', 'BatchMode=yes',
       '-o', 'ConnectTimeout=5', 'lab@192.168.231.11']
started = False
passed = False


def run(args, timeout=90):
    return subprocess.run(list(map(str, args)), check=True, text=True, capture_output=True, timeout=timeout).stdout


def check_gate(admission=False):
    rows = [json.loads(x) for x in (root / 'artifacts/p6/resource-history.jsonl').read_text().splitlines()]
    row = rows[-1]
    assert 0 <= time.time()-row['time'] <= 90 and row['policy'] == gate.POLICY and not gate.assess(row)
    if admission:
        assert gate.stable(rows, time.time())
    return rows


try:
    assert run(['sudo', '-n', 'virsh', 'domstate', 'lwlab-boot']).strip() == 'shut off'
    xml = run(['sudo', '-n', 'virsh', 'dumpxml', 'lwlab-boot'])
    tuning = ET.fromstring(xml).find('numatune')
    assert tuning is not None and tuning.find('memory').get('nodeset') == gate.NODESET
    assert tuning.find('memory').get('mode') == 'interleave'
    assert all(x.get('nodeset') == gate.NODESET for x in tuning.findall('memnode'))
    assert '/state-p6/windows.qcow2' in xml
    (control / 'vm.xml').write_text(xml)
    (control / 'source-commit.txt').write_text(run(['git', '-C', str(repo), 'rev-parse', 'HEAD']))
    if a.no_observe:
        assert a.previous_truth and a.previous_truth.name == 'p6-truth.jsonl'
        assert a.previous_truth.resolve().is_relative_to(root / 'artifacts/p6')
        previous = a.previous_truth.parent
        assert json.loads((previous / 'attempt-verification.json').read_text())['attempt_passed']
        run(['qemu-img', 'compare', str(root / 'state-p6/windows.qcow2'), str(previous / 'windows.qcow2')], timeout=300)
    firmware, expected = resolve_firmware(root, a.cpus, a.firmware_mode)
    assert hashlib.sha256(firmware.read_bytes()).hexdigest() == expected
    rows = check_gate(True)
    (control / 'admission.json').write_text(json.dumps(dict(time=time.time(), samples=rows), indent=2))
    run(['sudo', '-n', 'virsh', 'start', 'lwlab-boot'])
    started = True
    deadline = time.monotonic()+180
    while True:
        check_gate()
        try:
            if run(ssh + ['cat /sys/kernel/lwlab/status']).startswith('state=idle '):
                break
        except subprocess.SubprocessError:
            pass
        assert time.monotonic() < deadline, 'Linux boot timeout'
        time.sleep(2)
    assert run(ssh + ['uname -r']).strip() == '6.18.0-rc3-lwlab-p6'
    run(['scp', '-i', root / 'keys/guest_ed25519', firmware, 'lab@192.168.231.11:/tmp/p6-next-firmware.bin'])
    assert run(ssh + ['sha256sum /tmp/p6-next-firmware.bin']).split()[0] == expected
    run(ssh + ['sudo install -m 0644 /tmp/p6-next-firmware.bin /lib/firmware/lwlab/partition-p3.bin'])
    pid = run(['sudo', '-n', 'cat', '/run/libvirt/qemu/lwlab-boot.pid']).strip()
    assert pid.isdigit()
    (control / 'numa_maps.txt').write_text(run(['sudo', '-n', 'cat', f'/proc/{pid}/numa_maps']))
    command = ['python3', str(repo / 'p6/run-attempt.py'), a.name, '--seconds', str(a.seconds), '--cpus', str(a.cpus), '--windows-clock', '--firmware-mode', a.firmware_mode]
    if a.keep_running:
        command.append('--keep-running')
    if a.no_observe:
        command += ['--no-observe', '--previous-truth', str(a.previous_truth)]
    subprocess.run(command, check=True)
    passed = True
finally:
    if started and (not passed or not a.keep_running):
        state = run(['sudo', '-n', 'virsh', 'domstate', 'lwlab-boot']).strip()
        if state != 'shut off':
            # ACPI request only; preserve an unresponsive VM for diagnosis.
            run(['sudo', '-n', 'virsh', 'shutdown', 'lwlab-boot'])
            for _ in range(60):
                state = run(['sudo', '-n', 'virsh', 'domstate', 'lwlab-boot']).strip()
                if state == 'shut off':
                    break
                time.sleep(2)
        (control / 'final-domain-state.txt').write_text(state+'\n')
        assert state == 'shut off', 'VM did not stop; do not reuse its disk or start more tests'
