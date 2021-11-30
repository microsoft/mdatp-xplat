#!/bin/bash

ROOTDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"
cd $ROOTDIR

echo "Building mdatp.mobileconfig..."
./build_combined.py --template template.mobileconfig --out mdatp.mobileconfig --in ../profiles/kext.mobileconfig ../profiles/notif.mobileconfig ../profiles/fulldisk.mobileconfig ../profiles/sysext.mobileconfig ../profiles/netfilter.mobileconfig ../profiles/accessibility.mobileconfig

echo "Building mdatp-nokext.mobileconfig..."
./build_combined.py --template template.mobileconfig --out mdatp-nokext.mobileconfig --in ../profiles/notif.mobileconfig ../profiles/fulldisk.mobileconfig ../profiles/sysext.mobileconfig ../profiles/netfilter.mobileconfig ../profiles/accessibility.mobileconfig
