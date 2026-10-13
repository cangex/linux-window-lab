#!/usr/bin/env python3
"""Relocate the EDK2 core, build partition-only PI HOBs/ACPI, pack a flat AP image."""
import argparse,json,struct,uuid,hashlib,subprocess
from pathlib import Path
root=Path(__file__).resolve().parent
cfg=json.loads((root/'partition.json').read_text())
p={k:int(v,0) if isinstance(v,str) and v.startswith('0x') else v for k,v in cfg.items()}
b=p['memory_base']; end=b+p['memory_size']; A=lambda n:b+p[n+'_offset']
align=lambda n:(n+4095)&~4095
def guid(s):return uuid.UUID(s).bytes_le
def pe_load(raw,base):
    pe=struct.unpack_from('<I',raw,0x3c)[0]
    assert raw[:2]==b'MZ' and raw[pe:pe+4]==b'PE\0\0'
    machine,n=struct.unpack_from('<HH',raw,pe+4);assert machine==0x8664
    opt=pe+24;assert struct.unpack_from('<H',raw,opt)[0]==0x20b
    optsize=struct.unpack_from('<H',raw,pe+20)[0]
    entry=struct.unpack_from('<I',raw,opt+16)[0];old=struct.unpack_from('<Q',raw,opt+24)[0]
    size,headers=struct.unpack_from('<II',raw,opt+56);out=bytearray(align(size));out[:headers]=raw[:headers]
    for i in range(n):
        vs,va,rs,rp=struct.unpack_from('<IIII',raw,opt+optsize+i*40+8)
        assert va+max(vs,rs)<=len(out) and rp+rs<=len(raw)
        out[va:va+rs]=raw[rp:rp+rs]
    rel,sz=struct.unpack_from('<II',raw,opt+112+5*8);assert rel and sz
    cursor=rel
    while cursor<rel+sz:
        page,length=struct.unpack_from('<II',out,cursor);assert length>=8 and length%2==0
        for pos in range(cursor+8,cursor+length,2):
            item=struct.unpack_from('<H',out,pos)[0];kind=item>>12;where=page+(item&4095)
            if kind==0:continue
            assert kind==10,(kind,where)
            value=struct.unpack_from('<Q',out,where)[0]+base-old
            struct.pack_into('<Q',out,where,value&((1<<64)-1))
        cursor+=length
    return out,base+entry

def acpi_table(sig,body,revision):
    buf=bytearray(struct.pack('<4sIBB6s8sI4sI',sig,36+len(body),revision,0,b'LWLAB ',b'PARTUEFI',1,b'LWLB',1)+body)
    buf[9]=(-sum(buf))&255;return bytes(buf)
def acpi(dsdt):
    start=A('acpi');tables={}; cursor=start+0x1000
    def put(name,data):
        nonlocal cursor
        addr=cursor;tables[name]=(addr,data);cursor+=align(len(data));return addr
    ds=put('DSDT',dsdt)
    madt=put('APIC',acpi_table(b'APIC',struct.pack('<II',p['lapic_mmio'],0)+struct.pack('<BBBBI',0,8,p['apic_id'],p['apic_id'],1),5))
    # ACPI 6.5 FADT, hardware-reduced: no shared PM/SMI/RTC or reset registers.
    fadt=bytearray(276-36);struct.pack_into('<I',fadt,40-36,ds);fadt[45-36]=0
    struct.pack_into('<I',fadt,112-36,1<<20);fadt[131-36]=5;struct.pack_into('<Q',fadt,140-36,ds)
    fa=put('FACP',acpi_table(b'FACP',fadt,6))
    cpu=struct.pack('<BBBBIB3sI',0,16,p['cpu_proximity_domain'],p['apic_id'],1,0,b'\0'*3,0)
    mem=struct.pack('<BBIHQQIIQ',1,40,p['memory_proximity_domain'],0,b,p['memory_size'],0,1,0)
    sr=put('SRAT',acpi_table(b'SRAT',struct.pack('<IQ',1,0)+cpu+mem,3))
    xs=put('XSDT',acpi_table(b'XSDT',struct.pack('<QQQ',madt,fa,sr),1))
    rsdp=bytearray(36)
    rsdp[:8]=b'RSD PTR ';rsdp[9:15]=b'LWLAB ';rsdp[15]=2
    struct.pack_into('<I',rsdp,20,36);struct.pack_into('<Q',rsdp,24,xs)
    rsdp[8]=(-sum(rsdp[:20]))&255;rsdp[32]=(-sum(rsdp))&255
    output=bytearray(0x10000);output[:36]=rsdp
    for addr,data in tables.values():output[addr-start:addr-start+len(data)]=data
    assert cursor<=start+len(output)
    return output,{name:hex(addr) for name,(addr,data) in tables.items()}

