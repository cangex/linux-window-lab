#!/usr/bin/env python3
"""P3 payload plus fixed exclusive PCI subtree and a second NUMA RAM extent."""
import argparse,json,shutil,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('--disk',type=Path,required=True);p.add_argument('--platform',type=Path,required=True);p.add_argument('--ram-smoke',action='store_true');a=p.parse_args()
here=Path(__file__).resolve().parent
c=json.loads(a.platform.read_text());bar=int(c['nvme_bar'],0);size=int(c['nvme_size'],0)
assert c['root_bus']==128 and c['endpoint_bus']==129 and size==0x4000 and bar%size==0
assert bar==0x81e00000
assert c['machine']=='pc-q35-8.2' and c['ecam_base']=='0xe0000000'
assert c['root_port_bar']=='0x82000000'
assert c['root_port_memory_window']==['0x81e00000','0x81ffffff']
assert c['root_port_prefetch_window']==['0x383000000000','0x3837ffffffff']
subprocess.run(['python3',str(here.parent/'p3/stage.py'),str(a.output),'--disk',str(a.disk)],check=True)
def edit(path,old,new):
 s=path.read_text();assert old in s,(path,old);path.write_text(s.replace(old,new))
pkg=a.output/'LwPartitionPkg';inc=pkg/'Include'
constants={'HIGH_BASE':0x280000000,'HIGH_SIZE':0x180000000,'HIGH_END':0x400000000,'NVME_BAR':bar,'NVME_SIZE':size,'NVME_ECAM':0xe8100000}
(inc/'P5Platform.h').write_text('#pragma once\n'+''.join(f'#define P5_{k} 0x{v:x}ULL\n' for k,v in constants.items()))
manifest=json.loads((a.output/'partition.json').read_text());manifest.update(p5_platform=c,high_memory_base='0x280000000',high_memory_size='0x180000000')
(a.output/'partition.json').write_text(json.dumps(manifest,indent=2)+'\n')
dest=pkg/'LwNvmeDxe';dest.mkdir()
for name in ('LwNvmeDxe.c','LwNvmeDxe.inf'):shutil.copyfile(here/name,dest/name)
for name in ('LwPartitionPkg.dsc','LwPartitionPkg.fdf'):
 f=pkg/name;prefix=' INF ' if name.endswith('.fdf') else ' '
 edit(f,' LwPartitionPkg/LwBdsDxe/LwBdsDxe.inf',' LwPartitionPkg/LwBdsDxe/LwBdsDxe.inf\n'+prefix+'LwPartitionPkg/LwNvmeDxe/LwNvmeDxe.inf\n'+prefix+'MdeModulePkg/Bus/Pci/NvmExpressDxe/NvmExpressDxe.inf')
bds=pkg/'LwBdsDxe/LwBdsDxe.c'
edit(bds,'#include <Protocol/Bds.h>','#include <Protocol/Bds.h>\n#include <Protocol/PciIo.h>')
edit(bds,' Status=gBS->LocateHandleBuffer(ByProtocol,&gEfiBlockIoProtocolGuid',
 ''' Status=gBS->LocateHandleBuffer(ByProtocol,&gEfiPciIoProtocolGuid,NULL,&Count,&Handles);
 if (EFI_ERROR(Status) || Count!=1) LwFail(0x501,Status);
 for (I=0;I<Count;I++) { Status=gBS->ConnectController(Handles[I],NULL,NULL,TRUE); DEBUG((DEBUG_ERROR,"P5 NVMe connect %r\\n",Status)); if(EFI_ERROR(Status))LwFail(0x502,Status); }
 FreePool(Handles);
 Status=gBS->LocateHandleBuffer(ByProtocol,&gEfiBlockIoProtocolGuid''')
edit(bds,'if (EFI_ERROR(Status) || Count!=1) LwFail(0x401,Status);','if (EFI_ERROR(Status)) LwFail(0x401,Status);')
edit(bds,'if (EFI_ERROR(Status) || Count!=1) LwFail(0x402,Status);\n Path=FileDevicePath(Handles[0],',
 '''if (EFI_ERROR(Status)) LwFail(0x402,Status);
 for(I=0;I<Count;I++) {
  EFI_DEVICE_PATH_PROTOCOL *D=DevicePathFromHandle(Handles[I]);
  if(D && DevicePathType(D)==ACPI_DEVICE_PATH)break;
 }
 if(I==Count)LwFail(0x503,Count);
 Path=FileDevicePath(Handles[I],''')
