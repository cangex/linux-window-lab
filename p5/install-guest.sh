#!/bin/sh
# Run as root in lwlab-boot only; artifacts copied into the supplied directory.
set -eu
[ "$(hostname)" = lwlab-boot ] || { echo 'Expected lwlab-boot' >&2; exit 1; }
INPUT=${1:-/tmp/p3-install}
RELEASE=6.18.0-rc3-lwlab-p5
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
tar -xzf "$INPUT/p3-modules.tar.gz" -C "$STAGE"
mkdir -p /lib/modules
cp -a "$STAGE/lib/modules/." /lib/modules/
install -m 644 "$INPUT/bzImage" "/boot/vmlinuz-$RELEASE"
install -m 644 "$INPUT/.config" "/boot/config-$RELEASE"
install -m 644 "$INPUT/System.map" "/boot/System.map-$RELEASE"
install -D -m 644 "$INPUT/partition.bin" /lib/firmware/lwlab/partition-p3.bin
depmod "$RELEASE"
update-initramfs -c -k "$RELEASE"
cat > /etc/default/grub.d/99-lwlab.cfg <<'GRUB'
GRUB_DEFAULT=0
GRUB_TIMEOUT=3
GRUB_CMDLINE_LINUX_DEFAULT=""
GRUB_CMDLINE_LINUX='console=tty0 console=ttyS0,115200n8 nokaslr no5lvl zdu_pool=1536M@0x10000000 memmap=6G\$10G pci-stub.ids=1b36:0010 memmap=15M\$1M memmap=128K\$0x50000 noapic hpet=disable 8250.nr_uarts=1 no_ipi_broadcast=1'
GRUB
update-grub
