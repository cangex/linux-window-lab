#!/usr/bin/env python3
"""Host-side capture; QMP reads dedicated RAM GOP without pausing the VM."""
import argparse
import json
from pathlib import Path
import subprocess
import time
from visual_heartbeat import decode, png

p = argparse.ArgumentParser()
p.add_argument('output', type=Path)
p.add_argument('--seconds', type=int, default=3600)
a = p.parse_args()
def virsh(*args):
    return subprocess.run(['sudo', '-n', 'virsh', *args], check=True,
                          capture_output=True, text=True, timeout=15).stdout
end = time.monotonic() + a.seconds
while not a.output.is_dir():
    if time.monotonic() >= end: raise TimeoutError('Linux observer output not created')
    time.sleep(0.2)
domain_id = virsh('domid', 'lwlab-boot').strip()
assert domain_id.isdecimal()
raw = Path(f'/var/lib/libvirt/qemu/domain-{domain_id}-lwlab-boot/p3-heartbeat.raw')
first = True
last_frame = None
with (a.output / 'windows.jsonl').open('x') as log:
    while time.monotonic() < end and not (a.output / 'windows.stop').exists():
        before = time.monotonic()
        try:
            reply = virsh('qemu-monitor-command', 'lwlab-boot', '--hmp',
                          f'pmemsave 0x10200000 0x300000 "{raw}"')
            if reply.strip(): raise RuntimeError(reply.strip())
            frame = subprocess.run(['sudo', '-n', 'cat', str(raw)], check=True, capture_output=True, timeout=5).stdout
            record = dict(kind='sample', **decode(frame))
            last_frame = frame
            if first:
                (a.output / 'winpe-first.png').write_bytes(png(frame)); first = False
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            record = dict(kind='unavailable', error=str(exc))
        record.update(received_monotonic=time.monotonic(), capture_seconds=time.monotonic()-before)
        log.write(json.dumps(record) + '\n'); log.flush()
        if last_frame is not None and int(before) % 30 < 2:
            (a.output / 'winpe-latest.png').write_bytes(png(last_frame))
        time.sleep(max(0, 2 - (time.monotonic()-before)))
if last_frame is not None: (a.output / 'winpe-last.png').write_bytes(png(last_frame))
