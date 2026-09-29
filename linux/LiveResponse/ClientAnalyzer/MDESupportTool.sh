#!/bin/sh
set -eu

PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH

script_directory=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
helper="$script_directory/client_analyzer_binary_handoff.sh"
helper_sha256=56540d40160df0256b5295837e13c2280c34692dfff1c00484f81322faa3bffb
workspace=

cleanup() {
    rm -f "${workspace:-}/helper"
    rmdir "${workspace:-}" 2>/dev/null || :
}

trap cleanup EXIT
trap 'cleanup; exit 1' HUP INT TERM
workspace=$(mktemp -d /var/tmp/mde-client-analyzer-wrapper-XXXXXXXX)
helper_copy="$workspace/helper"
if [ "$(stat -c '%F:%u:%a:%h' "$workspace")" != "directory:$(id -u):700:2" ]; then
    echo "ERROR: Client Analyzer verification workspace is not private." >&2
    exit 1
fi
cat "$helper" > "$helper_copy"
chmod 700 "$helper_copy"

if [ "$(stat -c '%F:%u:%a:%h' "$helper_copy")" != "regular file:$(id -u):700:1" ]; then
    echo "ERROR: Client Analyzer helper copy is not private." >&2
    exit 1
fi

if [ "$(sha256sum "$helper_copy" | awk '{print $1}')" != "$helper_sha256" ]; then
    echo "ERROR: Client Analyzer package integrity verification failed." >&2
    exit 1
fi

"$helper_copy" run "$@"
