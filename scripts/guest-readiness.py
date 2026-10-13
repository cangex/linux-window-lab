#!/usr/bin/env python3
"""Readiness evidence for the development guest, not multikernel acceptance."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def output(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()


tools = ["gcc", "make", "ld", "objcopy", "git", "bc", "bison", "flex", "cmake",
         "ninja", "nasm", "iasl", "acpidump", "dtc", "pahole", "python3", "mcopy", "mkfs.fat"]
report = {
    "scope": "Ubuntu UEFI development environment only",
    "kernel": output("uname", "-r"),
    "architecture": output("uname", "-m"),
    "uefi_boot": Path("/sys/firmware/efi").is_dir(),
    "online_cpus": output("cat", "/sys/devices/system/cpu/online"),
    "numa_nodes": output("cat", "/sys/devices/system/node/online"),
    "tools": {tool: shutil.which(tool) for tool in tools},
    "memory": output("free", "-m"),
    "disks": output("lsblk", "-o", "NAME,SIZE,TYPE,MOUNTPOINTS"),
    "cloud_init": output("cloud-init", "status", "--format", "json"),
    "guest_agent": output("systemctl", "is-active", "qemu-guest-agent"),
    "multikernel_validated": False, "windows_boot_validated": False,
}
with tempfile.TemporaryDirectory(prefix="lwlab-check-") as folder:
    directory = Path(folder)
    source = directory / "hello.c"
    source.write_text('#include <stdio.h>\nint main(void) { puts("LWLAB_BUILD_OK"); return 0; }\n')
    subprocess.run(["gcc", "-Wall", "-Wextra", "-Werror", str(source), "-o", str(directory / "hello")], check=True)
    report["compiler_smoke"] = output(str(directory / "hello")) == "LWLAB_BUILD_OK"
    data = b"LWLAB_STORAGE_CHECK\n" * 65536
    path = directory / "io-check"
    with path.open("wb") as file:
        file.write(data)
        file.flush()
        import os
        os.fsync(file.fileno())
    report["storage_readback"] = hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256(data).digest()
cloud = json.loads(report["cloud_init"])
report["ready"] = (report["uefi_boot"] and report["online_cpus"] == "0-7" and
                   report["numa_nodes"] == "0-1" and all(report["tools"].values()) and
                   report["compiler_smoke"] and report["storage_readback"] and
                   report["guest_agent"] == "active" and cloud.get("status") == "done")
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["ready"] else 1)
