#!/usr/bin/env python3
"""P3-specific checks on the packed bytes, independent of the generators."""
import argparse
import binascii
import json
from pathlib import Path
import struct
import uuid

p=argparse.ArgumentParser()
p.add_argument('directory',type=Path)
a=p.parse_args()
layout=json.loads((a.directory/'layout.json').read_text())
c=layout['manifest']
number=lambda k:int(c[k],0)
base=number('memory_base'); entry=base+number('entry_offset')
raw=(a.directory/'partition.bin').read_bytes()
def read(addr,n):
    assert entry<=addr and addr+n<=entry+len(raw)
    return raw[addr-entry:addr-entry+n]
def table(name):
    addr=int(layout['acpi'][name],0)
    n=struct.unpack_from('<I',read(addr,8),4)[0]
    data=read(addr,n)
    assert data[:4].decode()==name and sum(data)%256==0
    return data
madt=table('APIC')
assert struct.unpack_from('<II',madt,36)==(number('lapic_mmio'),0)
assert madt[44:]==struct.pack('<BBBBI',0,8,c['apic_id'],c['apic_id'],1)+struct.pack('<BBBBII',1,12,0,0,0xfec00000,0)
fadt=table('FACP')
assert len(fadt)==276 and struct.unpack_from('<I',fadt,112)[0]==1<<20
assert not any(fadt[48:112]) # no legacy PM/SMI/RTC control addresses
assert not any(fadt[116:129]) # no global reset GAS/value
assert struct.unpack_from('<Q',fadt,140)[0]==int(layout['acpi']['DSDT'],0)
hpet=table('HPET')
assert struct.unpack_from('<I',hpet,36)[0]==0x8086a201
assert struct.unpack_from('<BBBBQ',hpet,40)==(0,64,0,0,0xfed00000)
xsdt=table('XSDT')
assert list(struct.unpack('<4Q',xsdt[36:]))==[int(layout['acpi'][n],0) for n in ('APIC','FACP','SRAT','HPET')]
srat=table('SRAT'); cursor=48; cpus=[]; memory=[]
while cursor<len(srat):
    kind,length=srat[cursor:cursor+2]
    assert length>=2 and cursor+length<=len(srat)
    if kind==0:
        assert length==16
        cpus.append((srat[cursor+3],struct.unpack_from('<I',srat,cursor+4)[0]))
    elif kind==1:
        assert length==40
        memory.append(struct.unpack_from('<QQ',srat,cursor+8))
        assert struct.unpack_from('<I',srat,cursor+28)[0]==1
    else: raise AssertionError('Unexpected SRAT resource')
    cursor+=length
assert cpus==[(c['apic_id'],1)]
assert memory==[(number('memory_base'),number('memory_size')),
                (number('low_memory_base'),number('low_memory_size')),
                (number('real_memory_base'),number('real_memory_size'))]
fb=int(c['framebuffer']['base'],0); fb_end=fb+int(c['framebuffer']['bytes'],0)
assert base+number('entry_offset')<fb<fb_end<=base+number('core_offset')
for asset in layout['assets']:
    at=int(asset['address'],0)
    assert at+asset['size']<=fb or at>=fb_end
# The HOB entry-to-core reserved allocation owns the GOP, preventing EFI allocation.
hob=base+number('hob_offset'); fb_reserved=False
for _ in range(100):
    kind,length=struct.unpack_from('<HH',read(hob,8))
    assert length>=8
    if kind==2:
        lo,size,typ=struct.unpack_from('<QQI',read(hob,length),24)
        if lo<=fb and fb_end<=lo+size:
            assert typ==0; fb_reserved=True
    if kind==0xffff: break
    hob+=length
assert fb_reserved
# Validate protective MBR and both GPT copies, including table/header CRCs.
disk=read(base+number('disk_offset'),number('disk_size'))
assert disk[510:512]==b'\x55\xaa' and disk[450]==0xee
sectors=len(disk)//512
headers=[]
for lba,other in ((1,sectors-1),(sectors-1,1)):
    h=bytearray(disk[lba*512:(lba+1)*512])
    assert h[:8]==b'EFI PART'
    revision,size,crc=struct.unpack_from('<III',h,8)
    assert revision==0x10000 and size==92
    struct.pack_into('<I',h,16,0)
    assert binascii.crc32(h[:size])==crc
    assert struct.unpack_from('<QQ',h,24)==(lba,other)
    loc,count,width,table_crc=struct.unpack_from('<QIII',h,72)
    assert count==128 and width==128
    entries=disk[loc*512:loc*512+count*width]
    assert binascii.crc32(entries)==table_crc
    assert entries[:16]==uuid.UUID('c12a7328-f81f-11d2-ba4b-00a0c93ec93b').bytes_le
    lo,hi=struct.unpack_from('<QQ',entries,32)
    assert lo==2048 and (hi-lo+1)*512==512*1024*1024
    assert hi<sectors-33 and not any(entries[128:])
    assert disk[lo*512+510:lo*512+512]==b'\x55\xaa'
    headers.append(entries)
assert headers[0]==headers[1]
print(json.dumps(dict(passed=True,checks=['MADT single AP/IOAPIC','hardware-reduced FADT',
    'HPET address','XSDT references','SRAT owned RAM only','reserved RAM GOP',
    'primary/backup GPT CRC and ESP bounds']),indent=2))
