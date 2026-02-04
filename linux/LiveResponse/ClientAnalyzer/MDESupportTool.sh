#!/bin/bash
set -euo pipefail

echo "cd /tmp/XMDEClientAnalyzerBinary/ClientAnalyzer"
cd /tmp/XMDEClientAnalyzerBinary/ClientAnalyzer

echo "Running MDESupportTool"
./MDESupportTool "$@"