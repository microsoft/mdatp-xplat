# MDE Auditd Exclusions Analyzer
Microsoft Defender Endpoint for Linux tool to troubleshoot Auditd performance issues

# About
This tool will help troubleshoot Auditd issues by presenting the most noisy processes running. The top processes should be consider for the auditd exclusions.

## Sample Usage
Full path for audit files (default path in Linux /var/log/audit.log): /var/log/audit/audit.log.1
                                            
                                            Process  Count
                               
                               "/usr/bin/python3.6"   6771
                    
                    "/lib/systemd/systemd-resolved"    998
                               
                               "/usr/bin/python2.7"    406
            
            "/opt/microsoft/omsagent/ruby/bin/ruby"    249

# Usage
This tool was developed for Python3

Clone the repository

pip install -r requirements.txt

python MDEAuditAnalyzer.py

# Dependencies
Dependencies can be found in requirements.txt

Manual install:

`
    pip install pandas
`
