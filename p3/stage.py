#!/usr/bin/env python3
"""Materialize P3 from frozen P2 scaffolding without modifying P2 sources."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

p = argparse.ArgumentParser()
p.add_argument('output', type=Path)
p.add_argument('--disk', type=Path, required=True)
a = p.parse_args()
here = Path(__file__).resolve().parent
# P3 is a fixed Q35 experiment. Reject manifest edits that disagree with the
# loader, RAM GOP, guest launcher, or the hard-coded platform-table templates.
manifest = json.loads((here / 'partition.json').read_text())
fixed = dict(version=3, boot_cpu=4, apic_id=4, memory_base='0x10000000',
    memory_size='0x60000000', low_memory_base='0x100000', low_memory_size='0xf00000',
    real_memory_base='0x50000', real_memory_size='0x20000', serial_io='0x2f8',
    lapic_mmio='0xfee00000', entry_offset='0x10000', core_offset='0x800000')
for field, value in fixed.items():
    if manifest[field] != value: raise ValueError(f'Unsupported P3 platform change: {field}')
assert manifest['linux_cpus'] == [0,1,2,3] and manifest['offline_cpus'] == [4,5,6,7]
assert manifest['pci'] == []
assert manifest['framebuffer']['base'] == '0x10200000' and manifest['framebuffer']['bytes'] == '0x300000'
assert len(manifest['ioapic']) == 1 and manifest['ioapic'][0]['address'] == '0xfec00000'
assert manifest['ioapic'][0]['id'] == manifest['ioapic'][0]['gsi_base'] == 0
assert manifest['hpet']['address'] == '0xfed00000'
if a.output.exists():
    p.error('Use a fresh staging directory')
shutil.copytree(here.parent / 'p2', a.output, ignore=shutil.ignore_patterns('__pycache__'))
shutil.copyfile(here / 'partition.json', a.output / 'partition.json')
shutil.copyfile(here / 'verify-image.py', a.output / 'verify-image.py')
shutil.copyfile(here / 'kernel/lwlab.c', a.output / 'kernel/lwlab.c')
pkg = a.output / 'LwPartitionPkg'
for source in (here / 'LwPartitionPkg').rglob('*'):
    if source.is_file():
        target = pkg / source.relative_to(here / 'LwPartitionPkg')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
def edit(path, old, new):
    text = path.read_text()
    if old not in text:
        raise ValueError(f'P2 input changed: {path}: {old!r}')
    path.write_text(text.replace(old, new))
edit(a.output / 'generate.py', '256<<20', '1536<<20')
edit(a.output / 'generate.py', 'b % (1<<30)', 'b % (2<<20)')
edit(a.output / 'generate.py', "d={'BASE':b", "d={'REAL_BASE':v['real_memory_base'],'REAL_SIZE':v['real_memory_size'],'LOW_BASE':v['low_memory_base'],'LOW_SIZE':v['low_memory_size'],'BASE':b")
edit(a.output / 'build-uefi.sh', 'source edksetup.sh', 'set --\nsource edksetup.sh')
with (a.output / 'build-uefi.sh').open('a') as build:
    build.write('python3 "$P2_DIR/verify-image.py" "$OUTPUT"\n')
edit(a.output / 'bootstrap.asm', 'cmp dword [r12+8],2', 'cmp dword [r12+8],3')
pack = a.output / 'pack.py'
text = pack.read_text()
start = text.index("    disk=args.output/'disk.img'")
end = text.index('    out=bytearray(', start)
text = text[:start] + ('    disk=Path(' + repr(str(a.disk.resolve())) + ')\n'
                     "    assert disk.stat().st_size==p['disk_size']\n") + text[end:]
pack.write_text(text)
shutil.copyfile(here / 'dsdt.asl.in', a.output / 'dsdt.asl.in')
lines = pack.read_text().splitlines()
lines = ["    asl=args.output/'dsdt.asl';asl.write_text((root/'dsdt.asl.in').read_text().replace('@APIC_ID@',str(p['apic_id'])))"
         if line.startswith("    asl=args.output/'dsdt.asl';") else line for line in lines]
pack.write_text('\n'.join(lines)+'\n')
edit(pack, "    allocation(b,0x10000,6)",
     "    hs.append(hob(3,bytes(16)+struct.pack('<IIQQ',0,0x2007,p['low_memory_base'],p['low_memory_size'])))\n"
     "    hs.append(hob(3,bytes(16)+struct.pack('<IIQQ',0,0x2007,p['real_memory_base'],p['real_memory_size'])))\n"
     "    allocation(b,0x10000,6)")
edit(pack, "+cpu+mem,3)",
     "+cpu+mem+struct.pack('<BBIHQQIIQ',1,40,p['memory_proximity_domain'],0,p['low_memory_base'],p['low_memory_size'],0,1,0)+struct.pack('<BBIHQQIIQ',1,40,p['memory_proximity_domain'],0,p['real_memory_base'],p['real_memory_size'],0,1,0),3)")
edit(pack, "p['apic_id'],p['apic_id'],1),5)",
     "p['apic_id'],p['apic_id'],1)+struct.pack('<BBBBII',1,12,0,0,0xfec00000,0),5)")
edit(pack, "    xs=put('XSDT'", "    hp=put('HPET',acpi_table(b'HPET',struct.pack('<IBBBBQBHB',0x8086a201,0,64,0,0,0xfed00000,0,0,0),1))\n    xs=put('XSDT'")
edit(pack, "struct.pack('<QQQ',madt,fa,sr)", "struct.pack('<QQQQ',madt,fa,sr,hp)")
edit(a.output / 'verify-layout.py', "assert resources==[(0,base,c['memory_size'])]",
     "assert resources==[(0,base,c['memory_size']),(0,c['low_memory_base'],c['low_memory_size']),(0,c['real_memory_base'],c['real_memory_size'])]")
subprocess.run(['python3', str(a.output / 'generate.py')], check=True)
for name in ('LwPartitionPkg.dsc', 'LwPartitionPkg.fdf'):
    path = pkg / name
    path.write_text('\n'.join(line for line in path.read_text().splitlines()
                             if '/SelfTest/' not in line and '/Child/' not in line) + '\n')
    edit(path, 'FatPkg/EnhancedFatDxe/Fat.inf',
         'MdeModulePkg/Universal/Disk/PartitionDxe/PartitionDxe.inf\n'
         + (' INF ' if name.endswith('.fdf') else ' ') + 'FatPkg/EnhancedFatDxe/Fat.inf')
inf = pkg / 'LwBdsDxe/LwBdsDxe.inf'
edit(inf, ' DebugLib', ' DebugLib\n SerialPortLib\n BaseMemoryLib')
edit(inf, ' gEfiSimpleFileSystemProtocolGuid',
     ' gEfiSimpleFileSystemProtocolGuid\n gEfiLoadedImageProtocolGuid\n gEfiSimpleTextOutProtocolGuid\n gEfiSimpleTextInProtocolGuid\n gEfiGraphicsOutputProtocolGuid\n gEfiDevicePathProtocolGuid')
edit(inf, ' gEfiEndOfDxeEventGroupGuid', ' gEfiEndOfDxeEventGroupGuid\n gEfiEventExitBootServicesGuid')
print(a.output)
