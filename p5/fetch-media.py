#!/usr/bin/env python3
"""Pinned official Microsoft evaluation ISO; bounded parallel range download."""
import argparse,concurrent.futures,hashlib,json,re,shutil,subprocess
from pathlib import Path
URL='https://software-static.download.prss.microsoft.com/dbazure/888969d5-f34g-4e03-ac9d-1f9786c66749/26100.1742.240906-0331.ge_release_svc_refresh_CLIENT_LTSC_EVAL_x64FRE_en-us.iso'
SIZE=5112850432
SHA256='67cec5865eaa037a72ddc633a717a10a2bed50778862267223ddb9c60ef5da68'
ETAG='"0x08F8F2035AD0DA31990F760514171E541CC1105B35B9241BAAB204C39FBC3F71"'
p=argparse.ArgumentParser();p.add_argument('destination',type=Path);a=p.parse_args()
a.destination.mkdir(parents=True,exist_ok=True)
chunks=a.destination/'chunks';chunks.mkdir(exist_ok=True)
def fetch(i):
 lo=i*(64<<20);hi=min(lo+(64<<20),SIZE)-1
 path=chunks/f'{i:03d}';headers=path.with_suffix('.headers')
 if not path.exists() or path.stat().st_size!=hi-lo+1:
  part=path.with_suffix('.part')
  subprocess.run(['curl','-sSfL','--retry','4','--connect-timeout','20','--max-time','1800',
   '-H','If-Match: '+ETAG,'-r',f'{lo}-{hi}','-D',str(headers),URL,'-o',str(part)],check=True)
  text=headers.read_text().lower()
  assert f'content-range: bytes {lo}-{hi}/{SIZE}' in text
  assert ETAG.lower() in text and part.stat().st_size==hi-lo+1
  part.replace(path)
 print(f'chunk {i} verified ({hi-lo+1} bytes)',flush=True)
 return path
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
 paths=list(pool.map(fetch,range((SIZE+(64<<20)-1)//(64<<20))))
output=a.destination/'windows11-ltsc-eval.iso'
assert not output.exists()
with output.open('xb') as dst:
 for src in paths:
  with src.open('rb') as f:shutil.copyfileobj(f,dst)
with output.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
assert digest==SHA256,'ISO differs from the experimentally frozen input'
(a.destination/'source.json').write_text(json.dumps(dict(url=URL,source_page='https://www.microsoft.com/en-us/evalcenter/download-windows-11-enterprise',edition='Windows 11 Enterprise LTSC 2024 Evaluation x64 en-US',media_build='26100.1742',bytes=SIZE,etag=ETAG,sha256=digest,verification='HTTPS official URL, checked Content-Range and ETag per chunk; locally recorded full SHA256'),indent=2)+'\n')
print('ISO complete SHA256 '+digest,flush=True)
