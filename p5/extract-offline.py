#!/usr/bin/env python3
"""Recover truth from a stopped Windows clone without mounting its filesystem.

Run as root on the lab host. qemu-img's default image locks must remain enabled.
Output RAW is preserved as evidence; this script never repairs a filesystem.
"""
import argparse,os,struct,subprocess,zlib
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('disk',type=Path);p.add_argument('raw',type=Path);p.add_argument('truth',type=Path);a=p.parse_args()
assert os.geteuid()==0,'sudo required for a new read-only loop device'
assert a.disk.is_file() and not a.raw.exists() and not a.truth.exists()
subprocess.run(['qemu-img','convert','-f','qcow2','-O','raw',str(a.disk),str(a.raw)],check=True)
with a.raw.open('rb') as f:
 f.seek(512);header=bytearray(f.read(512));assert header[:8]==b'EFI PART'
 size,crc=struct.unpack_from('<II',header,12);assert 92<=size<=512
 struct.pack_into('<I',header,16,0);assert zlib.crc32(header[:size])==crc
 entry_lba,count,entry_size,table_crc=struct.unpack_from('<QIII',header,72)
 assert 3<=count<=4096 and entry_size==128
 f.seek(entry_lba*512);table=f.read(count*entry_size);assert zlib.crc32(table)==table_crc
 lo,hi=struct.unpack_from('<QQ',table,2*entry_size+32)
 assert lo<hi and (hi+1)*512<=a.raw.stat().st_size
loop=subprocess.check_output(['losetup','--read-only','--find','--show','--offset',str(lo*512),'--sizelimit',str((hi-lo+1)*512),str(a.raw)],text=True).strip()
try:
 with a.truth.open('xb') as out:subprocess.run(['ntfscat',loop,'/LWLAB/truth.jsonl'],stdout=out,check=True)
finally:subprocess.run(['losetup','-d',loop],check=True)
