#!/usr/bin/env python3
"""Wrap a FAT volume in a deterministic GPT ESP for the control VM/UEFI disk."""
import argparse
import binascii
from pathlib import Path
import shutil
import struct
import uuid

p = argparse.ArgumentParser()
p.add_argument('fat', type=Path)
p.add_argument('output', type=Path)
a = p.parse_args()
size = a.fat.stat().st_size
assert size % 512 == 0
start, sectors = 2048, size // 512
total = sectors + 4096
disk_guid = uuid.UUID('f8e93052-c3f9-49d7-8620-c2c212688d11').bytes_le
esp_guid = uuid.UUID('2985c875-fd74-44eb-b2e9-e7f42c1b7d17').bytes_le
entries = bytearray(128 * 128)
struct.pack_into('<16s16sQQQ', entries, 0,
    uuid.UUID('c12a7328-f81f-11d2-ba4b-00a0c93ec93b').bytes_le,
    esp_guid, start, start + sectors - 1, 0)
entries[56:56+10] = 'LWPE3'.encode('utf-16le')
def header(current, alternate, table):
    data = bytearray(512)
    struct.pack_into('<8sIIIIQQQQ16sQIII', data, 0, b'EFI PART', 0x10000, 92,
        0, 0, current, alternate, 34, total-34, disk_guid, table, 128, 128,
        binascii.crc32(entries))
    struct.pack_into('<I', data, 16, binascii.crc32(data[:92]))
    return data
with a.output.open('xb') as out:
    out.truncate(total * 512)
    mbr = bytearray(512)
    mbr[446:462] = struct.pack('<B3sB3sII', 0, b'\0\2\0', 0xee,
                               b'\xff'*3, 1, min(total-1, 0xffffffff))
    mbr[510:512] = b'\x55\xaa'
    out.write(mbr); out.write(header(1, total-1, 2)); out.write(entries)
    out.seek(start*512)
    with a.fat.open('rb') as src:
        shutil.copyfileobj(src, out)
    out.seek((total-33)*512); out.write(entries); out.write(header(total-1, 1, total-33))
