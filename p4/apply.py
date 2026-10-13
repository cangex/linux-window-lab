#!/usr/bin/env python3
import argparse,shutil,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('stage',type=Path);a=p.parse_args()
here=Path(__file__).resolve().parent
subprocess.run([sys.executable,str(here.parent/'p3/apply.py'),str(a.source),str(a.stage)],check=True)
for name,src in [('lwobserve.inc',here/'kernel/lwobserve.inc'),('lwobserve.h',here/'lwobserve.h')]:
 shutil.copyfile(src,a.source/'kernel'/name)
f=a.source/'kernel/lwlab.c';s=f.read_text()
s=s.replace('static int __init lw_init(void)', '#include "lwobserve.inc"\n\nstatic int __init lw_init(void)')
s=s.replace('return sysfs_create_group(k, &lw_group);','if (sysfs_create_group(k, &lw_group)) return -ENOMEM;\n\treturn misc_register(&lwobs_device);')
f.write_text(s)
