#!/usr/bin/env python
# pylint: disable=C0115 C0209 C0116 C0301 C0114 R0903 C0103 R1702 R0914 R0912 R0915 W0129 C0325

from __future__ import print_function
import os
import sys
import plistlib
import shutil
import argparse
import subprocess

MDATP_MDMOVERRIDES = '/Library/Application Support/com.apple.TCC/MDMOverrides.plist'
MDATP_MOBILECONFIG_URL = 'https://raw.githubusercontent.com/microsoft/mdatp-xplat/master/macos/mobileconfig/combined/mdatp.mobileconfig'

class TerminalColor:
    def __init__(self):
        self._colors = {
            'green': '\033[92m' if sys.stdout.isatty() else '',
            'yellow': '\033[93m' if sys.stdout.isatty() else '',
            'red': '\033[91m' if sys.stdout.isatty() else '',
            'grey': '\033[2m' if sys.stdout.isatty() else '',
            'cancel': '\033[0m' if sys.stdout.isatty() else ''
        }

    def __getattr__(self, name):
        return self._colors.get(name, '')

tc = TerminalColor()

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
    def __init__(self, payload_type, team_id):
        Payload.__init__(self, payload_type, None)
        self.team_id = team_id

    def get_ids(self):
        return (self.team_id,)

    def __str__(self):
        return '{} ({})'.format(self.payload_type, self.team_id)

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
    try:
        with open(path, 'rb') as f:
            plist_data = plistlib.load(f)
            return plist_data
    except FileNotFoundError:
        print_debug(f'Error: File not found {path}')
        return None
    except plistlib.InvalidFileException:
        print_debug(f'Error: Invalid plist file {path}')
        return None
    except IOError as e:
        print_debug(f'IOError reading plist file: {e}')
        return None

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
                    if service_type in ('SystemPolicyAllFiles', 'Accessibility'):
                        yield get_TCC(definition, service_type)
                    else:
                        print_warning('Unexpected payload type: {}, {}{}'.format(payload_type, service_type, profile_description))
        else:
            print_warning('Profile contains com.apple.TCC.configuration-profile-policy policy but no Services{}'.format(profile_description))
    elif payload_type == 'com.apple.syspolicy.kernel-extension-policy':
        for team_id in content["AllowedTeamIdentifiers"]:
            yield PayloadKEXT(payload_type, team_id)
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
                            elif domain in ('com.microsoft.wdav', 'com.microsoft.wdav.ext'):
                                yield PayloadConfiguration(payload_type + '/' + domain, mcx_preference_settings)

def parse_profiles(path):
    result = {}
    plist = read_plist(path)
    if plist is None:
        print_error("Unable to read plist {}".format(path))
        return None

    for level, profiles in plist.items():
        for profile in profiles:
            for item in profile['ProfileItems']:
                payload_type = item['PayloadType']
                content = item['PayloadContent']

                for payload in get_payloads(payload_type, content, profile):
                    result_payloads = result.get(payload, [])

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
        if path != mdm_tcc:
            shutil.copy(path, mdm_tcc)
        os.system('plutil -convert xml1 "{}"'.format(mdm_tcc))
        tcc = read_plist(mdm_tcc)
    except IOError:
        tcc = None
        print_warning('No {} found, is the machine enrolled into MDM?'.format(path))

    if tcc:
        for service in tcc.values():
            if 'kTCCServiceSystemPolicyAllFiles' in service:
                definition = service['kTCCServiceSystemPolicyAllFiles']
                d = get_TCC(definition, 'SystemPolicyAllFiles')
                # definition['CodeRequirementData']
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

def analyze_report(path_profiles, path_expected, path_tcc):
    map_profiles = parse_profiles(path_profiles)
    if map_profiles is None:
        print_error("Unable to parse profile {}".format(path_profiles))
        return

    list_expected = parse_expected(path_expected)
    tcc = parse_tcc(path_tcc)

    for expected in list_expected:
        if expected not in map_profiles:
            print_error("Not provided: {}".format(expected))
            continue

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
            continue

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


def downloader(the_url, filename):
    print_debug("Download: {} to filename: {}".format(the_url, filename))
    try:
        subprocess.run(['curl', '-sSL', '-o', filename, the_url], check=True)
    except subprocess.CalledProcessError as e:
        print_error("An error occurred: {}".format(e))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description = "Validates MDM profiles for Defender")
    parser.add_argument("--template", type=str, help = "mdatp mobile config template file from {}".format(MDATP_MOBILECONFIG_URL))
    parser.add_argument("--in", type=str, help = "Optional, read exported profiles from it, instead of getting from the system")
    parser.add_argument("--tcc", type=str, help = "Optional, read TCC overrides from it, instead of getting from the system")
    args = parser.parse_args()

    if not args.template:
        args.template = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'mdatp.mobileconfig')
        if not os.path.exists(args.template):
            args.template = '/tmp/mdatp.mobileconfig'
            downloader(MDATP_MOBILECONFIG_URL, args.template)

    if not os.path.exists(args.template):
        print_error("Unable to download {}".format(MDATP_MOBILECONFIG_URL))

    args.template = os.path.abspath(os.path.expanduser(args.template))

    in_file = getattr(args, 'in')

    if not in_file:
        in_file = '/tmp/profiles.xml'

        if os.path.exists(in_file):
            print_debug("{} already exists, remove it first".format(in_file))
            os.system('sudo rm -f "{}"'.format(in_file))

        print_debug('Running "profiles" command, sudo password may be required...')
        os.system('sudo profiles show -output "{}"'.format(in_file))

    in_file = os.path.abspath(os.path.expanduser(in_file))

    if not args.tcc:
        args.tcc = MDATP_MDMOVERRIDES

    args.tcc = os.path.abspath(os.path.expanduser(args.tcc))

    analyze_report(in_file, args.template, args.tcc)
