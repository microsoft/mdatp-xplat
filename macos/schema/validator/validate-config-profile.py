#!/usr/bin/env python3
import argparse, shutil, subprocess, sys, tempfile
from jschon import create_catalog, JSON, JSONSchema

parser = argparse.ArgumentParser(description='Validate configuration profile against schema')
parser.add_argument('--schema', type=str, help='Path to the schema file')
parser.add_argument('--verbose', action='store_true', help='Include verbose output')
parser.add_argument('--print-valid', action='store_true', help='Include list of configuration values passed validation')
parser.add_argument('--print-invalid', action='store_true', help='Include list of configuration values failed validation')
parser.add_argument('--print-unsupported', action='store_true', help='Include list of configuration values out of schema scope')
parser.add_argument('file', type=str, nargs='+')

try:
    args = parser.parse_args()
except SystemExit:
    print(parser.print_help())
    sys.exit(2)

if not args.print_valid and not args.print_invalid and not args.print_unsupported:
    args.print_valid = True
    args.print_invalid = True
    args.print_unsupported = True

def debug(s: str):
    if args.verbose:
        print('[DEBUG] {}'.format(s))

def info(s: str):
    print('[INFO] {}'.format(s))

def warn(s: str):
    print('[WARN] {}'.format(s))

def load_json(path: str):
    debug("Probe JSON file: {}".format(path))
    payload = {
        'json': JSON.loadf(path),
        'name': ''
    }
    return [payload]

def load_plist(path: str):
    debug("Probe plist file: {}".format(path))
    import plistlib

    try:
        with open(path, 'rb') as f:
            debug("Probe as a plain plist")
            data = plistlib.load(f)
    except plistlib.InvalidFileException:
        debug("Probe as a signed mobileconfig file")
        temp_file = tempfile.NamedTemporaryFile()
        subprocess.run(["/usr/bin/security", "cms", "-D", "-i", path, "-o", temp_file.name])
        with open(temp_file.name, 'rb') as f:
            data = plistlib.load(f)

    debug("Plist loaded")

    result = []

    if 'PayloadContent' in data:
        debug("mobileconfig detected")
        for pc_outer in data['PayloadContent']:
            if 'PayloadContent' in pc_outer:
                for selector in ('com.microsoft.wdav', 'com.microsoft.wdav.ext'):
                    if selector in pc_outer['PayloadContent'] and 'Forced' in pc_outer['PayloadContent'][selector]:
                        id = 0

                        for pc_inner in pc_outer['PayloadContent'][selector]['Forced']:
                            id += 1
                            if 'mcx_preference_settings' in pc_inner:
                                payload = {
                                    'json': JSON(pc_inner['mcx_preference_settings']),
                                    'name': '{} ({}) / {} / {} #{}'.format(data['PayloadDisplayName'], data['PayloadIdentifier'], pc_outer['PayloadIdentifier'], selector, id)
                                }
                                result += [payload]
    else:
        debug("Simple plist detected")
        payload = {
            'json': JSON(data),
            'name': ''
        }
        result += [payload]

    debug("Found {} payloads".format(len(result)))
    return result

def load_file(path: str):
    try:
        return load_plist(path)
    except (plistlib.InvalidFileException, OSError):
        return load_json(path)
    
def report(node: dict, found_nodes: set, offset: int = 0):
    has_errors = 'errors' in node
    has_annotations = 'annotations' in node
    is_valid = 'valid' in node and node['valid']

    if node['instanceLocation']:
        found_nodes.add(node['instanceLocation'])
        if has_errors or has_annotations:
            if is_valid:
                if args.print_valid:
                    print('✅{}{}'.format('  ' * offset, node['keywordLocation']))
            else:
                if args.print_invalid:
                    if 'error' in node:
                        print('❌{}{}: {}'.format('  ' * offset, node['keywordLocation'], node['error']))
                    else:
                        print('❌{}{}'.format('  ' * offset, node['keywordLocation']))
        else:
            if not is_valid:
                if args.print_invalid:
                    if 'error' in node:
                        print('❌{}{}: {}'.format('  ' * offset, node['keywordLocation'], node['error']))

    if 'errors' in node:
        for n in node['errors']:
            report(n, found_nodes, offset + 1)
    if 'annotations' in node:
        for n in node['annotations']:
            report(n, found_nodes, offset + 1)

def found_data_nodes(node: dict, found_nodes: int, prefix: str = '/'):
    for k, v in node.data.items():
        found_nodes.add(prefix + k)
        if isinstance(v.data, dict):
            found_data_nodes(v, found_nodes, prefix + k + '/')
    
def analyze_json(schema: JSONSchema, payload: dict):
    result = schema.evaluate(payload['json'])
    output = result.output('verbose')
    success = output['valid']

    if output['valid']:
        info("JSON is valid{}".format(": " + payload['name'] if payload['name'] else ''))
    else:
        warn("JSON is invalid{}".format(": " + payload['name'] if payload['name'] else ''))

    found_expected_nodes = set()
    found_real_nodes = set()
    report(output, found_expected_nodes)

    found_data_nodes(payload['json'], found_real_nodes)

    unexpected_nodes = sorted(found_real_nodes.difference(found_expected_nodes))

    if len(unexpected_nodes) > 0:
        warn("Unexpected nodes found (either misspelled or not at the expected location):")
        success = False

        if args.print_unsupported:
            for node in unexpected_nodes:
                s = len(node.split('/'))
                print('❌{}{}'.format('  ' * s, node))

    return success

def analyze_file(schema: JSONSchema, path: str):
    payloads = load_file(path)
    success = True

    for payload in payloads:
        if not analyze_json(schema, payload):
            success = False

    return success

def download_schema():
    url = 'https://raw.githubusercontent.com/microsoft/mdatp-xplat/master/macos/schema/schema.json'
    global schema_temp_file, schema
    schema_temp_file = tempfile.NamedTemporaryFile()
    schema = schema_temp_file.name

    info("Downloading schema from {}".format(url))
    import urllib.request
    import urllib.error
    debug('Using module urllib.request')

    try:
        with urllib.request.urlopen(url) as response, open(schema, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
    except urllib.error.URLError as e:
        warn('Your Python has issues with SSL validation, please fix it. Querying {} with disabled validation. Error: {}'.format(url, e))
        import ssl
        ssl._create_default_https_context = ssl._create_unverified_context

        with urllib.request.urlopen(url) as response, open(schema, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
    debug("Downloaded schema to {}".format(schema))

schema_temp_file = None
schema = args.schema

try:
    if not schema:
        download_schema()

    create_catalog('2020-12')
    schema = JSONSchema.loadf(schema)
    success = True

    for path in args.file:
        info('Analyzing file: {}'.format(path))
        if not analyze_file(schema, path):
            success = False

    sys.exit(0 if success else 1)
except Exception as ex:
    import traceback
    print("".join(traceback.TracebackException.from_exception(ex).format()) == traceback.format_exc() == "".join(traceback.format_exception(type(ex), ex, ex.__traceback__)))
    print("".join(traceback.TracebackException.from_exception(ex).format()))
    sys.exit(3)
