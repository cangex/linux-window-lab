#!/bin/sh
set -eu
P2_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SOURCE=${1:-/opt/lwlab/src/linux-p2-clean}
BUILD=${2:-/opt/lwlab/build/p2-kernel}
mkdir -p "$BUILD"
cp "$P2_DIR/../p1/kernel.config" "$BUILD/.config"
"$SOURCE/scripts/config" --file "$BUILD/.config" -e EXPERT -d SERIAL_8250_PNP -d LWLAB_P1 -e LWLAB_P2 --set-str LOCALVERSION '-lwlab-p2'
make -C "$SOURCE" O="$BUILD" olddefconfig
cmp "$P2_DIR/kernel.config" "$BUILD/.config"
grep -q "# CONFIG_SERIAL_8250_PNP is not set" "$BUILD/.config"
make -C "$SOURCE" O="$BUILD" -j8 bzImage modules
