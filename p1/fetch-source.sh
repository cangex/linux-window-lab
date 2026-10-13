#!/bin/sh
# Export a clean, frozen tree. Do not run against an existing working directory.
set -eu
DEST=${1:?usage: fetch-source.sh NEW_DESTINATION}
[ ! -e "$DEST" ] || { echo 'Destination must not exist' >&2; exit 1; }
TEMP=$(mktemp -d)
trap 'rm -rf "$TEMP"' EXIT
COMMIT=d75950ccbae6f5f651d4a9fd0701de1819c30579
git init -q "$TEMP/repo"
git -C "$TEMP/repo" remote add origin https://github.com/cangex/zero-down-time-kernel-update.git
git -C "$TEMP/repo" fetch --depth=1 origin "$COMMIT"
[ "$(git -C "$TEMP/repo" rev-parse FETCH_HEAD)" = "$COMMIT" ]
git -C "$TEMP/repo" archive --format=tar "$COMMIT" -o "$TEMP/source.tar"
mkdir -p "$DEST"
tar -xf "$TEMP/source.tar" -C "$DEST"
printf '%s\n' "$COMMIT" > "$DEST/.lwlab-source-commit"
