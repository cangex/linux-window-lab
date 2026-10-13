#!/usr/bin/env python3
"""Apply P1/P2's frozen AP mechanism and the ABI 3 loader to a fresh source tree."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys

p = argparse.ArgumentParser()
p.add_argument('source', type=Path)
p.add_argument('stage', type=Path)
a = p.parse_args()
here = Path(__file__).resolve().parent
subprocess.run([sys.executable, str(here.parent / 'p2/apply.py'), str(a.source)], check=True)
shutil.copyfile(here / 'kernel/lwlab.c', a.source / 'kernel/lwlab.c')
shutil.copyfile(a.stage / 'LwPartitionPkg/Include/Platform.h', a.source / 'kernel/lw_platform.h')
# Keep CONFIG_LWLAB_P2 as the inherited build switch; handoff ABI is version 3.
