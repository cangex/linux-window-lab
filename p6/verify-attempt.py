#!/usr/bin/env python3
"""Combine cold truth and live evidence for one bounded attempt, never all P6."""
import argparse
import importlib.util
import json
import re
from pathlib import Path


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]


def select_truth(truth, observations):
    """Select by externally observed identity, not the last record on disk."""
    samples = [row for row in observations if row['event'] == 'sample']
    identities = {(row['target']['pid'], row['target']['created']) for row in samples}
    if len(identities) != 1:
        raise ValueError('expected one observed workload identity')
    identity = identities.pop()
    matching = [row for row in truth if (row['pid'], row['created']) == identity]
    nonces = {row['nonce'] for row in matching}
    if len(nonces) != 1:
        raise ValueError('cold truth missing or ambiguous for observed identity')
    return matching, nonces.pop()


def verify(directory):
    before = json.loads((directory / 'before.json').read_text())
    collection = json.loads((directory / 'collection-result.json').read_text())
    linux = json.loads((directory / 'linux/result.json').read_text())
    observations = read_rows(directory / 'observations.jsonl')
    truth, nonce = select_truth(read_rows(directory / 'p6-truth.jsonl'), observations)
    workload = load_module('verify-workload').verify(truth, before['cpus'], before['seconds'])
    semantics = load_module('verify-semantics').verify(truth, observations, nonce)
    bootstraps = [row for row in observations if row['event'] == 'bootstrap']
    errors = []
    if not collection['collection_passed']:
        errors.append('collection_failed')
    if not linux['pass'] or linux['boot_id'] != before['boot_id'] or linux['elapsed'] < before['seconds']:
        errors.append('linux_continuity_failed')
    if len(bootstraps) != 1 or bootstraps[0]['generation'] != linux['guest']['generation']:
        errors.append('generation_mismatch')
    # Require actual PRCB execution progression on every assigned CPU as well
    # as the separately checked workload thread counters from cold storage.
    samples = [row for row in observations if row['event'] == 'sample']
    for row in samples:
        if [(cpu['Number'], cpu['InitialApicId']) for cpu in row['cpus']] != [(i, 4+i) for i in range(before['cpus'])]:
            raise ValueError('unexpected observed CPU ownership')
    cpu_progress = [samples[-1]['cpus'][i]['CycleTime'] - samples[0]['cpus'][i]['CycleTime'] for i in range(before['cpus'])]
    if any(delta <= 0 for delta in cpu_progress):
        errors.append('cpu_execution_not_advancing')
    anomalies = [line for line in (directory / 'dmesg.txt').read_text().splitlines()
                 if re.search(r'(?i)(\brcu\b.*\bstall\b|soft lockup|hard LOCKUP|\bBUG:|\bOops:|Kernel panic)', line)]
    if anomalies:
        errors.append('linux_kernel_anomaly')
    if not semantics['passed']:
        errors.append('semantics_failed')
    return dict(attempt_passed=not errors, errors=errors, formal_p6_acceptance=False,
                scope='one cold-start load and observation attempt', workload=workload,
                semantics=semantics, linux=linux, cpu_cycle_deltas=cpu_progress,
                kernel_anomalies=anomalies,
                lifecycle_observation_target_met=min(workload[k] for k in ('child_starts', 'child_ends', 'dll_loads', 'dll_unloads')) >= 100)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    result = verify(args.directory)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['attempt_passed'] else 1)
