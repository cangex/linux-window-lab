#!/usr/bin/env python3
"""Supervise explicit r5 partition restart cycles in an already running VM.

Captures a Linux continuity stream across all cycles and cold truth afterwards.
Never starts a VM, reuses a failed partition, or counts this as a fault matrix.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import time
from firmware import firmware as resolve_firmware

p = argparse.ArgumentParser()
p.add_argument('name')
p.add_argument('--cycles', type=int, choices=(1, 10), default=1)
p.add_argument('--firmware-mode', choices=('r5','hal-enforce'), default='r5')
a = p.parse_args()
assert a.name.replace('-', '').replace('_', '').isalnum()
root = Path('/data/linux-window-lab')
repo = root / 'repo'
out = root / 'artifacts/p6' / a.name
out.mkdir(exist_ok=False)
spec = importlib.util.spec_from_file_location('gate', repo / 'p6/resource-gate.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
ssh = ['ssh', '-i', str(root / 'keys/guest_ed25519'), '-o', 'BatchMode=yes',
       '-o', 'ConnectTimeout=8', 'lab@192.168.231.11']
stop = '/tmp/' + a.name + '-continuity.done'
files = []
processes = []
failure = None
started = False


def run(args, timeout=60):
    return subprocess.run(list(map(str, args)), check=True, capture_output=True, text=True, timeout=timeout).stdout


def guest(command):
    return run(ssh + [command])


def resource(admission=False):
    rows = [json.loads(x) for x in (root / 'artifacts/p6/resource-history.jsonl').read_text().splitlines()]
    row = rows[-1]
    assert 0 <= time.time()-row['time'] <= 90 and row['policy'] == gate.POLICY and not gate.assess(row)
    if admission:
        assert gate.stable(rows, time.time())
    with (out / 'resources.jsonl').open('a') as f:
        f.write(json.dumps(row)+'\n')


def launch(command, path):
    file = path.open('w')
    files.append(file)
    proc = subprocess.Popen(command, stdout=file, stderr=file)
    processes.append(proc)
    return proc


try:
    resource(True)
    assert guest('uname -r').strip() == '6.18.0-rc3-lwlab-p6'
    assert guest('sha256sum /boot/vmlinuz-6.18.0-rc3-lwlab-p6').split()[0] == '6309c7f909e2205f96d9d9caca5b928b6e4495b3a878826c381c42d1dc24108c'
    assert guest('sha256sum /lib/firmware/lwlab/partition-p3.bin').split()[0] == resolve_firmware(root,4,a.firmware_mode)[1]
    before = guest('cat /sys/kernel/lwlab/status')
    assert 'stage=3 ' in before and 'started=1 ' in before
    bootid = guest('cat /proc/sys/kernel/random/boot_id').strip()
    xml = run(['sudo', '-n', 'virsh', 'dumpxml', 'lwlab-boot'])
    import xml.etree.ElementTree as ET
    memory = ET.fromstring(xml).find('numatune/memory')
    assert memory is not None and memory.get('nodeset') == gate.NODESET and memory.get('mode') == 'interleave'
    assert '/state-p6/windows.qcow2' in xml
    (out / 'vm.xml').write_text(xml)
    (out / 'before.json').write_text(json.dumps(dict(boot_id=bootid, status=before, cycles=a.cycles,firmware_mode=a.firmware_mode)))
    guest('test ! -e ' + shlex.quote(stop))
    run(['scp', '-i', root / 'keys/guest_ed25519', repo / 'p6/recover.py', repo / 'p6/recovery-probe.py', repo / 'p6/windows_clock.py',
         root / 'artifacts/p6/p6-cpu-profile-recovery.json',
         'lab@192.168.231.11:/tmp/p6-run/p6/'])
    started = True
    duration = a.cycles*360+120
    probe = launch(ssh + [f'sudo timeout {duration+30} python3 /tmp/p6-run/p6/recovery-probe.py --seconds {duration} --stop-file {stop}'], out / 'linux-guest.log')
    stream = launch(['python3', str(repo / 'p1/host-observe.py'), '--output', str(out / 'linux')], out / 'linux-host.log')
    deadline = time.monotonic()+90
    while not (out / 'linux/stream.jsonl').exists() or (out / 'linux/stream.jsonl').stat().st_size == 0:
        assert probe.poll() is None and stream.poll() is None
        assert time.monotonic() < deadline
        time.sleep(1)
    results = []
    for cycle in range(a.cycles):
        resource()
        log = out / f'cycle-{cycle+1:02}.jsonl'
        command='sudo timeout 330 python3 /tmp/p6-run/p6/recover.py /tmp/p6-run/p6/p6-cpu-profile-recovery.json'
        if a.firmware_mode=='hal-enforce':command+=' --require-no-shorthand'
        proc = launch(ssh + [command], log)
        deadline = time.monotonic()+345
        while proc.poll() is None:
            resource()
            assert probe.poll() is None and stream.poll() is None
            assert time.monotonic() < deadline
            time.sleep(5)
        assert proc.returncode == 0, f'recovery cycle {cycle+1} failed'
        rows = [json.loads(x) for x in log.read_text().splitlines()]
        result = rows[-1]
        assert result['event'] == 'result' and result['partition_bootstrap_passed'] and result['old_info_and_read_rejected']
        assert result['linux_boot_id'] == bootid and result['new_generation'] > result['old_generation']
        if results:
            assert results[-1]['new_generation'] == result['old_generation']
        results.append(result)
    guest('touch ' + shlex.quote(stop))
    assert probe.wait(timeout=20) == stream.wait(timeout=20) == 0
    linux = json.loads((out / 'linux/result.json').read_text())
    assert linux['pass'] and linux['boot_id'] == bootid
    assert guest('cat /proc/sys/kernel/random/boot_id').strip() == bootid
except BaseException as exc:
    failure = repr(exc)
finally:
    for name, command in [('dmesg.txt', 'sudo dmesg'), ('status.txt', 'cat /sys/kernel/lwlab/status')]:
        try:
            (out / name).write_text(guest(command))
        except Exception as exc:
            (out / (name+'.error')).write_text(repr(exc))
    # Preserve stop evidence before shutting down the containing test VM.
    # This cleanup is not a Windows independent recovery success.
    if started:
        try:
            subprocess.run(ssh + ['sudo poweroff'], capture_output=True, timeout=30)
        except Exception as exc:
            failure = (failure or '') + '; shutdown: ' + repr(exc)
    for proc in processes:
        if proc.poll() is None:
            proc.terminate()
    for file in files:
        file.close()
    (out / 'collection-result.json').write_text(json.dumps(dict(
        recovery_collection_passed=failure is None, error=failure,
        formal_p6_acceptance=False, cold_truth_verification_required=True,
        scope='explicit partition restart only; controlled fault matrix remains separate'), indent=2)+'\n')
if failure:
    raise SystemExit(failure)
print(str(out))
