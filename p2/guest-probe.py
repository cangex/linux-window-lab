#!/usr/bin/env python3
"""Persistent TCP + fsync/readback telemetry spanning the AP launch."""
import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import time
import threading

parser = argparse.ArgumentParser()
parser.add_argument('--seconds', type=int, default=30)
parser.add_argument('--flags', type=int, choices=[0], default=0)
args = parser.parse_args()
if socket.gethostname() != 'lwlab-boot':
    raise SystemExit('This probe is restricted to lwlab-boot')
if args.seconds < 1:
    raise SystemExit('--seconds must be positive')
control = Path('/sys/kernel/lwlab/control')
status = Path('/sys/kernel/lwlab/status')
boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
generation = secrets.randbelow(2**60) + 1
base, size, entry = 0x40000000, 0x10000000, 0x40010000

def state():
    return dict(item.split('=', 1) for item in status.read_text().split())

def prepare(version=2, cpu=4, memory=base, length=size, address=entry, gen=generation, flags=args.flags):
    return f'prepare {version} {cpu} {memory:x} {length:x} {address:x} {gen} {flags}\n'

def write_sysfs(path, command):
    # Buffered close() can retry a failed flush and issue a second command.
    # Sysfs control is a transaction: perform exactly one write syscall.
    data = command.encode()
    fd = os.open(path, os.O_WRONLY)
    try:
        if os.write(fd, data) != len(data):
            raise RuntimeError('partial sysfs command; deliberately not retried')
    finally:
        os.close(fd)

def write(command):
    write_sysfs(control, command)

def reject(command, wanted):
    before = state()
    try:
        write(command)
    except OSError as exc:
        assert exc.errno == wanted, (command, exc)
        after = state()
        assert after['state'] == before['state']
        assert after['generation'] == before['generation']
        return {'errno': exc.errno, 'state_unchanged': True}
    raise AssertionError('invalid request accepted: ' + command)

assert Path('/proc/sys/kernel/tainted').read_text().strip() == '0', 'Tainted kernel before launch'
serial = Path('/proc/tty/driver/serial').read_text()
assert 'port:000003F8' in serial and 'port:000002F8' not in serial, serial
assert '8250.nr_uarts=1' in Path('/proc/cmdline').read_text()
assert 'no_ipi_broadcast=1' in Path('/proc/cmdline').read_text()
checks = {}
checks['online_cpu'] = reject(prepare(cpu=4), errno.EBUSY)
checks['wrong_version'] = reject(prepare(version=1), errno.EINVAL)
checks['boot_cpu'] = reject(prepare(cpu=0), errno.EINVAL)
checks['zero_generation'] = reject(prepare(gen=0), errno.EINVAL)
checks['malformed'] = reject('prepare malformed\n', errno.EINVAL)
for cpu in range(4, 8):
    write_sysfs(Path(f'/sys/devices/system/cpu/cpu{cpu}/online'), '0\n')
checks['outside_memory'] = reject(prepare(memory=base + size), errno.ERANGE)
checks['wrong_size'] = reject(prepare(length=size*2), errno.ERANGE)
checks['illegal_entry'] = reject(prepare(address=entry+1), errno.ERANGE)
checks['entry_outside'] = reject(prepare(address=base+size), errno.ERANGE)
write(prepare())
assert state()['state'] == 'loaded'

server = socket.socket()
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(('0.0.0.0', 8081))
server.listen(1)
server.settimeout(60)
connection, peer = server.accept()
connection.settimeout(10)
connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
results = Path('/opt/lwlab/results/p2')
results.mkdir(parents=True, exist_ok=True)
path = results/'io-probe.bin'
start_error = None
start = time.monotonic()
launch_at = start + 5
end_at = None
launched = False
launching = False
done = threading.Event()
worker_failure = []
def launch():
    global start_error
    try:
        write('start\n')
    except OSError as exc:
        start_error = exc.errno
    except BaseException as exc:
        worker_failure.append(repr(exc))
    finally:
        done.set()
sequence = 0
last_heartbeat = None
try:
    while end_at is None or time.monotonic() < end_at:
        now = time.monotonic()
        if not launching and now >= launch_at:
            launching = True
            threading.Thread(target=launch, daemon=True).start()
        if launching and done.is_set() and not launched:
            assert not worker_failure, worker_failure
            assert start_error is None, (start_error, state())
            launched = True
            end_at = time.monotonic() + args.seconds
            assert state()['state'] == 'payload-ready', state()
            assert int(state()['checks'], 0) == 511, state()
            assert int(state()['timer_ticks']) > 0, state()
            assert state()['phase'] == '9', state()
            checks['second_start'] = reject('start\n', errno.EBUSY)
            checks['reload_after_start'] = reject(prepare(gen=generation+1), errno.EBUSY)
            try:
                write_sysfs(Path('/sys/devices/system/cpu/cpu4/online'), '1\n')
                raise AssertionError('started AP could be returned to Linux')
            except OSError as exc:
                assert exc.errno == errno.EBUSY, exc
                checks['reonline_after_start'] = {'errno': exc.errno}
        data = (f'{boot_id}:{generation}:{sequence}\n'.encode() * 128)
        with path.open('wb') as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        assert path.read_bytes() == data
        # sysfs status holds the launch mutex; do not block the I/O stream.
        sample = state() if not launching or done.is_set() else {"state":"launch-pending","heartbeat":"0"}
        if launched and args.flags == 0:
            assert sample['ack_generation'] == str(generation), sample
            assert sample['stage'] == '2' and sample['payload_error'] == '0', sample
            assert sample['actual_apic'] == sample['expected_apic'], sample
            hb = int(sample['heartbeat'])
            if last_heartbeat is not None:
                assert hb > last_heartbeat, sample
            last_heartbeat = hb
        message = {'kind': 'sample', 'boot_id': boot_id, 'sequence': sequence,
                   'monotonic': now, 'launched': launched, 'launch_pending': launching and not done.is_set(), 'state': sample,
                   'io_sha256': hashlib.sha256(data).hexdigest(), 'io_ok': True}
        connection.sendall((json.dumps(message) + '\n').encode())
        sequence += 1
        time.sleep(1)
    assert Path('/proc/sys/kernel/tainted').read_text().strip() == '0', 'Kernel became tainted'
    result = {'kind': 'result', 'pass': True, 'boot_id': boot_id, 'generation': generation,
              'seconds_after_start': args.seconds, 'samples': sequence, 'flags': args.flags,
              'start_errno': start_error, 'serial_ports': serial, 'kernel_taint': 0, 'negative_checks': checks, 'final': state()}
    (results/f'{generation}.json').write_text(json.dumps(result, indent=2)+'\n')
    connection.sendall((json.dumps(result)+'\n').encode())
finally:
    connection.close()
    server.close()
