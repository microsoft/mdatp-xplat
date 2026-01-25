#!/usr/bin/env python3
"""Analyze MDM profiles for Microsoft Defender for Endpoint on macOS.

This script validates that the required MDM profiles are properly
deployed and configured for Defender on macOS systems.
"""

from __future__ import annotations

import argparse
import logging
import os
import plistlib
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

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

class Payload():
    def __init__(self, payload_type, payload):
        self.payload_type = payload_type
        self.payload = payload

    def get_ids(self):
        assert('Not implemented')

    def get_all_ids(self):
        return (self.payload_type,) + self.get_ids()

    def __hash__(self):
        return hash(self.get_all_ids())

    def __eq__(self, other):
        return self.get_all_ids() == other.get_all_ids()

    def __ne__(self, other):
        return not(self == other)

    def __repr__(self):
        return self.__str__()

class PayloadTCC(Payload):
    def __init__(self, payload_type, service_type, payload):
        Payload.__init__(self, payload_type, payload)
        self.service_type = service_type
        self.identifier = payload['Identifier']

    def get_ids(self):
        return (self.identifier, self.service_type)

    def __str__(self):
        return '{}/{} ({})'.format(self.payload_type, self.service_type, self.identifier)

class PayloadKEXT(Payload):
    def __init__(self, payload_type, id):
        Payload.__init__(self, payload_type, None)
        self.id = id

    def get_ids(self):
        return (self.id,)

    def __str__(self):
        return '{} ({})'.format(self.payload_type, self.id)

class PayloadSysExt(Payload):
    def __init__(self, payload_type, team_id, bundle_id):
        Payload.__init__(self, payload_type, None)
        self.team_id = team_id
        self.bunle_id = bundle_id

    def get_ids(self):
        return (self.team_id, self.bunle_id)

    def __str__(self):
        return '{} ({}, {})'.format(self.payload_type, self.team_id, self.bunle_id)

class PayloadWebContentFilter(Payload):
    def __init__(self, payload_type, payload):
        Payload.__init__(self, payload_type, payload)
        self.id = payload['FilterDataProviderBundleIdentifier']
        self.properties = {}

        for p in ('FilterDataProviderDesignatedRequirement', 'FilterGrade', 'FilterSockets', 'FilterType', 'PluginBundleID'):
            self.properties[p] = payload[p]

    def get_ids(self):
        return (self.id,)

    def __str__(self):
        return '{} ({})'.format(self.payload_type, self.id)

class PayloadNotifications(Payload):
    def __init__(self, payload_type, payload):
        Payload.__init__(self, payload_type, payload)
        self.id = payload['BundleIdentifier']

    def get_ids(self):
        return (self.id,)

    def __str__(self):
        return '{} ({})'.format(self.payload_type, self.id)
    
class PayloadServiceManagement(Payload):
    def __init__(self, payload_type, payload):
        Payload.__init__(self, payload_type, payload)
        self.id = '{}={}'.format(payload['RuleType'], payload['RuleValue'])

    def get_ids(self):
        return (self.id,)

    def __str__(self):
        return '{} ({})'.format(self.payload_type, self.id)

class PayloadOnboardingInfo(Payload):
    def __init__(self, payload_type, payload):
        Payload.__init__(self, payload_type, payload)

    def get_ids(self):
        return ()

    def __str__(self):
        return '{}'.format(self.payload_type)

class PayloadConfiguration(Payload):
    def __init__(self, payload_type, payload):
        Payload.__init__(self, payload_type, payload)

    def get_ids(self):
        return ()

    def __str__(self):
        return '{}'.format(self.payload_type)

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

def get_TCC(definition, service_type):
    return PayloadTCC('com.apple.TCC.configuration-profile-policy', service_type, {
                        'Allowed': definition.get('Allowed'),
                        'CodeRequirement': definition.get('CodeRequirement'),
                        'IdentifierType': definition.get('IdentifierType'),
                        'Identifier': definition.get('Identifier'),
                        'StaticCode': definition.get('StaticCode'),
                    })

