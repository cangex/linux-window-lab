#!/usr/bin/env python3
"""Exercise the actual firmware matcher on the pinned PE and corrupted copies.

Input is the legally supplied lab Windows binary, never bundled in this repo.
This validates matching only; live boot proof is still required for the flag.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

p = argparse.ArgumentParser()
p.add_argument('kernel', type=Path)
a = p.parse_args()
raw = a.kernel.read_bytes()
assert hashlib.sha256(raw).hexdigest() == '93db70780a95192d13d04b4c3cb49c22a138063adba5c83d4855be02b645fdd0'
pe = struct.unpack_from('<I', raw, 60)[0]
count = struct.unpack_from('<H', raw, pe+6)[0]
optional = struct.unpack_from('<H', raw, pe+20)[0]
size, headers = struct.unpack_from('<II', raw, pe+24+56)
assert size == 0x144f000
mapped = bytearray(size)
mapped[:headers] = raw[:headers]
for i in range(count):
    vs, va, rs, rp = struct.unpack_from('<IIII', raw, pe+24+optional+i*40+8)
    assert va+max(vs, rs) <= size and rp+rs <= len(raw)
    mapped[va:va+rs] = raw[rp:rp+rs]
assert mapped[0xe0fc1c] == 0
matcher = Path(__file__).with_name('HalIpi.h').read_text().split('STATIC VOID LwHalIpiConfigure')[0]
source = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define STATIC static
#define CONST const
#define TRUE 1
#define FALSE 0
typedef int BOOLEAN;
typedef uint8_t UINT8;
typedef uint16_t UINT16;
typedef uint32_t UINT32;
static UINT16 ReadUnaligned16(UINT16 *p) { UINT16 v; memcpy(&v,p,2); return v; }
static UINT32 ReadUnaligned32(UINT32 *p) { UINT32 v; memcpy(&v,p,4); return v; }
#define CompareMem memcmp
''' + matcher + r'''
int main(int argc, char **argv) {
  if(argc!=2)return 10;
  FILE *f=fopen(argv[1],"rb"); if(!f)return 11;
  UINT8 *b=malloc(LW_HAL_IMAGE_SIZE); if(!b)return 12;
  if(fread(b,1,LW_HAL_IMAGE_SIZE,f)!=LW_HAL_IMAGE_SIZE)return 13;
  fclose(f);
  if(!LwHalImage(b))return 14;
  UINT32 pe=ReadUnaligned32((UINT32 *)(b+60));
  UINT32 fields[]={0,60,pe,pe+4,pe+8,pe+24,pe+24+56,0x5783c,0x57840,0x57850,0x283e59,0x283e69};
  for(unsigned i=0;i<sizeof(fields)/sizeof(fields[0]);i++) {
    UINT32 at=fields[i]; b[at]^=0x80;
    if(LwHalImage(b))return 20+i;
    b[at]^=0x80;
  }
  free(b);return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='lwlab-hal-match-') as directory:
    d = Path(directory)
    (d/'image.bin').write_bytes(mapped)
    (d/'test.c').write_text(source)
    subprocess.run(['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', str(d/'test.c'), '-o', str(d/'test')], check=True)
    subprocess.run([str(d/'test'), str(d/'image.bin')], check=True)
print(json.dumps(dict(real_image_match=True, corrupted_identity_or_code_rejections=12,
                      initial_no_shorthand=0, live_boot_required=True)))
