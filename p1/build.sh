#!/bin/sh
set -eu
P1_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SOURCE=${1:-/opt/lwlab/src/linux-p1}
BUILD=${2:-/opt/lwlab/build/p1}
mkdir -p "$BUILD"
make -C "$SOURCE" O="$BUILD" x86_64_defconfig
CFG="$SOURCE/scripts/config"
"$CFG" --file "$BUILD/.config" \
  -e KEXEC -e KEXEC_FILE -e KEXEC_HANDOVER -e ZDU -e LWLAB_P1 \
  -e EFI -e EFI_STUB -e EFI_MIXED -e ACPI -e SMP -e HOTPLUG_CPU \
  -e VIRTIO_PCI -e VIRTIO_BLK -e VIRTIO_NET -e VIRTIO_CONSOLE -e HW_RANDOM_VIRTIO \
  -e EXT4_FS -e DEVTMPFS -e DEVTMPFS_MOUNT -e BLK_DEV_INITRD \
  -e SERIAL_8250 -e SERIAL_8250_CONSOLE -e CONFIGFS_FS \
  -d DEBUG_INFO -d DEBUG_INFO_DWARF_TOOLCHAIN_DEFAULT -e DEBUG_INFO_NONE \
  -d SYSTEM_TRUSTED_KEYRING -d SYSTEM_REVOCATION_LIST -d MODULE_SIG \
  -d LOCALVERSION_AUTO --set-str LOCALVERSION '-lwlab-p1'
make -C "$SOURCE" O="$BUILD" olddefconfig
cmp "$P1_DIR/kernel.config" "$BUILD/.config"
grep -q '^CONFIG_LWLAB_P1=y$' "$BUILD/.config"
make -C "$SOURCE" O="$BUILD" -j8 bzImage modules
nasm -f bin "$P1_DIR/payload/ap-probe.asm" -o "$BUILD/ap-probe.bin"
sha256sum "$BUILD/arch/x86/boot/bzImage" "$BUILD/.config" "$BUILD/ap-probe.bin" > "$BUILD/SHA256SUMS"
