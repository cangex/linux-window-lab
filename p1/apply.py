#!/usr/bin/env python3
"""Apply the P1 overlay to the exact d75950c source archive (one time)."""
from pathlib import Path
import hashlib
import json
import shutil
import sys

root = Path(sys.argv[1]).resolve()
here = Path(__file__).resolve().parent
lock = json.loads((here / "sources.lock.json").read_text())
for name, expected in lock["linux"]["overlay_inputs_sha256"].items():
    actual = hashlib.sha256((root/name).read_bytes()).hexdigest()
    if actual != expected:
        raise SystemExit(f"Unexpected or already patched source: {name}")
if (root / "kernel/lwlab.c").exists():
    raise SystemExit("kernel/lwlab.c already exists")
path = root / "arch/x86/kernel/smpboot.c"
text = path.read_text()
if "int lwlab_kick_ap(" in text:
    raise SystemExit("P1 overlay already applied")
text = text.replace("extern unsigned long kernel_phys_addr;",
                    "extern unsigned long kernel_phys_addr;\nextern unsigned long boot_params_phys_addr;")
old = "static int do_zdu_boot_cpu(u32 apicid, int cpu,\n\t\t\t   unsigned long kernel_start_address)"
assert text.count(old) == 1
text = text.replace(old, old[:-1] + ", unsigned long handoff)")
old = "\t*kernel_virt_addr = kernel_start_address;"
assert text.count(old) == 1
text = text.replace(old, old + "\n\tif (handoff)\n\t\t*(unsigned long *)TRAMPOLINE_SYM_ZDU(&boot_params_phys_addr) = handoff;")
old = "do_zdu_boot_cpu(apicid, cpu, kernel_start_address);"
assert text.count(old) == 1
text = text.replace(old, "do_zdu_boot_cpu(apicid, cpu, kernel_start_address, 0);")
needle = "void __init setup_zdu_trampoline(void)"
assert text.count(needle) == 1
text = text.replace(needle, """/* P1 uses the existing AP trampoline, but supplies its own handoff ABI. */
int lwlab_kick_ap(unsigned int cpu, unsigned long entry, unsigned long handoff);
int lwlab_kick_ap(unsigned int cpu, unsigned long entry, unsigned long handoff)
{
	u32 apicid = apic->cpu_present_to_apicid(cpu);
	if (apicid == BAD_APICID || !apic_id_valid(apicid) ||
	    !test_bit(apicid, phys_cpu_present_map))
		return -EINVAL;
	mtrr_save_state();
	per_cpu(fpu_fpregs_owner_ctx, cpu) = NULL;
	return do_zdu_boot_cpu(apicid, cpu, entry, handoff);
}

""" + needle)
path.write_text(text)
shutil.copyfile(here / "kernel/lwlab.c", root / "kernel/lwlab.c")
with (root / "kernel/Makefile").open("a") as file:
    file.write("\nobj-$(CONFIG_LWLAB_P1) += lwlab.o\n")
with (root / "kernel/zdu/Kconfig").open("a") as file:
    file.write('\nconfig LWLAB_P1\n\tbool "Linux-Windows P1 AP probe"\n\tdepends on ZDU\n')
print("P1 overlay applied")