def get_payloads(payload_type, content, profile):
    profile_description = ' in profile "{}" ({})'.format(profile['ProfileDisplayName'], profile['ProfileIdentifier']) if profile else ''
    if payload_type == 'com.apple.TCC.configuration-profile-policy':
        if 'Services' in content:
            for service_type, definition_array in content['Services'].items():
                for definition in definition_array:
                    if service_type == 'SystemPolicyAllFiles' or service_type == 'Accessibility':
                        yield get_TCC(definition, service_type)
                    else:
                        print_warning('Unexpected payload type: {}, {}{}'.format(payload_type, service_type, profile_description))
        else:
            print_warning('Profile contains com.apple.TCC.configuration-profile-policy policy but no Services{}'.format(profile_description))
    elif payload_type == 'com.apple.syspolicy.kernel-extension-policy':
        for id in content["AllowedTeamIdentifiers"]:
            yield PayloadKEXT(payload_type, id)
    elif payload_type == 'com.apple.system-extension-policy':
        if 'AllowedSystemExtensions' in content:
            for team_id, bundle_ids in content['AllowedSystemExtensions'].items():
                for bundle_id in bundle_ids:
                    yield PayloadSysExt(payload_type, team_id, bundle_id)
        else:
            print_warning('Profile contains com.apple.system-extension-policy policy but no AllowedSystemExtensions{}'.format(profile_description))
    elif payload_type == 'com.apple.webcontent-filter':
        yield PayloadWebContentFilter(payload_type, {
            'FilterType': content.get('FilterType'),
            'PluginBundleID': content.get('PluginBundleID'),
            'FilterSockets': content.get('FilterSockets'),
            'FilterDataProviderBundleIdentifier': content.get('FilterDataProviderBundleIdentifier'),
            'FilterDataProviderDesignatedRequirement': content.get('FilterDataProviderDesignatedRequirement'),
            'FilterGrade': content.get('FilterGrade'),
        })
    elif payload_type == 'com.apple.notificationsettings':
        for definition in content['NotificationSettings']:
            yield PayloadNotifications(payload_type, definition)
    elif payload_type == 'com.apple.servicemanagement':
        for definition in content['Rules']:
            yield PayloadServiceManagement(payload_type, definition)
    elif payload_type == 'com.apple.ManagedClient.preferences':
        if 'PayloadContentManagedPreferences' in content:
            preferences = content['PayloadContentManagedPreferences']

            for domain, settings in preferences.items():
                if 'Forced' in settings:
                    forced = settings['Forced']

                    for setting in forced:
                        if 'mcx_preference_settings' in setting:
                            mcx_preference_settings = setting['mcx_preference_settings']

                            if domain == 'com.microsoft.wdav.atp':
                                if 'OnboardingInfo' in mcx_preference_settings:
                                    onboarding_info = mcx_preference_settings['OnboardingInfo']
                                    yield PayloadOnboardingInfo(payload_type + '/' + domain, onboarding_info)
                            elif domain == 'com.microsoft.wdav' or domain == 'com.microsoft.wdav.ext':
                                yield PayloadConfiguration(payload_type + '/' + domain, mcx_preference_settings)

def parse_profiles(path):
    result = {}
    plist = read_plist(path)

    for level, profiles in plist.items():
        for profile in profiles:
            for item in profile['ProfileItems']:
                payload_type = item['PayloadType']
                content = item['PayloadContent']

                for payload in get_payloads(payload_type, content, profile):
                    if payload in result:
                        result_payloads = result[payload]
                    else:
                        result_payloads = []

                    result_payloads.append({
                        'payload': payload,
                        'path': path,
                        'level': level,
                        'name': profile['ProfileDisplayName'],
                        'time': profile['ProfileInstallDate']
                    })

                    result[payload] = result_payloads

    return result

