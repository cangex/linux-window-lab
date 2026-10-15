#!/usr/bin/env python3
"""Derive 1/2/4 CPU ACPI variants from the verified P6 r5 payload.

Only the reserved ACPI blob changes. EDK2 code, HOBs, parking reservation,
embedded boot disk and all other bytes stay identical to the pinned input.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys

p = argparse.ArgumentParser()
p.add_argument('source', type=Path)
p.add_argument('output', type=Path)
p.add_argument('--cpus', type=int, choices=(1, 2, 4), required=True)
p.add_argument('--iasl', required=True)
a = p.parse_args()
assert not a.output.exists()
layout = json.loads((a.source / 'layout.json').read_text())
original = (a.source / 'partition.bin').read_bytes()
source_hash = hashlib.sha256(original).hexdigest()
assert source_hash == layout['payload_sha256'] == 'a85083a518da38af987ebca63f9d76aa22b111a5cb8eb2752e6c1e2af522fa1f'
a.output.mkdir(parents=True)
stage = a.output / 'stage'
subprocess.run([sys.executable, str(Path(__file__).with_name('stage.py')), str(stage),
                '--cpus', str(a.cpus), '--disk', str(a.source / 'partition.bin')], check=True)
spec = importlib.util.spec_from_file_location('pack', stage / 'pack.py')
pack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pack)
# Refuse any incidental platform change outside the explicit CPU fields.
cpu_fields = {'windows_cpus', 'windows_apic_ids', 'p6_cpu_count'}
assert {k: v for k, v in pack.cfg.items() if k not in cpu_fields} == {
    k: v for k, v in layout['manifest'].items() if k not in cpu_fields}
asl = a.output / 'dsdt.asl'
asl.write_text((stage / 'dsdt.asl.in').read_text().replace('@APIC_ID@', '4'))
subprocess.run([a.iasl, '-p', str(a.output / 'dsdt'), str(asl)], check=True)
tables, addresses = pack.acpi((a.output / 'dsdt.aml').read_bytes())
assert len(tables) == 0x10000 and addresses == layout['acpi']
offset = pack.A('acpi') - pack.A('entry')
raw = bytearray(original)
raw[offset:offset+len(tables)] = tables
assert raw[:offset] == original[:offset] and raw[offset+len(tables):] == original[offset+len(tables):]
layout['manifest'] = pack.cfg
assets = [x for x in layout['assets'] if int(x['address'], 0) == pack.A('acpi')]
assert len(assets) == 1 and assets[0]['size'] == len(tables)
assets[0]['sha256'] = hashlib.sha256(tables).hexdigest()
layout['payload_sha256'] = hashlib.sha256(raw).hexdigest()
layout['derived_from_sha256'] = source_hash
(a.output / 'partition.bin').write_bytes(raw)
(a.output / 'layout.json').write_text(json.dumps(layout, indent=2)+'\n')
subprocess.run([sys.executable, str(stage / 'verify-layout.py'), str(a.output)], check=True)
# Inspect the packed MADT and SRAT, independently of manifest CPU counts.
for table_name, header, stride, id_offset in [('APIC', 44, 8, 3), ('SRAT', 48, 16, 3)]:
    at = int(addresses[table_name], 0) - pack.A('acpi')
    length = struct.unpack_from('<I', tables, at+4)[0]
    cursor = header
    ids = []
    while cursor < length:
        kind, size = tables[at+cursor:at+cursor+2]
        assert size >= 2 and cursor+size <= length
        if kind == 0:
            assert size == stride
            ids.append(tables[at+cursor+id_offset])
        cursor += size
    assert ids == list(range(4, 4+a.cpus))
print(json.dumps(dict(cpu_count=a.cpus, sha256=layout['payload_sha256'], source_sha256=source_hash)))
