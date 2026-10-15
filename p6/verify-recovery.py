#!/usr/bin/env python3
"""Verify independent restart evidence, not the separate controlled fault matrix."""
import argparse
import importlib.util
import json
from pathlib import Path
import re


def rows(path):
    return [json.loads(x) for x in path.read_text(encoding='utf-8-sig').splitlines() if x.strip()]


def verify(out):
    before = json.loads((out / 'before.json').read_text())
    collection = json.loads((out / 'collection-result.json').read_text())
    linux = json.loads((out / 'linux/result.json').read_text())
    assert collection['recovery_collection_passed'] and linux['pass']
    assert linux['boot_id'] == before['boot_id']
    truth = rows(out / 'p6-truth.jsonl')
    spec = importlib.util.spec_from_file_location('workload', Path(__file__).with_name('verify-workload.py'))
    workload = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(workload)
    generations = []
    boot_ids = []
    nonces = []
    identities = set()
    cycles = []
    for i in range(before['cycles']):
        log = rows(out / f'cycle-{i+1:02}.jsonl')
        events = {event['event']: event for event in log}
        assert len(events) == len(log) and set(events) == {'before', 'stop', 'quiescence', 'result'}
        initial, stop, quiet, result = (events[k] for k in ('before', 'stop', 'quiescence', 'result'))
        assert initial['linux_boot_id'] == result['linux_boot_id'] == before['boot_id']
        assert stop['state']['state'] == 'stopped' and stop['state']['started'] == '0'
        assert quiet['bus_master_disabled'] and quiet['pci_command'] & 4 == 0
        assert result['partition_bootstrap_passed'] and result['old_info_and_read_rejected']
        old, new = result['old_generation'], result['new_generation']
        assert new > old and int(initial['state']['generation']) == old
        evidence = '\n'.join(quiet['kernel_log'])
        parked = re.findall(r'LWLAB P6: four parked CPUs and NVMe reset; nonce=(\d+) generation='+str(old)+r'\b', evidence)
        assert len(parked) == 1 and int(parked[0]) >= 1 << 63
        nonces.append(int(parked[0]))
        first, last = result['running_before'], result['running_after']
        previous_boot = initial['running']['windows_boot_id']
        assert first['windows_boot_id'] == last['windows_boot_id'] != previous_boot
        assert last['interrupt_time_100ns'] > first['interrupt_time_100ns']
        assert [(c['Number'], c['InitialApicId']) for c in last['cpus']] == [(j, 4+j) for j in range(4)]
        assert all(b['CycleTime'] > a['CycleTime'] for a, b in zip(first['cpus'], last['cpus']))
        if generations:
            assert generations[-1] == old and boot_ids[-1] == previous_boot
        else:
            generations.append(old)
            boot_ids.append(previous_boot)
        generations.append(new)
        boot_ids.append(last['windows_boot_id'])
        for target in (initial['running']['target'], last['target']):
            identities.add((target['pid'], target['created']))
        cycles.append(dict(old_generation=old, new_generation=new, old_windows_boot_id=previous_boot,
                           new_windows_boot_id=last['windows_boot_id'], park_nonce=int(parked[0])))
    assert len(set(boot_ids)) == len(boot_ids) and len(set(nonces)) == len(nonces)
    assert len(identities) == before['cycles']+1
    workloads = []
    for identity in sorted(identities):
        matching = [r for r in truth if (r['pid'], r['created']) == identity]
        assert len({r['nonce'] for r in matching}) == 1, 'cold truth identity missing or ambiguous'
        workloads.append(workload.verify(matching, 4, minimum_seconds=5))
    anomalies = [line for line in (out / 'dmesg.txt').read_text().splitlines()
                 if re.search(r'(?i)(\brcu\b.*\bstall\b|soft lockup|hard LOCKUP|\bBUG:|\bOops:|Kernel panic)', line)]
    assert not anomalies, anomalies
    return dict(independent_restart_passed=True, cycles=cycles, linux=linux, workloads=workloads,
                formal_p6_acceptance=False, controlled_fault_matrix_complete=False,
                note='Controlled Windows bugcheck/shutdown/reboot and NVMe timeout cases require separate evidence')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.directory), indent=2))
