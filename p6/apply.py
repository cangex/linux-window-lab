#!/usr/bin/env python3
"""P5 kernel plus explicit CPU/device quiescence; fixed Q35 only."""
import argparse,subprocess,shutil
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('stage',type=Path);a=p.parse_args();here=Path(__file__).resolve().parent
subprocess.run(['python3',str(here.parent/'p5/apply.py'),str(a.source),str(a.stage)],check=True)
binary=a.source/'kernel/lw-park.bin';subprocess.run(['nasm','-f','bin',str(here/'park.asm'),'-o',str(binary)],check=True)
data=binary.read_bytes();assert len(data)<4096
(a.source/'kernel/lw_park.h').write_text('static const unsigned char lw_park_code[]={'+','.join(hex(x) for x in data)+'};\n')
shutil.copyfile(here/'recovery.inc',a.source/'kernel/lw_recovery.inc')
f=a.source/'kernel/lwlab.c';s=f.read_text()
def change(old,new):
 global s
 assert s.count(old)==1,(old,s.count(old));s=s.replace(old,new)
change('#include "P5Platform.h"','#include "P5Platform.h"\n#include "lw_park.h"')
change('if (version != 3 || !generation || flags || !boot_cpu_has(X86_FEATURE_GBPAGES))',
 'if (version != 3 || generation <= lw_h->generation || flags || !boot_cpu_has(X86_FEATURE_GBPAGES))')
change('static int lw_prepare(const char *buf)','#include "lw_recovery.inc"\n\nstatic int lw_prepare(const char *buf)')
change('memset(lw_real, 0, LW_REAL_SIZE);','memset(lw_real, 0, LW_REAL_SIZE-4096);\n\tmemcpy(lw_real+LW_REAL_SIZE-4096,lw_park_code,sizeof(lw_park_code));')
change('cpu_hotplug_disable();','if (!lw_hotplug_held) { cpu_hotplug_disable(); lw_hotplug_held=true; }')
change('cpu_hotplug_enable();','cpu_hotplug_enable(); lw_hotplug_held=false;')
change('if (cpu_online(lw_cpu))\n\t\treturn -EBUSY;',
 'for (ret=4;ret<8;ret++)\n\t\tif (!cpu_possible(ret) || cpu_online(ret) || apic->cpu_present_to_apicid(ret)!=ret)\n\t\t\treturn -EBUSY;')
change('else if (!strncmp(buf, "prepare ", 8))','else if (sysfs_streq(buf,"stop"))\n\t\tret=lw_stop_partition();\n\telse if (!strncmp(buf, "prepare ", 8))')
f.write_text(s)
