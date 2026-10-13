#!/usr/bin/env python3
"""Keep one Linux TCP/fsync/readback stream alive across a P3 AP attempt.

The result's pass field covers Linux continuity only. Windows userspace needs
independent evidence; firmware readiness and ExitBootServices do not suffice.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import threading
import time

p = argparse.ArgumentParser()
p.add_argument('--seconds', type=int, default=120)
a = p.parse_args()
assert a.seconds > 0
assert socket.gethostname() == 'lwlab-boot'
assert os.uname().release == '6.18.0-rc3-lwlab-p3'
assert Path('/proc/sys/kernel/tainted').read_text().strip() == '0'
assert 'no_ipi_broadcast=1' in Path('/proc/cmdline').read_text()
assert 'noapic' in Path('/proc/cmdline').read_text().split()
assert 'hpet=disable' in Path('/proc/cmdline').read_text().split()
assert 'IO-APIC' not in Path('/proc/interrupts').read_text()
serial = Path('/proc/tty/driver/serial').read_text()
assert 'port:000003F8' in serial and 'port:000002F8' not in serial
def write(path, text):
    fd = os.open(path, os.O_WRONLY)
    try:
        data = text.encode()
        assert os.write(fd, data) == len(data)
    finally:
        os.close(fd)
control = '/sys/kernel/lwlab/control'
def state():
    return dict(item.split('=', 1) for item in Path('/sys/kernel/lwlab/status').read_text().split())
assert state()['state'] == 'idle'
for cpu in range(4, 8):
    write(f'/sys/devices/system/cpu/cpu{cpu}/online', '0\n')
generation = secrets.randbelow(2**60) + 1
write(control, f'prepare 3 4 10000000 60000000 10010000 {generation} 0\n')
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
output = Path('/opt/lwlab/results/p3')
output.mkdir(exist_ok=True, parents=True)
done = threading.Event()
errors = []
def launch():
    try:
        write(control, 'start\n')
    except BaseException as exc:
        errors.append(str(exc))
    finally:
        done.set()
with socket.socket() as server:
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', 8081)); server.listen(1); server.settimeout(90)
    connection, peer = server.accept()
    with connection:
        connection.settimeout(10)
        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        began = time.monotonic()
        launched = False
        seq = 0
        while time.monotonic() - began < a.seconds + 5:
            if not launched and time.monotonic() - began >= 5:
                launched = True
                threading.Thread(target=launch, daemon=True).start()
            data = (f'{boot}:{generation}:{seq}\n'.encode() * 128)
            path = output / 'io-probe.bin'
            with path.open('wb') as f:
                f.write(data); f.flush(); os.fsync(f.fileno())
            assert path.read_bytes() == data
            current = state() if not launched or done.is_set() else dict(state='launch-pending', heartbeat='0')
            sample = dict(kind='sample', boot_id=boot, sequence=seq,
                monotonic=time.monotonic(), launched=launched,
                launch_pending=launched and not done.is_set(), state=current,
                generation=generation, io_ok=True, io_sha256=hashlib.sha256(data).hexdigest())
            connection.sendall((json.dumps(sample) + '\n').encode())
            seq += 1; time.sleep(1)
        taint = int(Path('/proc/sys/kernel/tainted').read_text())
        result = dict(kind='result', scope='linux-continuity-only',
            windows_userspace_confirmed=False, coexistence_passed=False,
            pass_=taint == 0, boot_id=boot, generation=generation,
            samples=seq, start_errors=errors, launch_finished=done.is_set(),
            kernel_taint=taint, final=state() if done.is_set() else None)
        result['pass'] = result.pop('pass_')
        (output / f'{generation}.json').write_text(json.dumps(result, indent=2) + '\n')
        connection.sendall((json.dumps(result) + '\n').encode())
