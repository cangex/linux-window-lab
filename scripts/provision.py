#!/usr/bin/env python3
"""Create one fresh Ubuntu/OVMF lab VM. Existing domain/state is never overwritten."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from xml.sax.saxutils import escape


def run(*args, capture=False):
    return subprocess.run(args, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def virsh(*args, capture=False):
    return run("sudo", "-n", "virsh", "-c", "qemu:///system", *args, capture=capture)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/data/linux-window-lab"))
    args = parser.parse_args()
    root = args.root.resolve()
    name, network = "lwlab-dev", "lwlab-net"
    if name in virsh("list", "--all", "--name", capture=True).splitlines():
        raise SystemExit("lwlab-dev already exists; refusing to replace it")
    if network in virsh("net-list", "--all", "--name", capture=True).splitlines():
        raise SystemExit("lwlab-net already exists; inspect partial setup before continuing")
    image = root / "images/noble-server-cloudimg-amd64.img"
    sums = (root / "images/SHA256SUMS").read_text().splitlines()
    expected = [s.split()[0] for s in sums if s.split()[-1].lstrip("*") == image.name]
    actual = hashlib.file_digest(image.open("rb"), "sha256").hexdigest()
    if expected != [actual]:
        raise SystemExit("Ubuntu cloud image checksum mismatch")
    if (root / "state").exists():
        raise SystemExit("state directory already exists; refusing to overwrite VM data")
    routes = json.loads(run("ip", "-j", "route", capture=True))
    import ipaddress
    subnet = ipaddress.ip_network("192.168.231.0/24")
    for route in routes:
        dst = route.get("dst", "default")
        if dst != "default" and ipaddress.ip_network(dst, strict=False).overlaps(subnet):
            raise SystemExit("192.168.231.0/24 overlaps a host route")
    for folder in ("state", "config", "artifacts", "keys"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    (root / "keys").chmod(0o700)
    key = root / "keys/guest_ed25519"
    if not key.exists():
        run("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "lwlab-guest", "-f", str(key))
    public = key.with_suffix(".pub").read_text().strip()
    userdata = f"""#cloud-config
hostname: lwlab-dev
manage_etc_hosts: true
users:
  - name: lab
    groups: [adm, sudo]
    shell: /bin/bash
    sudo: ALL=(ALL) NOPASSWD:ALL
    lock_passwd: true
    ssh_authorized_keys:
      - {public}
ssh_pwauth: false
disable_root: true
package_update: true
package_upgrade: false
packages:
  - build-essential
  - git
  - bc
  - bison
  - flex
  - libssl-dev
  - libelf-dev
  - dwarves
  - pkg-config
  - cmake
  - ninja-build
  - nasm
  - uuid-dev
  - acpica-tools
  - device-tree-compiler
  - python3-venv
  - mtools
  - dosfstools
  - pciutils
  - numactl
  - qemu-guest-agent
write_files:
  - path: /etc/default/grub.d/99-lwlab.cfg
    content: |
      GRUB_CMDLINE_LINUX_DEFAULT="console=tty0 console=ttyS0,115200n8"
runcmd:
  - [update-grub]
  - [systemctl, enable, --now, qemu-guest-agent]
  - [mkdir, -p, /opt/lwlab/src, /opt/lwlab/build, /opt/lwlab/results]
  - [chown, -R, 'lab:lab', /opt/lwlab]
final_message: "LWLAB cloud-init complete after $UPTIME seconds"
"""
    (root / "config/user-data").write_text(userdata)
    (root / "config/meta-data").write_text("instance-id: lwlab-dev-001\nlocal-hostname: lwlab-dev\n")
    run("cloud-localds", str(root / "state/seed.iso"), str(root / "config/user-data"), str(root / "config/meta-data"))
    run("qemu-img", "create", "-f", "qcow2", "-F", "qcow2", "-b", str(image), str(root / "state/linux.qcow2"), "80G")
    # Staging disk is deliberately not attached until the partition device policy exists.
    run("qemu-img", "create", "-f", "qcow2", str(root / "state/windows.qcow2"), "64G")
    shutil.copyfile("/usr/share/OVMF/OVMF_VARS_4M.fd", root / "state/OVMF_VARS.fd")
    network_xml = """<network>
  <name>lwlab-net</name><forward mode='nat'/>
  <bridge name='virbr-lwlab' stp='on' delay='0'/>
  <ip address='192.168.231.1' netmask='255.255.255.0'><dhcp>
    <range start='192.168.231.100' end='192.168.231.150'/>
    <host mac='52:54:00:4c:57:10' name='lwlab-dev' ip='192.168.231.10'/>
  </dhcp></ip>
