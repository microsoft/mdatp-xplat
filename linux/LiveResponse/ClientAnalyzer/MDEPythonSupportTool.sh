#!/bin/sh
set -eu

PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH

script_directory=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
helper="$script_directory/client_analyzer_handoff.py"
helper_sha256=58b3030bc06e487f938f77b015a18f642a1e55de6fca5a6eae7892f043cb02fb
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

python3 "$helper_copy" run-python "$@"
