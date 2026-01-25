#!/usr/bin/env python3

from __future__ import print_function
import getopt, os, sys, plistlib, re, shutil, sys, argparse, uuid

if sys.stdout.isatty():
    class tc:
        green = '\033[92m'
        yellow = '\033[93m'
        red = '\033[91m'
        grey = '\033[2m'
        cancel = '\033[0m'

else:
    class tc:
        green = ''
        yellow = ''
        red = ''
        grey = ''
        cancel = ''

def print_warning(s):
    print('{}[WARNING]{} {}'.format(tc.yellow, tc.cancel, s))

def print_success(s):
    print('{}[OK]{} {}'.format(tc.green, tc.cancel, s))

def print_error(s):
    print('{}[ERROR]{} {}'.format(tc.red, tc.cancel, s))

def print_debug(s):
    print('{}{}{}'.format(tc.grey, s, tc.cancel))

def read_plist(path):
    print_debug('Reading {}'.format(path))

    if 'load' in plistlib.__all__:
        with open(path, 'rb') as f:
            return plistlib.load(f)
    else:
        return plistlib.readPlist(path)

def write_plist(path, plist):
    print_debug("Saving {}...".format(path))

    if 'dumps' in plistlib.__all__:
        s = plistlib.dumps(plist).decode('UTF-8')
    else:
        s = plistlib.writePlistToString(plist)

    output_file = os.path.abspath(os.path.expanduser(path))
    header_prefix1 = '<?xml'
    header_prefix2 = '<!DOCTYPE'
    re_indent = re.compile('[ \t]+<')
    re_replace = '<'
    output_type = 'w'
    if type(s) is bytes:
        output_type = 'wb'
        header_prefix1 = header_prefix1.encode()
        header_prefix2 = header_prefix2.encode()
        re_indent = re.compile(b'[ \t]+<')
        re_replace = b'<'

    with open(output_file, output_type) as f:
        for ss in s.splitlines():
            ss = re_indent.sub(re_replace, ss)
            f.write(ss)
            if ss.startswith(header_prefix1) or ss.startswith(header_prefix2):
                f.write('\n')

parser = argparse.ArgumentParser(description = "Merge individual MDM profiles into a single combined profile")
parser.add_argument("--in", type=str, nargs="+", help = "Individual .mobileconfig profiles to read")
parser.add_argument("--template", type=str, help = "Template to use for output")
parser.add_argument("--out", type=str, help = "Optional, writes combined profile to this .mobileconfig")
args = parser.parse_args()

try:
    plist_template = read_plist(args.template)
except (OSError, plistlib.InvalidFileException) as e:
    print_error("Cannot read template {}: {}".format(args.template, e))
    sys.exit(1)

plist_template['PayloadContent'] = []
plist_template['PayloadIdentifier'] = plist_template['PayloadUUID'] = str(uuid.uuid1()).upper()

tcc_payload = None
for f_in in getattr(args, 'in'):
    try:
        plist = read_plist(f_in)
        for payload in plist['PayloadContent']:

            # JAMF doesn't like having multiple TCC configuration profiles, so combine into a single one
            if payload['PayloadType'] == "com.apple.TCC.configuration-profile-policy":
                if tcc_payload is None:
                    tcc_payload = payload
                else:
                    # Merge the new TCC profile with the existing one.
                    tcc_payload['Services'].update(payload['Services'])
                # Don't append TCC until all profiles have been examined
                continue

            plist_template['PayloadContent'].append(payload)
    except (OSError, plistlib.InvalidFileException, KeyError) as e:
        print_error("Cannot read input file {}: {}".format(f_in, e))

if tcc_payload is not None:
    plist_template['PayloadContent'].append(tcc_payload)

out_file = getattr(args, 'out')

if out_file:
    write_plist(out_file, plist_template)
else:
    print_debug(plist_template)