#!/usr/bin/env python3
"""Finite, fail-stop P6 sequence; no recurring scheduler or automatic retries.

The separate controlled fault and observation stress matrix is not certified by
this sequence. Every completed phase has cold-disk verification before advance.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time
import importlib.util

p = argparse.ArgumentParser()
p.add_argument('name')
p.add_argument('--through', choices=('single-recovery', 'restarts', 'cold-matrix', 'long-runs'), required=True)
a = p.parse_args()
assert a.name.replace('-', '').replace('_', '').isalnum()
root = Path('/data/linux-window-lab')
repo = root / 'repo'
artifacts = root / 'artifacts/p6'
out = artifacts / a.name
out.mkdir(exist_ok=False)
spec = importlib.util.spec_from_file_location('gate', repo / 'p6/resource-gate.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
source = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
state = dict(source_commit=source, through=a.through, state='running', phase='initial-30m', completed=[],
             p6_complete=False, started=time.time(), controlled_fault_matrix_complete=False)


def save():
    state['updated'] = time.time()
    temp = out / 'status.tmp'
    temp.write_text(json.dumps(state, indent=2)+'\n')
    temp.replace(out / 'status.json')


def phase(name):
    assert subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip() == source, 'source changed; stop for review'
    state['phase'] = name
    save()


def off():
    for _ in range(60):
        value = subprocess.check_output(['sudo', '-n', 'virsh', 'domstate', 'lwlab-boot'], text=True).strip()
        if value == 'shut off':
            return
        time.sleep(2)
    raise RuntimeError('VM still running; no disk access or further tests permitted')


def admission():
    # A resource interruption does not provoke another VM start. Wait while
    # off, for a fresh full window, then stop this finite campaign after 1 hour.
    off()
    for _ in range(61):
        rows = [json.loads(x) for x in (artifacts / 'resource-history.jsonl').read_text().splitlines()]
        if gate.stable(rows, time.time()):
            return
        time.sleep(60)
    raise RuntimeError('no new resource admission within one hour')


def execute(name, command):
    phase(name)
    with (out / (name+'.log')).open('w') as log:
        subprocess.run(command, stdout=log, stderr=log, check=True)


def verified(name, recovery=False):
    off()
    command = ['python3', str(repo / 'p6/finalize-attempt.py'), name]
    if recovery:
        command.append('--recovery')
    execute(name+'-verify', command)
    file = artifacts / name / ('recovery-verification.json' if recovery else 'attempt-verification.json')
    result = json.loads(file.read_text())
    assert result['independent_restart_passed' if recovery else 'attempt_passed']
    state['completed'].append(dict(name=name, verification=str(file), recovery=recovery, time=time.time()))
    save()


def cold(name, cpus, seconds, previous_truth=None):
    phase(name+'-admission')
    admission()
    command = ['python3', str(repo / 'p6/run-cold.py'), name, '--cpus', str(cpus), '--seconds', str(seconds)]
    if previous_truth:
        command += ['--no-observe', '--previous-truth', str(previous_truth)]
    execute(name, command)
    verified(name)


def restart(name, cycles):
    phase(name+'-admission')
    admission()
    prime = name+'-prime'
    execute(prime, ['python3', str(repo / 'p6/run-cold.py'), prime, '--cpus', '4', '--seconds', '60', '--keep-running'])
    execute(name, ['python3', str(repo / 'p6/run-recovery.py'), name, '--cycles', str(cycles)])
    verified(name, recovery=True)


try:
    save()
    # This first run was already dispatched interactively. Its separate
    # finalizer must succeed; never replace failure evidence with a retry.
    initial = artifacts / 'r5-mp4-30m-02'
    deadline = time.monotonic()+2700
    while True:
        assert not (artifacts / 'r5-mp4-30m-02-finalize-error.json').exists(), 'initial cold verification failed'
        assert time.monotonic() < deadline, 'initial attempt deadline expired'
        try:
            result = json.loads((initial / 'attempt-verification.json').read_text())
            assert result['attempt_passed'], 'initial attempt failed'
            break
        except (FileNotFoundError, json.JSONDecodeError):
            time.sleep(15)
    off()
    state['completed'].append(dict(name=initial.name, verification=str(initial / 'attempt-verification.json')))
    restart('r5-recovery-single-01', 1)
    if a.through != 'single-recovery':
        restart('r5-recovery-ten-01', 10)
    if a.through in ('cold-matrix', 'long-runs'):
        for cpus in (1, 2):
            for index in range(1, 4):
                cold(f'r5-cpu{cpus}-30m-{index:02}', cpus, 1800)
        for index in range(3, 12):
            cold(f'r5-mp4-30m-{index:02}', 4, 1800)
    if a.through == 'long-runs':
        cold('r5-mp4-2h-01', 4, 7200)
        cold('r5-mp4-24h-01', 4, 86400)
        cold('r5-mp4-observer-off-01', 4, 1800, artifacts / 'r5-mp4-24h-01/p6-truth.jsonl')
    state['state'] = 'requested-sequence-verified'
    state['outstanding'] = ['controlled fault matrix', 'observation identity reuse/paging/unsupported-profile stress',
                            'full P6 acceptance review']
except BaseException as exc:
    state['state'] = 'failed'
    state['error'] = repr(exc)
    # Only the project VM may be affected. Never reset the physical server.
    try:
        value = subprocess.check_output(['sudo', '-n', 'virsh', 'domstate', 'lwlab-boot'], text=True).strip()
        if value != 'shut off':
            subprocess.run(['sudo', '-n', 'virsh', 'shutdown', 'lwlab-boot'], check=True, timeout=30)
            off()
    except Exception as cleanup:
        state['cleanup_error'] = repr(cleanup)
    raise
finally:
    save()
