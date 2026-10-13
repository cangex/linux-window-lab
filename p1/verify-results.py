#!/usr/bin/env python3
"""Independently verify the complete saved matrix and per-sample AP evidence."""
import argparse
import hashlib
import json
from pathlib import Path

# Recorded errno values belong to the Linux guest, even when verifying on macOS.
LINUX_EIO, LINUX_EBUSY, LINUX_EINVAL, LINUX_ERANGE, LINUX_ETIMEDOUT = 5, 16, 22, 34, 110

p = argparse.ArgumentParser()
p.add_argument('directory', type=Path)
a = p.parse_args()
matrix = json.loads((a.directory/'matrix.json').read_text())
assert matrix['pass']
assert len(matrix['runs']) == 12
boot_ids, generations = set(), set()
rows = []
for run in matrix['runs']:
    assert run['pass'] and run['persistent_tcp'] and run['ping_failures'] == 0
    guest = run['guest']
    assert run['boot_id'] not in boot_ids
    assert guest['generation'] not in generations
    boot_ids.add(run['boot_id'])
    generations.add(guest['generation'])
    messages = [json.loads(line) for line in (a.directory/run['name']/'stream.jsonl').read_text().splitlines()]
    assert messages[-1]['kind'] == 'result'
    assert messages[-1]['boot_id'] == run['boot_id']
    samples = messages[:-1]
    assert len(samples) == run['samples'] == guest['samples']
    pre = [m for m in samples if not m['launched']]
    post = [m for m in samples if m['launched']]
    assert len(pre) >= 4 and post
    assert all(m['io_ok'] and m['sequence'] == i and m['boot_id'] == run['boot_id'] for i,m in enumerate(samples))
    observed_seconds = messages[-1]['received_monotonic'] - post[0]['received_monotonic']
    # Up to two seconds for receipt/sampling around the exact guest launch boundary.
    assert observed_seconds >= guest['seconds_after_start'] - 2
    gaps = [b['received_monotonic'] - a['received_monotonic'] for a,b in zip(samples,samples[1:])]
    assert gaps and min(gaps) >= 0 and max(gaps) < 8
    assert abs(max(gaps) - run['max_tcp_gap_seconds']) < 1e-6
    for m in samples:
        data = (f"{run['boot_id']}:{guest['generation']}:{m['sequence']}\n".encode() * 128)
        assert m['io_sha256'] == hashlib.sha256(data).hexdigest()
    raw_result = {k:v for k,v in messages[-1].items() if k != 'received_monotonic'}
    assert raw_result == guest
    expected_errno = {'online_cpu': LINUX_EBUSY, 'wrong_version': LINUX_EINVAL,
                      'boot_cpu': LINUX_EINVAL, 'zero_generation': LINUX_EINVAL,
                      'malformed': LINUX_EINVAL, 'outside_memory': LINUX_ERANGE,
                      'wrong_size': LINUX_ERANGE, 'illegal_entry': LINUX_ERANGE,
                      'entry_outside': LINUX_ERANGE, 'second_start': LINUX_EBUSY,
                      'reload_after_start': LINUX_EBUSY, 'reonline_after_start': LINUX_EBUSY}
    assert {k:v['errno'] for k,v in guest['negative_checks'].items()} == expected_errno
    flag = guest['flags']
    if flag == 0:
        assert guest['start_errno'] is None
        heartbeats = []
        for m in post:
            state = m['state']
            assert state['state'] == 'payload-ready' and state['stage'] == '2'
            assert state['ack_generation'] == state['generation'] == str(guest['generation'])
            assert state['actual_apic'] == state['expected_apic'] == '4'
            assert state['payload_error'] == '0' and state['started'] == '1'
            assert int(state['ack_magic'], 16) == 0x313030765041574c
            assert int(state['cr3'],16) == 0x180002000
            assert int(state['stack'],16) == 0x180100000
            heartbeats.append(int(state['heartbeat']))
        assert heartbeats[0] > 0
        assert all(b > a for a,b in zip(heartbeats,heartbeats[1:]))
    else:
        assert guest['start_errno'] == (LINUX_ETIMEDOUT if flag == 1 else LINUX_EIO)
        for m in post:
            state = m['state']
            assert state['state'] == 'failed' and state['started'] == '1'
            assert state['stage'] == ('1' if flag == 1 else '255')
            assert state['payload_error'] == ('0' if flag == 1 else '3')
            assert state['heartbeat'] == '0'
    log = (a.directory/f"{run['name']}-dmesg.log").read_text()
    assert f"LWLAB: AP kick cleanup complete generation={guest['generation']}" in log
    assert not any(marker in log for marker in ['WARNING:', 'BUG:', 'Oops:', 'Kernel panic'])
    rows.append({'name': run['name'], 'boot_id': run['boot_id'], 'generation': guest['generation'],
                 'flags': flag, 'samples': len(samples), 'requested_seconds': guest['seconds_after_start'],
                 'observed_post_start_seconds': round(observed_seconds,3),
                 'max_tcp_gap_seconds': round(run['max_tcp_gap_seconds'],6),
                 'final_heartbeat': int(guest['final']['heartbeat'])})
normal = [r for r in rows if r['flags'] == 0]
assert len(normal) == 10
assert max(r['requested_seconds'] for r in normal) >= 1800
assert sorted(r['flags'] for r in rows) == [0]*10+[1,2]
report = {'pass': True, 'independent_boots': len(boot_ids), 'normal_boots': len(normal), 'runs': rows}
print(json.dumps(report,indent=2))
