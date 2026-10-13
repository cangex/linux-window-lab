#!/usr/bin/env python3
"""Apply the frozen P1 AP mechanism, then the P2 handoff/partition loader."""
import subprocess,sys,shutil
from pathlib import Path
here=Path(__file__).resolve().parent
root=Path(sys.argv[1]).resolve()
subprocess.run([sys.executable,str(here.parent/'p1/apply.py'),str(root)],check=True)
shutil.copyfile(here/'kernel/lwlab.c',root/'kernel/lwlab.c')
shutil.copyfile(here/'LwPartitionPkg/Include/Platform.h',root/'kernel/lw_platform.h')
for file in ['kernel/Makefile','kernel/zdu/Kconfig']:
 p=root/file;p.write_text(p.read_text().replace('LWLAB_P1','LWLAB_P2').replace('P1 AP probe','P2 partition UEFI'))
