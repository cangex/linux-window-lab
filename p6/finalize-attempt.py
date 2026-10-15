#!/usr/bin/env python3
"""Cold extraction, acceptance checks and a lossless small disk archive.

Successful runs retain a byte-compared qcow2 snapshot plus immutable backing
chain, instead of another full RAW. Failed runs retain the RAW as well.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

p = argparse.ArgumentParser()
p.add_argument('name')
a = p.parse_args()
assert a.name.replace('-', '').replace('_', '').isalnum()
root = Path('/data/linux-window-lab')
out = root / 'artifacts/p6' / a.name
disk = root / 'state-p6/windows.qcow2'
assert out.is_dir()
assert subprocess.check_output(['sudo', '-n', 'virsh', 'domstate', 'lwlab-boot'], text=True).strip() == 'shut off'
snapshot = out / 'windows.qcow2'
assert not snapshot.exists()
shutil.copy2(disk, snapshot)
chain = json.loads(subprocess.check_output(['qemu-img', 'info', '--output=json', '--backing-chain', str(snapshot)], text=True))
assert len(chain) == 3
expected = [root / 'state-p6-activation/windows.qcow2', root / 'state-p5-install/windows.qcow2']
assert [Path(x['filename']).resolve() for x in chain[1:]] == expected
backing_hashes = dict(zip(map(str, expected), (
    'cf1b7bc98a2e92fc5cce089db7c5a4664fd72375bec06538ecf16f0ed4f4724a',
    '21dfa48d805d7f11b76f493b2ff0943ad727a25b8a0653edc33d22f9bbb5f2f9')))
for path, digest in backing_hashes.items():
    with open(path, 'rb') as file:
        assert hashlib.file_digest(file, 'sha256').hexdigest() == digest, 'immutable backing changed'
raw = out / 'windows.raw'
truth = out / 'p6-truth.jsonl'
with (out / 'extract.log').open('w') as log:
    subprocess.run(['sudo', '-n', 'python3', str(root / 'repo/p6/extract-offline.py'), str(snapshot), str(raw), str(truth)],
                   stdout=log, stderr=log, check=True, timeout=600)
with (out / 'archive-compare.log').open('w') as log:
    subprocess.run(['qemu-img', 'compare', '-f', 'qcow2', '-F', 'raw', str(snapshot), str(raw)],
                   stdout=log, stderr=log, check=True, timeout=600)
with snapshot.open('rb') as file:
    digest = hashlib.file_digest(file, 'sha256').hexdigest()
(out / 'disk-archive.json').write_text(json.dumps(dict(qcow2_sha256=digest, backing_chain=chain,
    guest_bytes_equal_to_raw=True, immutable_backing_sha256=backing_hashes), indent=2)+'\n')
with (out / 'attempt-verification.json').open('w') as log, (out / 'verification-error.log').open('w') as errors:
    result = subprocess.run(['python3', str(root / 'repo/p6/verify-attempt.py'), str(out)], stdout=log, stderr=errors, timeout=180)
if result.returncode == 0:
    # qemu-img compare checked logical disk bytes, including zero regions.
    # This removes only the redundant encoding; the snapshot is never reused.
    raw.unlink()
raise SystemExit(result.returncode)
