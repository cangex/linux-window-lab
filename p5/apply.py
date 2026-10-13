#!/usr/bin/env python3
"""Apply P4 plus P5's fixed high RAM and exclusively assigned NVMe mapping."""
import argparse,shutil,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('stage',type=Path);a=p.parse_args()
here=Path(__file__).resolve().parent
subprocess.run([sys.executable,str(here.parent/'p4/apply.py'),str(a.source),str(a.stage)],check=True)
shutil.copyfile(a.stage/'LwPartitionPkg/Include/P5Platform.h',a.source/'kernel/P5Platform.h')
f=a.source/'kernel/lwlab.c';s=f.read_text()
s=s.replace('#include "lw_platform.h"','#include "lw_platform.h"\n#include "P5Platform.h"\n#include <linux/pci.h>\n#include <asm/cpufeature.h>')
s=s.replace('static void *lw_real;','static void *lw_real;\nstatic void *lw_high;\nstatic struct resource lw_high_res;')
s=s.replace('if (version != 3 || !generation || flags)','if (version != 3 || !generation || flags || !boot_cpu_has(X86_FEATURE_GBPAGES))')
s=s.replace('\tmemset(lw_real, 0, LW_REAL_SIZE);','\tmemset(lw_real, 0, LW_REAL_SIZE);\n\tmemset(lw_high, 0, P5_HIGH_SIZE);')
s=s.replace('\tlw_transition("prepared");','''
 // High partition RAM uses WB 1 GiB leaves (checked CPU support above).
 for (i=10;i<16;i++) pdpt[i]=((u64)i<<30)|0x83;
 // Fixed ECAM and NVMe BAR use UC mappings; RAM stays WB.
pd[0xe8000000ULL>>21]|=0x18;
pd[P5_NVME_BAR>>21]|=0x18;
 lw_transition("prepared");''')
s=s.replace('\tif (!lw_low || !lw_real) {','\tlw_high = lw_claim_ram(P5_HIGH_BASE, P5_HIGH_SIZE, &lw_high_res);\n\tif (!lw_low || !lw_real || !lw_high) {')
# Binding must already be quiescent. We do not touch any other PCI endpoint.
s=s.replace('\tret = request_firmware(',''' {
  struct pci_dev *pdev=pci_get_domain_bus_and_slot(0,129,PCI_DEVFN(0,0));
  bool owned=pdev && pdev->vendor==0x1b36 && pdev->device==0x0010 &&
   pdev->driver && !strcmp(pdev->driver->name,"pci-stub") &&
   pci_resource_start(pdev,0)==P5_NVME_BAR && pci_resource_len(pdev,0)==P5_NVME_SIZE;
  if (pdev) pci_dev_put(pdev);
  if(!owned)return -ENODEV;
 }
 ret = request_firmware(''')
f.write_text(s)
u=a.source/'kernel/lwobserve.h';u.write_text(u.read_text().replace('extent[3]','extent[4]'))
f=a.source/'kernel/lwobserve.inc';s=f.read_text().replace('.version = 1, .count = 3','.version = 2, .count = 4').replace('{LW_REAL_BASE,LW_REAL_SIZE} }','{LW_REAL_BASE,LW_REAL_SIZE}, {P5_HIGH_BASE,P5_HIGH_SIZE} }').replace('maps[3] = {lw_h, lw_low, lw_real}','maps[4] = {lw_h, lw_low, lw_real, lw_high}').replace('i<3','i<4');f.write_text(s)
