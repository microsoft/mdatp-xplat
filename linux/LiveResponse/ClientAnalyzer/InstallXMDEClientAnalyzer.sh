#!/bin/sh
set -eu

PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH

script_directory=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
helper="$script_directory/client_analyzer_handoff.py"

if [ ! -f "$helper" ] || [ -L "$helper" ]; then
    echo "ERROR: Client Analyzer package is incomplete." >&2
    exit 1
fi

exec python3 "$helper" install-binary "$@"
