#!/usr/bin/env python3
"""Decode the cooperative WinPE GDI heartbeat in its dedicated RAM GOP.

Only the P3 test application's 512x48 bitmap is interpreted. This is not a
Windows object parser or the Linux external reader planned for P4.
"""
import binascii
import struct
import zlib

WIDTH, HEIGHT = 1024, 768
FRAME_BYTES = WIDTH * HEIGHT * 4

def decode(frame):
    if len(frame) != FRAME_BYTES:
        raise ValueError('Incomplete framebuffer')
    record = bytearray(48)
    for bit in range(384):
        # Require all four central pixels to agree; reject partial GDI paints.
        values = []
        for dy, dx in ((3, 3), (3, 4), (4, 3), (4, 4)):
            at = ((700 + bit // 64 * 8 + dy) * WIDTH + bit % 64 * 8 + dx) * 4
            rgb = frame[at:at+3]
            if rgb == b'\x10' * 3: values.append(0)
            elif rgb == b'\xf0' * 3: values.append(1)
            else: raise ValueError('Heartbeat cell is not a valid palette color')
        if len(set(values)) != 1:
            raise ValueError('Torn heartbeat cell')
        record[bit // 8] |= values[0] << (bit % 8)
    magic, nonce, seq, tick, pid, version, crc, inverse = struct.unpack('<8sQQQIIII', record)
    if magic != b'LWP3HB01' or version != 1 or pid == 0 or nonce == 0:
        raise ValueError('Heartbeat identity/version mismatch')
    if binascii.crc32(record[:40]) != crc or inverse != (crc ^ 0xffffffff):
        raise ValueError('Heartbeat CRC mismatch')
    return dict(nonce=f'{nonce:016x}', sequence=seq, tick_ms=tick, pid=pid,
                version=version, crc32=f'{crc:08x}')

def png(frame):
    if len(frame) != FRAME_BYTES: raise ValueError('Incomplete framebuffer')
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', binascii.crc32(kind + data))
    rgb = bytearray(WIDTH * HEIGHT * 3)
    rgb[0::3] = frame[2::4]; rgb[1::3] = frame[1::4]; rgb[2::3] = frame[0::4]
    rows = b''.join(b'\0' + rgb[y*WIDTH*3:(y+1)*WIDTH*3] for y in range(HEIGHT))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', WIDTH, HEIGHT, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))

def validate_progress(frames, start, end, minimum_span=30):
    """Fail closed on stale/replayed frames, identity changes, or coverage gaps."""
    errors = []
    if len(frames) < 2:
        return dict(passed=False, errors=['Fewer than two userspace frames'])
    first, last = frames[0], frames[-1]
    identities = {(f['nonce'], f['pid'], f['version']) for f in frames}
    if len(identities) != 1: errors.append('Userspace identity changed')
    progresses = [first]
    for prev, cur in zip(frames, frames[1:]):
        if cur['sequence'] < prev['sequence'] or cur['tick_ms'] < prev['tick_ms']:
            errors.append('Sequence or tick regressed')
        if cur['sequence'] == prev['sequence']:
            if cur['tick_ms'] != prev['tick_ms']: errors.append('Tick changed without sequence')
        else:
            if cur['tick_ms'] <= prev['tick_ms']: errors.append('Sequence advanced without tick')
            progresses.append(cur)
    gaps = [b['received_monotonic']-a['received_monotonic'] for a,b in zip(progresses, progresses[1:])]
    trailing = end - progresses[-1]['received_monotonic']
    if max(gaps + [trailing], default=0) >= 8: errors.append('Userspace progress gap >= 8 seconds')
    if first['received_monotonic'] - start > 90: errors.append('Userspace startup exceeded 90 seconds')
    span = min(last['received_monotonic'], end) - max(first['received_monotonic'], start)
    if span < minimum_span: errors.append('Insufficient simultaneous coverage')
    wall = last['received_monotonic'] - first['received_monotonic']
    tick_span = (last['tick_ms'] - first['tick_ms']) / 1000
    if abs(wall - tick_span) > max(4, wall * 0.05): errors.append('Windows tick and host elapsed time disagree')
    return dict(passed=not errors, errors=sorted(set(errors)), samples=len(frames),
                progressing_samples=len(progresses), nonce=first['nonce'], pid=first['pid'],
                first_sequence=first['sequence'], last_sequence=last['sequence'],
                simultaneous_seconds=round(span, 3), windows_tick_seconds=tick_span,
                max_progress_gap_seconds=max(gaps + [trailing], default=0),
                first_received=first['received_monotonic'], last_received=last['received_monotonic'])
