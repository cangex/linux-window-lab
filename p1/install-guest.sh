#!/bin/sh
# Run as root in lwlab-boot only; artifacts copied into the supplied directory.
set -eu
[ "$(hostname)" = lwlab-boot ] || { echo 'Expected lwlab-boot' >&2; exit 1; }
INPUT=${1:-/tmp/p1-install}
RELEASE=6.18.0-rc3-lwlab-p1
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
tar -xzf "$INPUT/p1-modules.tar.gz" -C "$STAGE"
mkdir -p /lib/modules
cp -a "$STAGE/lib/modules/." /lib/modules/
install -m 644 "$INPUT/bzImage" "/boot/vmlinuz-$RELEASE"
install -m 644 "$INPUT/.config" "/boot/config-$RELEASE"
install -m 644 "$INPUT/System.map" "/boot/System.map-$RELEASE"
install -D -m 644 "$INPUT/ap-probe.bin" /lib/firmware/lwlab/ap-probe.bin
depmod "$RELEASE"
update-initramfs -c -k "$RELEASE"
cat > /etc/default/grub.d/99-lwlab.cfg <<'GRUB'
GRUB_DEFAULT=0
GRUB_TIMEOUT=3
GRUB_CMDLINE_LINUX_DEFAULT=""
GRUB_CMDLINE_LINUX="console=tty0 console=ttyS0,115200n8 nokaslr no5lvl zdu_pool=16M@0x180000000"
GRUB
update-grub
