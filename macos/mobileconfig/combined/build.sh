#!/bin/bash
set -euo pipefail

ROOTDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"
cd "$ROOTDIR"

echo "Building mdatp.mobileconfig..."
./build_combined.py --template template.mobileconfig --out mdatp.mobileconfig --in \
    ../profiles/accessibility.mobileconfig \
    ../profiles/background_services.mobileconfig \
    ../profiles/fulldisk.mobileconfig \
    ../profiles/netfilter.mobileconfig \
    ../profiles/notif.mobileconfig \
    ../profiles/sysext.mobileconfig
