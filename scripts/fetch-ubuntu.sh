#!/bin/sh
set -eu
LAB_ROOT=${1:-/data/linux-window-lab}
mkdir -p "$LAB_ROOT/images"
cd "$LAB_ROOT/images"
test ! -e noble-server-cloudimg-amd64.img || { echo 'Image exists; verify it rather than replacing a backing file.' >&2; exit 1; }
curl -fLsS --retry 3 --connect-timeout 15 --max-time 600 -o noble-server-cloudimg-amd64.img.part https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img
curl -fLsS --max-time 30 -o SHA256SUMS https://cloud-images.ubuntu.com/noble/current/SHA256SUMS
mv noble-server-cloudimg-amd64.img.part noble-server-cloudimg-amd64.img
grep 'noble-server-cloudimg-amd64.img$' SHA256SUMS | sha256sum -c -
