import sys
import argparse
import json2excel

# Menu
parser = argparse.ArgumentParser(prog='LinuxMDEparser.exe', usage='%(prog)s [command] [--option]')
subparsers = parser.add_subparsers(dest='Commands', title='Commands', help='Choose log filename to convert')
subparsers.required=True

# Log file options
wdavhistory = subparsers.add_parser('wdavhistory', help='Convert var\opt\microsoft\mdatp\wdavhistory')
wdavhistory.add_argument('--convert', dest='convert', help='Converts wdavhistory to wdavhistory.csv', action='store_true')

if len(sys.argv) <= 1:
    sys.argv.append('--help')

args = parser.parse_args()

# wdavhistory
if args.Commands == 'wdavhistory':
    if args.convert:
        convert_wdavhistory = json2excel.Json2excel('wdavhistory', 'scans', 'wdavhistory.csv')
        convert_wdavhistory.json2excel()
    else:
        parser.print_help(sys.stderr)