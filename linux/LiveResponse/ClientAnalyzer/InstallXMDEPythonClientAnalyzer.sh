#!/bin/bash
set -euo pipefail

wget --quiet -O /tmp/XMDEClientAnalyzer.zip https://aka.ms/XMDEClientAnalyzer
if [[ $? -ne 0 ]]; then
    echo 'ERROR: wget failed to retrieve XMDEClientAnalyzerBinary.zip exiting!'
    exit 1
fi
echo '36C2B13AE657456119F3DC2A898FD9D354499A33F65015670CE2CD8A937F3C66 /tmp/XMDEClientAnalyzer.zip' | sha256sum -c

unzip -q /tmp/XMDEClientAnalyzer.zip -d /tmp/XMDEClientAnalyzer
if [[ $? -ne 0 ]]; then
    echo "ERROR: Failed to unzip the XMDEClientAnalyzerBinary.zip in /tmp to /tmp/XMDEClientAnalyzerBinary"
    exit 2
fi

cd /tmp/XMDEClientAnalyzer
chmod a+x mde_support_tool.sh

echo 'Running final setup script /tmp/XMDEClientAnalyzer/mde_support_tool.sh'
./mde_support_tool.sh