#!/usr/bin/env python3
"""Fetch the pinned Microsoft add-on payloads; no third-party Windows images."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess


def digest(path, algorithm):
    h = hashlib.new(algorithm)
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    lock = json.loads(Path(__file__).with_name('media-source.json').read_text())

    def fetch(item):
        path = args.destination / item['path']
        path.parent.mkdir(parents=True, exist_ok=True)
        def valid(p):
            return p.exists() and p.stat().st_size == item['size'] and digest(p, 'sha1') == item['sha1']
        if not valid(path):
            tmp = path.with_suffix(path.suffix + '.part')
            subprocess.run(['curl', '--fail', '--location', '--silent', '--show-error',
                            '--retry', '3', '--connect-timeout', '20', '--max-time', '1800',
                            '--output', str(tmp), item['url']], check=True)
            if not valid(tmp):
                raise ValueError(f'Microsoft manifest size/hash mismatch: {path.name}')
            tmp.replace(path)
        result = dict(item, sha256=digest(path, 'sha256'))
        print(f"verified {path.name}: {result['sha256']}", flush=True)
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(fetch, lock['files']))
    (args.destination / 'downloaded.json').write_text(json.dumps(
        dict(version=lock['version'], files=results), indent=2) + '\n')


if __name__ == '__main__':
    main()
