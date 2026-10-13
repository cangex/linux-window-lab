#!/bin/sh
set -eu
DEST=${1:-/opt/lwlab/src/edk2-p2}
[ ! -e "$DEST" ] || { echo 'Destination exists' >&2; exit 1; }
git clone --depth 1 --branch edk2-stable202508 https://github.com/tianocore/edk2.git "$DEST"
[ "$(git -C "$DEST" rev-parse HEAD)" = d46aa46c8361194521391aa581593e556c707c6e ]
git -C "$DEST" submodule update --init --depth 1 MdePkg/Library/MipiSysTLib/mipisyst MdeModulePkg/Library/BrotliCustomDecompressLib/brotli