def hobs(core_size,core_entry,fv_size):
    hs=[]
    def hob(t,data):
        length=(8+len(data)+7)&~7;return struct.pack('<HHI',t,length,0)+data+b'\0'*(length-8-len(data))
    def allocation(start,length,typ,name=None,extra=b''):
        if length:hs.append(hob(2,(guid(name) if name else bytes(16))+struct.pack('<QQII',start,length,typ,0)+extra))
    # A single tested WB RAM resource; nothing from the main Linux platform leaks in.
    hs.append(hob(3,bytes(16)+struct.pack('<IIQQ',0,0x2007,b,p['memory_size'])))
    allocation(b,0x10000,6)
    allocation(A('entry'),A('core')-A('entry'),0)
    allocation(A('core'),core_size,3,'f8e21975-0899-4f58-a4be-5525a9c6d77a',guid('d6a2cb7f-6a18-4e2f-b43b-9920a733700a')+struct.pack('<Q',core_entry))
    allocation(A('core')+core_size,A('fv')-A('core')-core_size,0)
    allocation(A('fv'),align(fv_size),4)
    allocation(A('fv')+align(fv_size),A('acpi')-A('fv')-align(fv_size),0)
    allocation(A('acpi'),0x10000,9)
    allocation(A('acpi')+0x10000,A('stack')-A('acpi')-0x10000,0)
    allocation(A('stack'),p['stack_size'],4,'4ed4bf27-4092-42e9-807d-527b1d00c9bd')
    allocation(A('stack')+p['stack_size'],A('free')-A('stack')-p['stack_size'],0)
    hs.append(hob(5,struct.pack('<QQ',A('fv'),fv_size)))
    hs.append(hob(6,struct.pack('<BB6s',32,16,bytes(6))))
    body=b''.join(hs);finish=A('hob')+56+len(body)
    phit=hob(1,struct.pack('<IIQQQQQ',9,0,end,A('hob'),end,A('free'),finish))
    return phit+body+hob(0xffff,b'')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('build',type=Path);ap.add_argument('output',type=Path);args=ap.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    asm=args.output/'bootstrap.bin';subprocess.run(['nasm','-f','bin','-I',str(root)+'/',str(root/'bootstrap.asm'),'-o',str(asm)],check=True)
    core,entry=pe_load((args.build/'X64/DxeCore.efi').read_bytes(),A('core'))
    fv=(args.build/'FV/LWFV.Fv').read_bytes();assert len(fv)<p['disk_offset']-p['fv_offset']
    boot=bytearray(asm.read_bytes());token=struct.pack('<Q',0x4c57434f52454e54);assert boot.count(token)==1;boot[boot.index(token):boot.index(token)+8]=struct.pack('<Q',entry)
    asl=args.output/'dsdt.asl';asl.write_text(f'DefinitionBlock ("", "DSDT", 2, "LWLAB", "PARTUEFI", 1) {{ Scope (\\_SB) {{ Device (CPU0) {{ Name (_HID, "ACPI0007") Name (_UID, {p["apic_id"]}) }} }} }}\n')
    subprocess.run(['iasl','-p',str(args.output/'dsdt'),str(asl)],check=True)
    tables,addresses=acpi((args.output/'dsdt.aml').read_bytes())
    disk=args.output/'disk.img';disk.write_bytes(bytes(p['disk_size']))
    subprocess.run(['mkfs.vfat','-F','12','-n','LWLAB',str(disk)],check=True)
    marker=args.output/'MARKER.TXT';marker.write_bytes(b'LWLAB P2 partition-only file\r\n')
    for src,name in [(args.build/'X64/P2SelfTest.efi','P2TEST.EFI'),(args.build/'X64/P2Child.efi','P2CHILD.EFI'),(marker,'MARKER.TXT')]:
        subprocess.run(['mcopy','-i',str(disk),str(src),'::'+name],check=True)
    out=bytearray(A('acpi')+len(tables)-A('entry'))
    assets=[(A('entry'),boot),(A('core'),core),(A('fv'),fv),(A('disk'),disk.read_bytes()),(A('hob'),hobs(len(core),entry,len(fv))),(A('acpi'),tables)]
    for addr,data in assets:out[addr-A('entry'):addr-A('entry')+len(data)]=data
    (args.output/'partition.bin').write_bytes(out)
    (args.output/'layout.json').write_text(json.dumps({'manifest':cfg,'core_entry':hex(entry),'acpi':addresses,'assets':[{'address':hex(a),'size':len(d),'sha256':hashlib.sha256(d).hexdigest()} for a,d in assets],'payload_sha256':hashlib.sha256(out).hexdigest()},indent=2)+'\n')
if __name__=='__main__':main()
