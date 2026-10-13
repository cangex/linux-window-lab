#!/usr/bin/env python3
"""Extend the frozen P3 official-media build with a cooperative P4 writer."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('p3_media',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
assert not a.output.exists();a.output.mkdir(parents=True)
here=Path(__file__).resolve().parent
run=lambda *args,**kw:subprocess.run(list(map(str,args)),check=True,**kw)
sha=lambda p:hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
media=a.output/'media';shutil.copytree(a.p3_media/'media',media)
writer=a.output/'lw4writer.exe'
run('x86_64-w64-mingw32-gcc','-O2','-Wall','-Wextra','-Werror','-static',here/'writer.c','-o',writer)
start=a.output/'startnet.cmd'
start.write_bytes(b'@echo off\r\nwpeinit\r\nstart "LWLAB P4 writer" /b X:\\Windows\\System32\\lw4writer.exe\r\nstart "LWLAB P3 heartbeat" /b X:\\Windows\\System32\\lwprobe.exe\r\n')
wim=media/'sources/boot.wim'
run('wimlib-imagex','update',wim,'1',input=f'add "{writer.resolve()}" /Windows/System32/lw4writer.exe\nadd "{start.resolve()}" /Windows/System32/startnet.cmd\n',text=True)
fat=a.output/'winpe-fat.img'
with fat.open('xb') as f:f.truncate(512*1024*1024)
run('mkfs.vfat','-F','32','-n','LWPEP4',fat)
run('mcopy','-s','-i',fat,*sorted(media.iterdir()),'::/')
(a.output/'media.json').write_text(json.dumps(dict(p3_media_manifest_sha256=sha(a.p3_media/'media.json'),writer_sha256=sha(writer),wim_sha256=sha(wim),fat_sha256=sha(fat)),indent=2)+'\n')
