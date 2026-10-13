#!/usr/bin/env python3
"""Observe one continuous TCP stream; never reconnect after launch."""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import time

p = argparse.ArgumentParser()
p.add_argument('--output', type=Path, required=True)
p.add_argument('--ip', default='192.168.231.11')
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=False)
deadline = time.monotonic() + 90
while True:
    try:
        sock = socket.create_connection((a.ip, 8081), timeout=10)
        break
    except OSError:
        if time.monotonic() >= deadline:
            raise
        time.sleep(1)
sock.settimeout(10)
stream = sock.makefile('rb')
samples, gaps, ping_failures = 0, [], 0
last, first, boot_id = None, None, None
result = None
with (a.output/'stream.jsonl').open('w') as log:
    while True:
        line = stream.readline()
        if not line:
            raise RuntimeError('TCP stream ended without a final result')
        now = time.monotonic()
        message = json.loads(line)
        log.write(json.dumps({'received_monotonic': now, **message})+'\n')
        log.flush()
        if message['kind'] == 'result':
            result = message
            break
        if boot_id is None:
            boot_id, first = message['boot_id'], now
        assert message['boot_id'] == boot_id
        assert message['sequence'] == samples
        assert message['io_ok']
        if last is not None:
            gaps.append(now-last)
        last = now
        samples += 1
        if samples % 10 == 0:
            probe = subprocess.run(['ping', '-n', '-c', '1', '-W', '1', a.ip], stdout=subprocess.DEVNULL)
            ping_failures += probe.returncode != 0
        if samples % 60 == 0:
            print(json.dumps({'samples': samples, 'elapsed': round(now-first, 1),
                              'ap_heartbeat': message['state']['heartbeat'],
                              'max_tcp_gap': max(gaps), 'ping_failures': ping_failures}), flush=True)
stream.close()
sock.close()
summary = {'pass': result['pass'] and ping_failures == 0 and max(gaps, default=0) < 8,
           'boot_id': boot_id, 'samples': samples, 'elapsed': round(last-first, 3),
           'max_tcp_gap_seconds': max(gaps, default=0), 'ping_failures': ping_failures,
           'persistent_tcp': True, 'guest': result}
(a.output/'result.json').write_text(json.dumps(summary, indent=2)+'\n')
print(json.dumps(summary, indent=2))
raise SystemExit(0 if summary['pass'] else 1)
