#!/usr/bin/env python3
"""Linux lab assembly of official ADK files, with an explicit userspace probe.

This does not run Microsoft's Windows-only copype/DISM tooling. Preserve the
original WIM and record exactly what is added to the experimental copy.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

def run(*args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def main():
    p = argparse.ArgumentParser()
    p.add_argument('addon', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    catalog_path = Path(__file__).with_name('media-source.json')
    catalog = json.loads(catalog_path.read_text())
    inputs = {}
    for item in catalog['files']:
        source = a.addon / item['path']
        with source.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha1').hexdigest()
        if source.stat().st_size != item['size'] or digest != item['sha1']:
            raise ValueError(f'Pinned Microsoft input mismatch: {source.name}')
        inputs[item['path']] = sha(source)
    if a.output.exists():
        p.error('Output exists; use a fresh directory to preserve evidence')
    a.output.mkdir(parents=True)
    out = a.output.resolve()
    extracted = out / 'extracted'
    for msi in sorted(a.addon / item['path'] for item in catalog['files'] if item['path'].endswith('.msi')):
        run('msiextract', '-C', extracted, msi, stdout=subprocess.DEVNULL)
    candidates = list(extracted.glob('**/amd64/en-us/winpe.wim'))
    if len(candidates) != 1:
        raise ValueError(f'Expected one amd64 WIM: {candidates}')
    wim = candidates[0]
    media = out / 'media'
    shutil.copytree(wim.parent.parent / 'Media', media)
    (media / 'sources').mkdir()
    bootwim = media / 'sources/boot.wim'
    shutil.copyfile(wim, bootwim)
    info = run('wimlib-imagex', 'info', wim, capture_output=True, text=True).stdout
    (out / 'wim-info.txt').write_text(info)
    run('wimlib-imagex', 'extract', wim, '1',
        'Windows/Boot/EFI_EX/bootmgfw_EX.efi', '--dest-dir=' + str(out / 'bootex'))
    bootmgr = out / 'bootex/bootmgfw_EX.efi'
    shutil.copyfile(bootmgr, media / 'EFI/Boot/bootx64.efi')
    shutil.copyfile(bootmgr, media / 'EFI/Microsoft/Boot/bootmgfw.efi')
    probe = out / 'lwprobe.exe'
    run('x86_64-w64-mingw32-gcc', '-O2', '-Wall', '-Wextra', '-Werror',
        '-static', Path(__file__).with_name('winpe-probe.c'), '-lgdi32', '-luser32', '-o', probe)
    startnet = out / 'startnet.cmd'
    startnet.write_bytes(b'@echo off\r\nwpeinit\r\nstart "LWLAB userspace probe" /b X:\\Windows\\System32\\lwprobe.exe\r\n')
    commands = (f'add "{probe}" /Windows/System32/lwprobe.exe\n'
                f'add "{startnet}" /Windows/System32/startnet.cmd\n')
    run('wimlib-imagex', 'update', bootwim, '1', input=commands, text=True)
    disk = out / 'winpe-fat.img'
    with disk.open('wb') as f:
        f.truncate(512 * 1024 * 1024)
    run('mkfs.vfat', '-F', '32', '-n', 'LWPEP3', disk)
    run('mcopy', '-s', '-i', disk, *sorted(media.iterdir()), '::/')
    files = {str(f.relative_to(media)): sha(f) for f in sorted(media.rglob('*')) if f.is_file()}
    report = dict(architecture='amd64', assembly='Linux msiextract/wimlib/mtools',
                  addon_version=catalog['version'], source_catalog_sha256=sha(catalog_path),
                  input_sha256=inputs,
                  original_wim_sha256=sha(wim), probe_sha256=sha(probe),
                  fat_sha256=sha(disk), bootex=True, files=files,
                  baseline_boot_passed=False, coexistence_passed=False)
    (out / 'media.json').write_text(json.dumps(report, indent=2) + '\n')

if __name__ == '__main__':
    main()
