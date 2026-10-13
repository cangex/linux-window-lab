#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SOURCE=${1:?source tree with p3/apply.py applied}
BUILD=${2:?output directory}
mkdir -p "$BUILD"
cp "$HERE/../p2/kernel.config" "$BUILD/.config"
"$SOURCE/scripts/config" --file "$BUILD/.config" --set-str LOCALVERSION '-lwlab-p3'
make -C "$SOURCE" O="$BUILD" olddefconfig
make -C "$SOURCE" O="$BUILD" -j8 bzImage modules
