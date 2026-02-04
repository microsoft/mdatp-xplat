#!/bin/bash
set -euo pipefail

echo "Starting Client Analyzer Script. Running As:"
whoami

echo "Getting XMDEClientAnalyzerBinary"
wget --quiet -O /tmp/XMDEClientAnalyzerBinary.zip https://go.microsoft.com/fwlink/?linkid=2297517
if [[ $? -ne 0 ]]; then
    echo 'ERROR: wget failed to retrieve XMDEClientAnalyzerBinary.zip exiting!'
    exit 1
fi
echo '9D0552DBBD1693D2E2ED55F36147019CFECFDC009E76BAC4186CF03CD691B469 /tmp/XMDEClientAnalyzerBinary.zip' | sha256sum -c


echo "Unzipping XMDEClientAnalyzerBinary.zip"
unzip -q /tmp/XMDEClientAnalyzerBinary.zip -d /tmp/XMDEClientAnalyzerBinary
if [[ $? -ne 0 ]]; then
    echo "ERROR: Failed to unzip the XMDEClientAnalyzerBinary.zip in /tmp to /tmp/XMDEClientAnalyzerBinary"
    exit 2
fi


echo "Unzipping SupportToolLinuxBinary.zip"
unzip -q /tmp/XMDEClientAnalyzerBinary/SupportToolLinuxBinary.zip -d /tmp/XMDEClientAnalyzerBinary/ClientAnalyzer
if [[ $? -ne 0 ]]; then
    echo "ERROR: Failed to unzip the SupportToolLinuxBinary.zip file in /tmp/XMDEClientAnalyzerBinary to /tmp/XMDEClientAnalyzerBinary/ClientAnalyzer"
    exit 3
fi
echo "MDESupportTool installed at /tmp/XMDEClientAnalyzerBinary/ClientAnalyzer"