def parse_expected(path):
    result = []

    for item in read_plist(path)['PayloadContent']:
        payload_type = item['PayloadType']
        payloads = list(get_payloads(payload_type, item, None))

        if len(payloads) == 0:
            print_warning('Unexpected payload type: {}, {}'.format(payload_type, item))

        result += payloads

    return result

def parse_tcc(path):
    result = {}
    mdm_tcc = '/tmp/MDMOverrides.plist'

    try:
        shutil.copy(path, mdm_tcc)
        subprocess.run(['plutil', '-convert', 'xml1', mdm_tcc], check=True, capture_output=True)
        tcc = read_plist(mdm_tcc)
    except (IOError, subprocess.CalledProcessError) as e:
        tcc = None
        print_warning('No {} found or conversion failed, is the machine enrolled into MDM? Error: {}'.format(path, e))

    if tcc:
        for service in tcc.values():
            if 'kTCCServiceSystemPolicyAllFiles' in service:
                definition = service['kTCCServiceSystemPolicyAllFiles']
                d = get_TCC(definition, 'SystemPolicyAllFiles')
                definition['CodeRequirementData']
                result[d] = {
                    'CodeRequirement': definition.get('CodeRequirement'),
                    'IdentifierType': definition.get('IdentifierType'),
                    'Identifier': definition.get('Identifier'),
                    'Allowed': definition.get('Allowed'),
                }

    return result

def format_location(profile_data):
    return '{}, profile: "{}", deployed: {}'.format(profile_data['path'], profile_data['name'], profile_data['time'])

def report_configurations(name, configs, is_ext):
    if len(configs) == 1:
        print_success("Configuration payload {} found".format(name))
    elif len(configs) == 0:
        if is_ext:
            print_debug("Configuration payload {} not found".format(name))
        else:
            print_warning("Configuration payload {} not found".format(name))
    elif len(configs) > 1:
        print_warning("Multiple payloads {} found".format(name))
        settings_map = {}

        i = 1
        for config in configs:
            print_debug("  {}: {}".format(i, config))

            for k, v in config['payload'].payload.items():
                if k in settings_map:
                    settings_list = settings_map[k]
                    settings_list.append({'settings': v, 'config': config})
                else:
                    settings_list = []                   
                    settings_list.append({'settings': v, 'config': config})
                    settings_map[k] = settings_list

            i += 1

        for k, values in settings_map.items():
            if len(values) > 1:
                print_error("Conflicting configuration payloads {}, setting {} will be lost fully or partially".format(name, k))
                i = 1
                for v in values:
                    print_debug("  {}: {} -> {}".format(i, v['config'], v['settings']))
                    i += 1

