#!/bin/sh
set -eu
SOURCE=${1:-/opt/lwlab/src/linux-p2-clean}
BUILD=${2:-/opt/lwlab/build/p2-kernel}
OUTPUT=${3:-/opt/lwlab/build/p2-package}
FIRMWARE=${4:-/opt/lwlab/build/p2-firmware}
[ ! -e "$OUTPUT" ] || { echo 'Output already exists' >&2; exit 1; }
mkdir -p "$OUTPUT"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
make -C "$SOURCE" O="$BUILD" INSTALL_MOD_PATH="$STAGE" modules_install
tar -czf "$OUTPUT/p2-modules.tar.gz" -C "$STAGE" lib
cp "$BUILD/arch/x86/boot/bzImage" "$BUILD/.config" "$BUILD/System.map" "$FIRMWARE/partition.bin" "$OUTPUT/"
(cd "$OUTPUT" && sha256sum bzImage .config System.map partition.bin p2-modules.tar.gz > SHA256SUMS)
