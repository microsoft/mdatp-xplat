import argparse
from argparse import RawTextHelpFormatter
from wdavhistory import Wdavhistory
import real_time_protection
import wdavhistory
import real_time_protection_json

parser = argparse.ArgumentParser(prog='LinuxMDEparser', description='Parser for MDE Linux logs. Please run it in the directory where the log file is located.', usage='%(prog)s [options]', formatter_class=RawTextHelpFormatter)
parser.add_argument('LogFile', help='Type the filename to convert. Available options:\n'
                                        '\n   real_time_protection - Troubleshoot performance issues\n'
                                        '   wdavhistory - Troubleshoot AV acvtivity. You can find this file in var\opt\microsoft\mdatp log folder\n'
                                        '   real_time_protection_json - Troubleshoot performance issues for Microsoft Defender (https://docs.microsoft.com/en-us/windows/security/threat-protection/microsoft-defender-atp/linux-support-perf)')
args = parser.parse_args()

if args.LogFile == 'real_time_protection':
    real_time_protection.RealTimeStatiscs.RealTimeStatiscs2Excel()

if args.LogFile == 'wdavhistory':
    wdavhistory.Wdavhistory.Wdavhistory2Excel()

if args.LogFile == 'real_time_protection.json':
    real_time_protection_json.RealTimeStatiscsJson.RealTimeStatiscsJson2Excel()

else:
    print('Not a valid log file. Please see -h for help')