"""Pinned experimental firmware variants; unknown modes/CPU counts fail closed."""
import json
from pathlib import Path


def firmware(root, cpus, mode='r5'):
    here = Path(__file__).parent
    if mode == 'r5':
        digest = json.loads((here / 'firmware-sha256.json').read_text())[str(cpus)]
        relative = 'p6-package-r5' if cpus == 4 else f'firmware-r5-cpu{cpus}'
    else:
        entry = json.loads((here / 'firmware-variants.json').read_text())[mode][str(cpus)]
        digest, relative = entry['sha256'], entry['directory']
        assert Path(relative).name == relative
    return Path(root) / 'artifacts/p6' / relative / 'partition.bin', digest
