### [analyze_profiles.py - Verifies MDM profiles on a client machine](analyze_profiles.py)

Helps diagnosing issues with configuration profiles for Defender deployed with MDM. 
To use, download the script and run it without parameters, it will ask to sudo, and output all *potential* issues with profiles.

To collect diagnostics on one machine, and analyze on another machine, collect two files:
- `/Library/Application Support/com.apple.TCC/MDMOverrides.plist`
- Run `sudo profiles show -output ~/Documents/profiles.xml` 
