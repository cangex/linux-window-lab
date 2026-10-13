#!/bin/bash
set -eu
P2_DIR=$(cd -- "$(dirname -- "$0")" && pwd)
SOURCE=${1:-/opt/lwlab/src/edk2-p2}
OUTPUT=${2:-/opt/lwlab/build/p2-firmware}
mkdir -p "$SOURCE/LwPartitionPkg"
cp -a "$P2_DIR/LwPartitionPkg/." "$SOURCE/LwPartitionPkg/"
cd "$SOURCE"
make -C BaseTools/Source/C -j8 APPLICATIONS='VfrCompile EfiRom GenFfs GenFv GenFw GenSec GenCrc32 LzmaCompress TianoCompress VolInfo DevicePath'
export WORKSPACE="$SOURCE"
set +u
source edksetup.sh
set -u
build -a X64 -t GCC5 -b DEBUG -p LwPartitionPkg/LwPartitionPkg.dsc -n 8
python3 "$P2_DIR/pack.py" "$SOURCE/Build/LwPartition/DEBUG_GCC5" "$OUTPUT"
python3 "$P2_DIR/verify-layout.py" "$OUTPUT"
