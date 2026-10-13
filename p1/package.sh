#!/bin/sh
set -eu
SOURCE=${1:-/opt/lwlab/src/linux-p1}
BUILD=${2:-/opt/lwlab/build/p1}
OUTPUT=${3:-/opt/lwlab/build/p1-package}
[ ! -e "$OUTPUT" ] || { echo 'Output already exists' >&2; exit 1; }
mkdir -p "$OUTPUT"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
make -C "$SOURCE" O="$BUILD" INSTALL_MOD_PATH="$STAGE" modules_install
tar -czf "$OUTPUT/p1-modules.tar.gz" -C "$STAGE" lib
cp "$BUILD/arch/x86/boot/bzImage" "$BUILD/.config" "$BUILD/System.map" "$BUILD/ap-probe.bin" "$OUTPUT/"
(cd "$OUTPUT" && sha256sum bzImage .config System.map ap-probe.bin p1-modules.tar.gz > SHA256SUMS)
