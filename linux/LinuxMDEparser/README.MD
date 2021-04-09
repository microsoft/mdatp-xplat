# LinuxMDEparser
Microsoft Defender Endpoint Log Parser for Linux.

# About
The LinuxMDEparser is a Windows tool that allows you to export or parse MDE for Linux log files to Excel, making it easier to filter and search the logs. After collecting the MDE logs from any Linux machine, you can then run this tool on your on Windows.

# Usage
LinuxMDEparser {Command} <option>

EX: LinuxMDEparser.exe real-time-protection --convert
    LinuxMDEparser.exe wdavhistory -h

Make sure you run it from the folder where the log file is located. Excel file will also be created in the same folder.

Files are included when you collect the Linux - "mdatp diagnostic create" command in Linux, except for real_time_protection.json - this ones need to be collected locally in a terminal window:

mdatp diagnostic real-time-protection-statistics --output json > real_time_protection.json

More details https://docs.microsoft.com/en-us/windows/security/threat-protection/microsoft-defender-atp/linux-support-perf

# Help
You can always check the available options by running: LinuxMDEparser -h

usage: LinuxMDEparser.exe [command] [--option]

optional arguments:
  -h, --help            show this help message and exit

Commands:
  {wdavhistory,real-time-protection}
                        Choose log filename to convert
    wdavhistory         File can be found on var\opt\microsoft\mdatp\wdavhistory from MDE logs folder
    real-time-protection
                        Troubleshoot performance issues for Microsoft Defender

# Dependecies
LinuxMDEparser will require you to install the following dependecies:

Argparse - https://pypi.org/project/argparse/ --> pip install argparse

# Compiling tool using pyinstaller
pip install pyinstaller

pyinstaller -F -n LinuxMDEparser

pyinstaller produces a standalone executable as dist/LinuxMDEparser.exe

For a compilied version of the latest release, please check "dist" folder or https://aka.ms/LinuxMDEparser

# To-Do
Allow for special caracters such as Chinese