edit(pkg/'LwBdsDxe/LwBdsDxe.inf',' gEfiLoadedImageProtocolGuid',' gEfiPciIoProtocolGuid\n gEfiLoadedImageProtocolGuid')
cpu=pkg/'LwCpuDxe/LwCpuDxe.c'
edit(cpu,'#include <LwLab.h>','#include <LwLab.h>\n#include "P5Platform.h"')
edit(cpu,'if (Base<LW_BASE || Base>=LW_END || Length>LW_END-Base) return EFI_UNSUPPORTED;',
 '''if(Base>=P5_NVME_BAR && Base<P5_NVME_BAR+P5_NVME_SIZE && Length<=P5_NVME_BAR+P5_NVME_SIZE-Base) return Attr==EFI_MEMORY_UC?EFI_SUCCESS:EFI_UNSUPPORTED;
 if (!((Base>=LW_BASE && Base<LW_END && Length<=LW_END-Base) || (Base>=P5_HIGH_BASE && Base<P5_HIGH_END && Length<=P5_HIGH_END-Base))) return EFI_UNSUPPORTED;''')
asl='''DefinitionBlock ("", "DSDT", 2, "LWLAB", "PARTUEFI", 1) {
 Scope (\\_SB) {
  Device (CPU0) { Name (_HID,"ACPI0007") Name (_UID,@APIC_ID@) }
  Device (PCW0) {
   Name (_HID,EisaId("PNP0A08")) Name (_CID,EisaId("PNP0A03")) Name (_UID,128) Name (_SEG,0) Name (_BBN,128)
   Name (_CCA,1)
   Name (_CRS,ResourceTemplate () {
    WordBusNumber (ResourceProducer,MinFixed,MaxFixed,PosDecode,0,128,129,0,2)
    DWordMemory (ResourceProducer,PosDecode,MinFixed,MaxFixed,NonCacheable,ReadWrite,0,0x81e00000,0x82000fff,0,0x201000)
    QWordMemory (ResourceProducer,PosDecode,MinFixed,MaxFixed,Prefetchable,ReadWrite,0,0x383000000000,0x3837ffffffff,0,0x800000000)
   })
   Method (_OSC,4) { CreateDWordField(Arg3,0,STS0) CreateDWordField(Arg3,8,CTL0) And(CTL0,0x1F,CTL0) Return(Arg3) }
  }
 }
}
'''.replace('@BAR@',hex(bar)).replace('@END@',hex(bar+size-1)).replace('@SIZE@',hex(size))
(a.output/'dsdt.asl.in').write_text(asl)
pack=a.output/'pack.py'
edit(pack,'    allocation(b,0x10000,6)',"    hs.append(hob(3,bytes(16)+struct.pack('<IIQQ',0,0x2007,0x280000000,0x180000000)))\n    allocation(b,0x10000,6)")
edit(pack,"struct.pack('<BB6s',32,16,bytes(6))","struct.pack('<BB6s',48,16,bytes(6))")
edit(pack,"p['real_memory_base'],p['real_memory_size'],0,1,0),3)","p['real_memory_base'],p['real_memory_size'],0,1,0)+struct.pack('<BBIHQQIIQ',1,40,1,0,0x280000000,0x180000000,0,1,0),3)")
edit(pack,"    xs=put('XSDT'","    mc=put('MCFG',acpi_table(b'MCFG',bytes(8)+struct.pack('<QHBBI',0xe0000000,0,128,129,0),1))\n    xs=put('XSDT'")
edit(pack,"struct.pack('<QQQQ',madt,fa,sr,hp)","struct.pack('<QQQQQ',madt,fa,sr,hp,mc)")
edit(a.output/'verify-layout.py',"(0,c['real_memory_base'],c['real_memory_size'])]","(0,c['real_memory_base'],c['real_memory_size']),(0,0x280000000,0x180000000)]")
v=a.output/'verify-image.py'
edit(v,"struct.unpack('<4Q',xsdt[36:])","struct.unpack('<5Q',xsdt[36:])")
edit(v,"('APIC','FACP','SRAT','HPET')","('APIC','FACP','SRAT','HPET','MCFG')")
edit(v,"(number('real_memory_base'),number('real_memory_size'))]","(number('real_memory_base'),number('real_memory_size')),(0x280000000,0x180000000)]\nassert struct.unpack_from('<QHBBI',table('MCFG'),44)==(0xe0000000,0,128,129,0)")
if a.ram_smoke:
 edit(bds,'DevicePathType(D)==ACPI_DEVICE_PATH','DevicePathType(D)==HARDWARE_DEVICE_PATH')
print(a.output)