def report(path_profiles, path_expected, path_tcc):
    map_profiles = parse_profiles(path_profiles)
    list_expected = parse_expected(path_expected)
    tcc = parse_tcc(path_tcc)

    for expected in list_expected:
        if expected in map_profiles:
            m = map_profiles[expected]

            t = None
            check_tcc = False

            if expected.payload_type == 'com.apple.TCC.configuration-profile-policy' and expected.service_type == 'SystemPolicyAllFiles':
                if tcc and expected in tcc:
                    t = tcc[expected]

                check_tcc = True

            if len(m) == 1:
                if expected.payload == m[0]['payload'].payload:
                    if not check_tcc or t == m[0]['payload'].payload:
                        print_success("Found {} in {}".format(expected, format_location(m[0])))
                    else:
                        print_error("Found {} in {} but not in TCC database".format(expected, format_location(m[0])))
                else:
                    print_error("Found, but does not match expected {} in {}".format(expected, format_location(m[0])))
                    print_debug("    Found: {}".format(m[0]['payload'].payload))
            else:
                print_error("Duplicate definitions, only one of them is active: {}".format(expected))

                n=1
                for d in m:
                    if expected.payload == d['payload'].payload:
                        match_label = '{}[Match]{}'.format(tc.green, tc.cancel)
                    else:
                        match_label = '{}[Mismatch]{}'.format(tc.red, tc.cancel)

                    if check_tcc:
                        if t == d['payload'].payload:
                            tcc_label = ' {}[In TCC]{}'.format(tc.green, tc.cancel)
                        else:
                            tcc_label = ' {}[Not in TCC]{}'.format(tc.red, tc.cancel)
                    else:
                        tcc_label = ''

                    print_debug("    Candidate {}: {} {}{}{}".format(n, format_location(d), tc.cancel, match_label, tcc_label))
                    n += 1
        else:
            print_error("Not provided: {}".format(expected))

    # 'com.apple.ManagedClient.preferences'
    onboarding_infos = []
    configs = []
    configs_ext = []
    for k, v in map_profiles.items():
        if k.payload_type == 'com.apple.ManagedClient.preferences/com.microsoft.wdav.atp':
            onboarding_infos += v
        elif k.payload_type == 'com.apple.ManagedClient.preferences/com.microsoft.wdav':
            print(v)
            configs += v
        elif k.payload_type == 'com.apple.ManagedClient.preferences/com.microsoft.wdav.ext':
            configs_ext += v

    if len(onboarding_infos) == 1:
        print_success("Onboarding info found")
    elif len(onboarding_infos) == 0:
        print_error("Onboarding info not found")
    else:
        print_error("Conflicting onboarding info profiles found")
        i = 1
        for info in onboarding_infos:
            print_debug("  {}: {}".format(i, info))
            i += 1

    report_configurations('com.microsoft.wdav', configs, False)
    report_configurations('com.microsoft.wdav.ext', configs_ext, True)

parser = argparse.ArgumentParser(description = "Validates MDM profiles for Defender")
parser.add_argument("--template", type=str, help = "Template file from https://github.com/microsoft/mdatp-xplat/blob/master/macos/mobileconfig/combined/mdatp.mobileconfig")
parser.add_argument("--in", type=str, help = "Optional, read exported profiles from it, instead of getting from the system")
parser.add_argument("--tcc", type=str, help = "Optional, read TCC overrides from it, instead of getting from the system")
args = parser.parse_args()

if not args.template:
    args.template = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'mdatp.mobileconfig')

    if not os.path.exists(args.template):
        url = 'https://raw.githubusercontent.com/microsoft/mdatp-xplat/master/macos/mobileconfig/combined/mdatp.mobileconfig'
        args.template = '/tmp/mdatp.mobileconfig'
        print_debug("Downloading template from {}".format(url))      

        try:
            import urllib.request
            print_debug('Using module urllib.request')

            try:
                with urllib.request.urlopen(url) as response, open(args.template, 'wb') as out_file:
                    shutil.copyfileobj(response, out_file)
            except urllib.error.URLError as e:
                print_warning('Your Python has issues with SSL validation, please fix it. Querying {} with disabled validation. Error: {}'.format(url, e))
                import ssl
                ssl._create_default_https_context = ssl._create_unverified_context

                with urllib.request.urlopen(url) as response, open(args.template, 'wb') as out_file:
                    shutil.copyfileobj(response, out_file)
        except ImportError as e:
            print_warning('urllib.request not available: {}'.format(e))
            raise

args.template = os.path.abspath(os.path.expanduser(args.template))

in_file = getattr(args, 'in')

if not in_file:
    in_file = '/tmp/profiles.xml'

    if os.path.exists(in_file):
        print_debug("{} already exists, remove it first".format(in_file))
        subprocess.run(['sudo', 'rm', '-f', in_file], check=False)

    print_debug('Running "profiles" command, sudo password may be required...')
    subprocess.run(['sudo', 'profiles', 'show', '-output', in_file], check=True)

in_file = os.path.abspath(os.path.expanduser(in_file))

if not args.tcc:
    args.tcc = '/Library/Application Support/com.apple.TCC/MDMOverrides.plist'

args.tcc = os.path.abspath(os.path.expanduser(args.tcc))

report(in_file, args.template, args.tcc)
