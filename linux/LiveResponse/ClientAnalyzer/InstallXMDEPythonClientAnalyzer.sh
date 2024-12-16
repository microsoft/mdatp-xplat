#! /usr/bin/bash

wget --quiet -O XMDEClientAnalyzer.zip https://aka.ms/XMDEClientAnalyzer
echo '36C2B13AE657456119F3DC2A898FD9D354499A33F65015670CE2CD8A937F3C66 XMDEClientAnalyzer.zip' | sha256sum -c

unzip -q XMDEClientAnalyzer.zip -d /tmp/XMDEClientAnalyzer

cd /tmp/XMDEClientAnalyzer
chmod a+x mde_support_tool.sh

./mde_support_tool.sh