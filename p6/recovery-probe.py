#!/usr/bin/env python3
"""Linux continuity during partition recovery; never starts or stops Windows."""
import argparse
import json
import os
from pathlib import Path
import socket
import time

p = argparse.ArgumentParser()
p.add_argument('--seconds', type=int, required=True)
p.add_argument('--stop-file', type=Path)
a = p.parse_args()
assert a.seconds >= 30
if a.stop_file:
    assert not a.stop_file.exists()
assert socket.gethostname() == 'lwlab-boot'
assert os.uname().release == '6.18.0-rc3-lwlab-p6'
assert Path('/proc/sys/kernel/tainted').read_text().strip() == '0'
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
output = Path('/opt/lwlab/results/p6')
output.mkdir(parents=True, exist_ok=True)
with socket.socket() as server:
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', 8081))
    server.listen(1)
    server.settimeout(90)
    connection, peer = server.accept()
    with connection:
        connection.settimeout(10)
        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        began = time.monotonic()
        seq = 0
        while time.monotonic() - began < a.seconds and not (a.stop_file and a.stop_file.exists()):
            start = time.monotonic_ns()
            data = (f'{boot}:recovery:{seq}\n'.encode() * 128)
            path = output / 'recovery-io.bin'
            with path.open('wb') as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            assert path.read_bytes() == data
            assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == boot
            # Do not take the loader's sysfs lock here: a blocked stop/prepare
            # must not block the independent continuity stream being measured.
            sample = dict(kind='sample', boot_id=boot, sequence=seq,
                          monotonic=time.monotonic(), io_ok=True,
                          io_ns=time.monotonic_ns()-start, state=dict(heartbeat=0))
            connection.sendall((json.dumps(sample)+'\n').encode())
            seq += 1
            time.sleep(1)
        taint = int(Path('/proc/sys/kernel/tainted').read_text())
        result = dict(kind='result', scope='linux-recovery-continuity-only',
                      boot_id=boot, samples=seq, kernel_taint=taint,
                      formal_lifecycle_acceptance=False)
        result['pass'] = taint == 0 and (not a.stop_file or a.stop_file.exists())
        connection.sendall((json.dumps(result)+'\n').encode())
