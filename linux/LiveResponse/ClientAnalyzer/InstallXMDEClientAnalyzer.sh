#! /usr/bin/bash
echo "Starting Client Analyzer Script. Running As:"
whoami

echo "Getting XMDEClientAnalyzerBinary"
wget --quiet -O /tmp/XMDEClientAnalyzerBinary.zip https://go.microsoft.com/fwlink/?linkid=2297517
echo '9D0552DBBD1693D2E2ED55F36147019CFECFDC009E76BAC4186CF03CD691B469 /tmp/XMDEClientAnalyzerBinary.zip' | sha256sum -c

echo "Unzipping XMDEClientAnalyzerBinary.zip"
unzip -q /tmp/XMDEClientAnalyzerBinary.zip -d /tmp/XMDEClientAnalyzerBinary

echo "Unzipping SupportToolLinuxBinary.zip"
unzip -q /tmp/XMDEClientAnalyzerBinary/SupportToolLinuxBinary.zip -d /tmp/XMDEClientAnalyzerBinary/ClientAnalyzer

echo "MDESupportTool installed at /tmp/XMDEClientAnalyzerBinary/ClientAnalyzer"
