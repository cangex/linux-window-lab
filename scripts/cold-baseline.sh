#!/bin/sh
# Run after a successful guest readiness check. Stops only lwlab-dev and restarts it.
set -eu
export LC_ALL=C
LAB_ROOT=${1:-/data/linux-window-lab}
BASELINE="$LAB_ROOT/baselines/pre-multikernel"
vm_state=$(sudo -n virsh -c qemu:///system domstate lwlab-dev)
test ! -e "$BASELINE" || { echo 'Baseline exists; refusing to replace it.' >&2; exit 1; }
case "$vm_state" in
  running) sudo -n virsh -c qemu:///system shutdown lwlab-dev ;;
  'shut off') ;;
  *) echo "Unexpected VM state: $vm_state" >&2; exit 1 ;;
esac
attempt=0
while test "$(sudo -n virsh -c qemu:///system domstate lwlab-dev)" != 'shut off'; do
  attempt=$((attempt + 1))
  test "$attempt" -le 45 || { echo 'Graceful shutdown timed out; no baseline copied.' >&2; exit 1; }
  sleep 1
done
mkdir -p "$BASELINE"
sudo -n virsh -c qemu:///system dumpxml lwlab-dev --inactive > "$BASELINE/domain.xml"
for filename in linux.qcow2 windows.qcow2 OVMF_VARS.fd; do
  sudo -n cp --reflink=auto --sparse=always "$LAB_ROOT/state/$filename" "$BASELINE/$filename"
done
sudo -n sha256sum "$BASELINE/linux.qcow2" "$BASELINE/windows.qcow2" "$BASELINE/OVMF_VARS.fd" > "$BASELINE/SHA256SUMS"
sudo -n virsh -c qemu:///system start lwlab-dev
printf 'Cold baseline saved in %s; verify SSH after restart.\n' "$BASELINE"
