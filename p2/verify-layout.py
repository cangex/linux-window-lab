#!/usr/bin/env python3
"""Independent structural checks of the *packed* image, before AP launch."""
import argparse,hashlib,json,struct
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args()
layout=json.loads((a.directory/'layout.json').read_text());cfg=layout['manifest']
c={k:int(v,0) if isinstance(v,str) and v.startswith('0x') else v for k,v in cfg.items()}
base=c['memory_base'];end=base+c['memory_size'];entry=base+c['entry_offset']
raw=(a.directory/'partition.bin').read_bytes()
assert hashlib.sha256(raw).hexdigest()==layout['payload_sha256']
def read(address,size):
 assert entry<=address and address+size<=entry+len(raw),(hex(address),size)
 return raw[address-entry:address-entry+size]
ranges=[]
for item in layout['assets']:
 start=int(item['address'],0);size=item['size'];data=read(start,size)
 assert hashlib.sha256(data).hexdigest()==item['sha256']
 assert size>0 and base<=start and start+size<=end
 for lo,hi in ranges:assert start+size<=lo or start>=hi
 ranges.append((start,start+size))
rsdp=read(base+c['acpi_offset'],36)
assert rsdp[:8]==b'RSD PTR ' and sum(rsdp[:20])%256==sum(rsdp)%256==0
for name,address in layout['acpi'].items():
 addr=int(address,0);head=read(addr,36);length=struct.unpack_from('<I',head,4)[0]
 table=read(addr,length);assert table[:4].decode()==name and sum(table)%256==0
hob=base+c['hob_offset'];allocations=[];types=[];resources=[]
for _ in range(100):
 typ,length,res=struct.unpack('<HHI',read(hob,8));assert length>=8 and length%8==0 and res==0
 data=read(hob,length);types.append(typ)
 if typ==1:
  version,boot,top,bottom,free_top,free_bottom,finish=struct.unpack_from('<IIQQQQQ',data,8)
  assert top==free_top==end and free_bottom==base+c['free_offset'] and bottom<=hob
 elif typ==2:
  start,size,kind=struct.unpack_from('<QQI',data,24);assert size>0 and not(start%4096 or size%4096)
  assert base<=start and start+size<=end
  for lo,hi in allocations:assert start+size<=lo or start>=hi
  allocations.append((start,start+size))
 elif typ==3:
  kind,attrs,start,size=struct.unpack_from('<IIQQ',data,24);resources.append((kind,start,size))
 elif typ==0xffff:
  assert hob==finish;break
 hob+=length
else:raise AssertionError('missing HOB terminator')
assert resources==[(0,base,c['memory_size'])]
assert 5 in types and 6 in types and types[0]==1
assert sorted(allocations)[0][0]==base
for first,second in zip(sorted(allocations),sorted(allocations)[1:]):assert first[1]==second[0]
assert sorted(allocations)[-1][1]==base+c['free_offset']
print(json.dumps({'pass':True,'assets':len(ranges),'acpi_tables':len(layout['acpi']),'allocation_hobs':len(allocations),'payload_sha256':layout['payload_sha256']},indent=2))