</network>
"""
    (root / "config/network.xml").write_text(network_xml)
    r = escape(str(root), {"'": "&apos;"})
    domain = f"""<domain type='kvm'>
  <name>{name}</name>
  <memory unit='MiB'>16384</memory><currentMemory unit='MiB'>16384</currentMemory>
  <vcpu placement='static'>8</vcpu>
  <os><type arch='x86_64' machine='pc-q35-8.2'>hvm</type>
    <loader readonly='yes' secure='no' type='pflash'>/usr/share/OVMF/OVMF_CODE_4M.fd</loader>
    <nvram>{r}/state/OVMF_VARS.fd</nvram><boot dev='hd'/>
  </os>
  <features><acpi/><apic/></features>
  <cpu mode='host-passthrough' check='none' migratable='off'>
    <topology sockets='1' dies='1' cores='8' threads='1'/>
    <numa><cell id='0' cpus='0-3' memory='8192' unit='MiB'/>
          <cell id='1' cpus='4-7' memory='8192' unit='MiB'/></numa>
  </cpu>
  <clock offset='utc'><timer name='hpet' present='no'/></clock>
  <on_poweroff>destroy</on_poweroff><on_reboot>restart</on_reboot><on_crash>preserve</on_crash>
  <pm><suspend-to-mem enabled='no'/><suspend-to-disk enabled='no'/></pm>
  <devices>
    <emulator>/usr/bin/qemu-system-x86_64</emulator>
    <disk type='file' device='disk'><driver name='qemu' type='qcow2'/>
      <source file='{r}/state/linux.qcow2'/><target dev='vda' bus='virtio'/></disk>
    <disk type='file' device='cdrom'><driver name='qemu' type='raw'/>
      <source file='{r}/state/seed.iso'/><target dev='sda' bus='sata'/><readonly/></disk>
    <interface type='network'><mac address='52:54:00:4c:57:10'/>
      <source network='{network}'/><model type='virtio'/></interface>
    <serial type='pty'><target type='isa-serial' port='0'/>
      <log file='{r}/artifacts/serial0.log' append='on'/></serial>
    <serial type='pty'><target type='isa-serial' port='1'/>
      <log file='{r}/artifacts/serial1.log' append='on'/></serial>
    <console type='pty'><target type='serial' port='0'/></console>
    <channel type='unix'><target type='virtio' name='org.qemu.guest_agent.0'/></channel>
    <graphics type='vnc' port='-1' autoport='yes' listen='127.0.0.1'/>
    <video><model type='vga'/></video>
    <memballoon model='none'/>
    <rng model='virtio'><backend model='random'>/dev/urandom</backend></rng>
  </devices>
</domain>
"""
    (root / "config/domain.xml").write_text(domain)
    run("sudo", "-n", "chown", "-R", "libvirt-qemu:kvm", str(root / "state"))
    # Logs use libvirt's logging daemon; parent must be traversable.
    virsh("net-define", str(root / "config/network.xml"))
    virsh("net-start", network)
    virsh("net-autostart", network)
    virsh("define", str(root / "config/domain.xml"))
    virsh("start", name)
    (root / "artifacts/provision.json").write_text(json.dumps({
        "domain": name, "network": network, "guest_ip": "192.168.231.10",
        "cloud_image_sha256": actual, "vcpus": 8, "memory_mib": 16384,
        "windows_disk_attached": False, "multikernel_boot_validated": False,
        "windows_boot_validated": False}, indent=2) + "\n")
    print("VM started. Wait for cloud-init before checking readiness.")


if __name__ == "__main__":
    main()
