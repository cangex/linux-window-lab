#!/usr/bin/env python3
"""P6 fixed-Q35 multi-AP platform, retaining P5's memory/device ownership."""
import argparse,json,subprocess,shutil
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('--disk',type=Path,required=True)
p.add_argument('--cpus',type=int,choices=(1,2,4),required=True)
p.add_argument('--hal-ipi-mode',choices=('probe','enforce'))
a=p.parse_args()
here=Path(__file__).resolve().parent
subprocess.run(['python3',str(here.parent/'p5/stage.py'),str(a.output),'--disk',str(a.disk),
 '--platform',str(here.parent/'p5/platform.json')],check=True)
def edit(name,old,new):
 f=a.output/name;s=f.read_text();assert s.count(old)==1,(name,old,s.count(old));f.write_text(s.replace(old,new))
cpus=list(range(4,4+a.cpus))
manifest=a.output/'partition.json';c=json.loads(manifest.read_text())
c.update(windows_cpus=cpus,windows_apic_ids=cpus,p6_cpu_count=a.cpus)
manifest.write_text(json.dumps(c,indent=2)+'\n')
edit('pack.py','    allocation(b,0x10000,6)','    allocation(0x6f000,0x1000,0)\n    allocation(b,0x10000,6)')
edit('verify-layout.py','allocations=[];types=[];resources=[]',
 'allocations=[];types=[];resources=[];parking=0')
edit('verify-layout.py',
 '  assert base<=start and start+size<=end\n  for lo,hi in allocations:assert start+size<=lo or start>=hi\n  allocations.append((start,start+size))',
 '''  if start==0x6f000:
   assert size==4096 and kind==0
   assert c['real_memory_base']<=start and start+size<=c['real_memory_base']+c['real_memory_size']
   parking+=1
  else:
   assert base<=start and start+size<=end
   for lo,hi in allocations:assert start+size<=lo or start>=hi
   allocations.append((start,start+size))''')
edit('verify-layout.py','assert sorted(allocations)[0][0]==base',
 'assert parking==1\nassert sorted(allocations)[0][0]==base')
edit('verify-image.py','assert fb_reserved',
 "assert fb_reserved\n# Parking page must remain outside all Windows allocations.\nhob=base+number('hob_offset'); park=False\nfor _ in range(100):\n    kind,length=struct.unpack('<HH',read(hob,4))\n    if kind==2:\n        lo,size,typ=struct.unpack_from('<QQI',read(hob,length),24)\n        if lo==0x6f000 and size==4096 and typ==0:park=True\n    if kind==0xffff:break\n    hob+=length\nassert park")
edit('pack.py',"struct.pack('<BBBBI',0,8,p['apic_id'],p['apic_id'],1)",
 "b''.join(struct.pack('<BBBBI',0,8,i,i,1) for i in p['windows_apic_ids'])")
edit('pack.py',"cpu=struct.pack('<BBBBIB3sI',0,16,p['cpu_proximity_domain'],p['apic_id'],1,0,b'\\0'*3,0)",
 "cpu=b''.join(struct.pack('<BBBBIB3sI',0,16,p['cpu_proximity_domain'],i,1,0,b'\\0'*3,0) for i in p['windows_apic_ids'])")
edit('dsdt.asl.in','Device (CPU0) { Name (_HID,"ACPI0007") Name (_UID,@APIC_ID@) }',
 '\n  '.join(f'Device (CPU{i}) {{ Name (_HID,"ACPI0007") Name (_UID,{apic}) }}' for i,apic in enumerate(cpus)))
edit('verify-image.py',"struct.pack('<BBBBI',0,8,c['apic_id'],c['apic_id'],1)",
 "b''.join(struct.pack('<BBBBI',0,8,i,i,1) for i in c['windows_apic_ids'])")
edit('verify-image.py',"assert cpus==[(c['apic_id'],1)]","assert cpus==[(i,1) for i in c['windows_apic_ids']]")
edit('verify-image.py',"'MADT single AP/IOAPIC'","'MADT partition CPUs/IOAPIC'")
if a.hal_ipi_mode:
 directory=a.output/'LwPartitionPkg/LwBdsDxe'
 shutil.copy2(here/'HalIpi.h',directory/'HalIpi.h')
 edit('LwPartitionPkg/LwBdsDxe/LwBdsDxe.c','#include "RamGop.h"',
  '#include "RamGop.h"\n#define LW_HAL_IPI_MODE '+str(1 if a.hal_ipi_mode=='probe' else 2)+'\n#include "HalIpi.h"')
 edit('LwPartitionPkg/LwBdsDxe/LwBdsDxe.c','if (!EFI_ERROR(Status)) { LW_MBOX->Phase=21;',
  'if (!EFI_ERROR(Status)) { LwHalIpiConfigure(); LW_MBOX->Phase=21;')
 c['p6_hal_ipi_mode']=a.hal_ipi_mode
 manifest.write_text(json.dumps(c,indent=2)+'\n')
print(json.dumps(dict(stage=str(a.output),windows_cpus=cpus,linux_cpus=[0,1,2,3],hal_ipi_mode=a.hal_ipi_mode)))
