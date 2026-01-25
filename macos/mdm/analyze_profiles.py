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
import ssl
import subprocess
import sys
import urllib.error
import urllib.request

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class _TerminalColors:
    """Terminal color codes for output formatting."""

    green: str
    yellow: str
    red: str
    grey: str
    cancel: str


if sys.stdout.isatty():

    class _TerminalColorsEnabled(_TerminalColors):
        """Terminal colors when TTY is available."""

        green = "\033[92m"
        yellow = "\033[93m"
        red = "\033[91m"
        grey = "\033[2m"
        cancel = "\033[0m"

    tc: _TerminalColors = _TerminalColorsEnabled()
else:

    class _TerminalColorsDisabled(_TerminalColors):
        """Terminal colors when TTY is not available."""

        green = ""
        yellow = ""
        red = ""
        grey = ""
        cancel = ""

    tc = _TerminalColorsDisabled()


class Payload:
    """Base class for MDM payloads."""

    def __init__(self, payload_type: str, payload: dict | None) -> None:
        """Initialize a payload.

        Args:
            payload_type: Type identifier for the payload.
            payload: Payload data dictionary.

        """
        self.payload_type = payload_type
        self.payload = payload

    def get_ids(self) -> tuple:
        """Return the unique identifiers for this payload.

        Returns:
            Tuple of identifier values.

        Raises:
            NotImplementedError: Must be overridden by subclasses.

        """
        raise NotImplementedError("Subclasses must implement get_ids()")

    def get_all_ids(self) -> tuple:
        """Return all identifiers including payload type.

        Returns:
            Tuple containing payload type and all IDs.

        """
        return (self.payload_type, *self.get_ids())

    def __hash__(self) -> int:
        """Return hash of the payload."""
        return hash(self.get_all_ids())

    def __eq__(self, other: object) -> bool:
        """Check equality with another payload."""
        if not isinstance(other, Payload):
            return NotImplemented
        return self.get_all_ids() == other.get_all_ids()

    def __ne__(self, other: object) -> bool:
        """Check inequality with another payload."""
        return not self == other

    def __repr__(self) -> str:
        """Return string representation."""
        return self.__str__()


class PayloadTCC(Payload):
    """TCC (Transparency, Consent, and Control) payload."""

    def __init__(self, payload_type: str, service_type: str, payload: dict) -> None:
        """Initialize a TCC payload.

        Args:
            payload_type: Type identifier for the payload.
            service_type: TCC service type.
            payload: Payload data dictionary.

        """
        Payload.__init__(self, payload_type, payload)
        self.service_type = service_type
        self.identifier = payload["Identifier"]

    def get_ids(self) -> tuple:
        """Return the unique identifiers for this payload."""
        return (self.identifier, self.service_type)

    def __str__(self) -> str:
        """Return string representation."""
        return f"{self.payload_type}/{self.service_type} ({self.identifier})"


class PayloadKEXT(Payload):
    """Kernel extension payload."""

    def __init__(self, payload_type: str, kext_id: str) -> None:
        """Initialize a KEXT payload.

        Args:
            payload_type: Type identifier for the payload.
            kext_id: Kernel extension identifier.

        """
        Payload.__init__(self, payload_type, None)
        self.kext_id = kext_id

    def get_ids(self) -> tuple:
        """Return the unique identifiers for this payload."""
        return (self.kext_id,)

    def __str__(self) -> str:
        """Return string representation."""
        return f"{self.payload_type} ({self.kext_id})"


class PayloadSysExt(Payload):
    """System extension payload."""

    def __init__(self, payload_type: str, team_id: str, bundle_id: str) -> None:
        """Initialize a system extension payload.

        Args:
            payload_type: Type identifier for the payload.
            team_id: Developer team identifier.
            bundle_id: Bundle identifier.

        """
        Payload.__init__(self, payload_type, None)
        self.team_id = team_id
        self.bundle_id = bundle_id

    def get_ids(self) -> tuple:
        """Return the unique identifiers for this payload."""
        return (self.team_id, self.bundle_id)

    def __str__(self) -> str:
        """Return string representation."""
        return f"{self.payload_type} ({self.team_id}, {self.bundle_id})"


class PayloadWebContentFilter(Payload):
    """Web content filter payload."""

    def __init__(self, payload_type: str, payload: dict) -> None:
        """Initialize a web content filter payload.

        Args:
            payload_type: Type identifier for the payload.
            payload: Payload data dictionary.

        """
        Payload.__init__(self, payload_type, payload)
        self.filter_id = payload["FilterDataProviderBundleIdentifier"]
        self.properties: dict = {}

        filter_props = (
            "FilterDataProviderDesignatedRequirement",
            "FilterGrade",
            "FilterSockets",
            "FilterType",
            "PluginBundleID",
        )
        for p in filter_props:
            self.properties[p] = payload[p]

    def get_ids(self) -> tuple:
        """Return the unique identifiers for this payload."""
        return (self.filter_id,)

    def __str__(self) -> str:
        """Return string representation."""
        return f"{self.payload_type} ({self.filter_id})"


class PayloadNotifications(Payload):
    """Notifications payload."""

    def __init__(self, payload_type: str, payload: dict) -> None:
        """Initialize a notifications payload.

        Args:
            payload_type: Type identifier for the payload.
            payload: Payload data dictionary.

        """
        Payload.__init__(self, payload_type, payload)
        self.notification_id = payload["BundleIdentifier"]

    def get_ids(self) -> tuple:
        """Return the unique identifiers for this payload."""
        return (self.notification_id,)

    def __str__(self) -> str:
        """Return string representation."""
        return f"{self.payload_type} ({self.notification_id})"


class PayloadServiceManagement(Payload):
    """Service management payload."""

    def __init__(self, payload_type: str, payload: dict) -> None:
        """Initialize a service management payload.

        Args:
            payload_type: Type identifier for the payload.
            payload: Payload data dictionary.

        """
        Payload.__init__(self, payload_type, payload)
        self.service_id = "{}={}".format(payload["RuleType"], payload["RuleValue"])

    def get_ids(self) -> tuple:
        """Return the unique identifiers for this payload."""
        return (self.service_id,)

    def __str__(self) -> str:
        """Return string representation."""
        return f"{self.payload_type} ({self.service_id})"


class PayloadOnboardingInfo(Payload):
    """Onboarding info payload."""

    def __init__(self, payload_type: str, payload: dict) -> None:
        """Initialize an onboarding info payload.

        Args:
            payload_type: Type identifier for the payload.
            payload: Payload data dictionary.

        """
        Payload.__init__(self, payload_type, payload)

    def get_ids(self) -> tuple:
        """Return the unique identifiers for this payload."""
        return ()

    def __str__(self) -> str:
        """Return string representation."""
        return f"{self.payload_type}"


class PayloadConfiguration(Payload):
    """Configuration payload."""

    def __init__(self, payload_type: str, payload: dict) -> None:
        """Initialize a configuration payload.

        Args:
            payload_type: Type identifier for the payload.
            payload: Payload data dictionary.

        """
        Payload.__init__(self, payload_type, payload)

    def get_ids(self) -> tuple:
        """Return the unique identifiers for this payload."""
        return ()

    def __str__(self) -> str:
        """Return string representation."""
        return f"{self.payload_type}"


def _print_warning(msg: str) -> None:
    """Print a warning message.

    Args:
        msg: Warning message to print.

    """
    _ = msg  # Suppress unused argument


def _print_success(msg: str) -> None:
    """Print a success message.

    Args:
        msg: Success message to print.

    """
    _ = msg  # Suppress unused argument


def _print_error(msg: str) -> None:
    """Print an error message.

    Args:
        msg: Error message to print.

    """
    _ = msg  # Suppress unused argument


def _print_debug(msg: str) -> None:
    """Print a debug message.

    Args:
        msg: Debug message to print.

    """
    _ = msg  # Suppress unused argument


def read_plist(path: str) -> dict:
    """Read a plist file and return its contents.

    Args:
        path: Path to the plist file.

    Returns:
        Dictionary containing plist contents.

    """
    _print_debug(f"Reading {path}")

    if "load" in plistlib.__all__:
        with open(path, "rb") as f:
            return plistlib.load(f)
    else:
        return plistlib.readPlist(path)


def get_tcc(definition: dict, service_type: str) -> PayloadTCC:
    """Create a TCC payload from a definition.

    Args:
        definition: TCC definition dictionary.
        service_type: TCC service type.

    Returns:
        PayloadTCC instance.

    """
    return PayloadTCC(
        "com.apple.TCC.configuration-profile-policy",
        service_type,
        {
            "Allowed": definition.get("Allowed"),
            "CodeRequirement": definition.get("CodeRequirement"),
            "IdentifierType": definition.get("IdentifierType"),
            "Identifier": definition.get("Identifier"),
            "StaticCode": definition.get("StaticCode"),
        },
    )


def get_payloads(payload_type: str, content: dict, profile: dict | None) -> list:  # noqa: PLR0912
    """Extract payloads from profile content.

    Args:
        payload_type: Type of payload to extract.
        content: Content dictionary.
        profile: Profile dictionary for error messages.

    Yields:
        Payload instances.

    """
    if profile:
        profile_desc = ' in profile "{}" ({})'.format(
            profile["ProfileDisplayName"], profile["ProfileIdentifier"]
        )
    else:
        profile_desc = ""
    if payload_type == "com.apple.TCC.configuration-profile-policy":
        if "Services" in content:
            for service_type, definition_array in content["Services"].items():
                for definition in definition_array:
                    if service_type in {"SystemPolicyAllFiles", "Accessibility"}:
                        yield get_tcc(definition, service_type)
                    else:
                        _print_warning(
                            f"Unexpected payload type: {payload_type}, "
                            f"{service_type}{profile_desc}"
                        )
        else:
            _print_warning(
                f"Profile contains com.apple.TCC.configuration-profile-policy "
                f"policy but no Services{profile_desc}"
            )
    elif payload_type == "com.apple.syspolicy.kernel-extension-policy":
        for kext_id in content["AllowedTeamIdentifiers"]:
            yield PayloadKEXT(payload_type, kext_id)
    elif payload_type == "com.apple.system-extension-policy":
        if "AllowedSystemExtensions" in content:
            for team_id, bundle_ids in content["AllowedSystemExtensions"].items():
                for bundle_id in bundle_ids:
                    yield PayloadSysExt(payload_type, team_id, bundle_id)
        else:
            _print_warning(
                f"Profile contains com.apple.system-extension-policy "
                f"policy but no AllowedSystemExtensions{profile_desc}"
            )
    elif payload_type == "com.apple.webcontent-filter":
        yield PayloadWebContentFilter(
            payload_type,
            {
                "FilterType": content.get("FilterType"),
                "PluginBundleID": content.get("PluginBundleID"),
                "FilterSockets": content.get("FilterSockets"),
                "FilterDataProviderBundleIdentifier": content.get(
                    "FilterDataProviderBundleIdentifier"
                ),
                "FilterDataProviderDesignatedRequirement": content.get(
                    "FilterDataProviderDesignatedRequirement"
                ),
                "FilterGrade": content.get("FilterGrade"),
            },
        )
    elif payload_type == "com.apple.notificationsettings":
        for definition in content["NotificationSettings"]:
            yield PayloadNotifications(payload_type, definition)
    elif payload_type == "com.apple.servicemanagement":
        for definition in content["Rules"]:
            yield PayloadServiceManagement(payload_type, definition)
    elif (
        payload_type == "com.apple.ManagedClient.preferences"
        and "PayloadContentManagedPreferences" in content
    ):
        preferences = content["PayloadContentManagedPreferences"]

        for domain, settings in preferences.items():
            if "Forced" in settings:
                forced = settings["Forced"]

                for setting in forced:
                    if "mcx_preference_settings" in setting:
                        mcx_preference_settings = setting["mcx_preference_settings"]

                        if domain == "com.microsoft.wdav.atp":
                            if "OnboardingInfo" in mcx_preference_settings:
                                onboarding_info = mcx_preference_settings["OnboardingInfo"]
                                payload_key = payload_type + "/" + domain
                                yield PayloadOnboardingInfo(payload_key, onboarding_info)
                        elif domain in {"com.microsoft.wdav", "com.microsoft.wdav.ext"}:
                            payload_key = payload_type + "/" + domain
                            yield PayloadConfiguration(payload_key, mcx_preference_settings)


def parse_profiles(path: str) -> dict:
    """Parse profiles from plist file.

    Args:
        path: Path to the profiles plist file.

    Returns:
        Dictionary mapping payloads to their profile data.

    """
    result: dict = {}
    plist = read_plist(path)

    for level, profiles in plist.items():
        for profile in profiles:
            for item in profile["ProfileItems"]:
                payload_type = item["PayloadType"]
                content = item["PayloadContent"]

                for payload in get_payloads(payload_type, content, profile):
                    result_payloads = result.get(payload, [])

                    result_payloads.append(
                        {
                            "payload": payload,
                            "path": path,
                            "level": level,
                            "name": profile["ProfileDisplayName"],
                            "time": profile["ProfileInstallDate"],
                        }
                    )

                    result[payload] = result_payloads

    return result


def parse_expected(path: str) -> list:
    """Parse expected payloads from plist file.

    Args:
        path: Path to the expected payloads plist file.

    Returns:
        List of expected payloads.

    """
    result: list = []

    for item in read_plist(path)["PayloadContent"]:
        payload_type = item["PayloadType"]
        payloads = list(get_payloads(payload_type, item, None))

        if len(payloads) == 0:
            _print_warning(f"Unexpected payload type: {payload_type}, {item}")

        result += payloads

    return result


def parse_tcc(path: str) -> dict:
    """Parse TCC overrides from plist file.

    Args:
        path: Path to the TCC overrides plist file.

    Returns:
        Dictionary mapping TCC payloads to their data.

    """
    result: dict = {}
    mdm_tcc = "/tmp/MDMOverrides.plist"  # noqa: S108

    try:
        shutil.copy(path, mdm_tcc)
        subprocess.run(["plutil", "-convert", "xml1", mdm_tcc], check=True, capture_output=True)
        tcc = read_plist(mdm_tcc)
    except (OSError, subprocess.CalledProcessError) as e:
        tcc = None
        _print_warning(
            f"No {path} found or conversion failed, "
            f"is the machine enrolled into MDM? Error: {e}"
        )

    if tcc:
        for service in tcc.values():
            if "kTCCServiceSystemPolicyAllFiles" in service:
                definition = service["kTCCServiceSystemPolicyAllFiles"]
                d = get_tcc(definition, "SystemPolicyAllFiles")
                _ = definition["CodeRequirementData"]  # Access for validation
                result[d] = {
                    "CodeRequirement": definition.get("CodeRequirement"),
                    "IdentifierType": definition.get("IdentifierType"),
                    "Identifier": definition.get("Identifier"),
                    "Allowed": definition.get("Allowed"),
                }

    return result


def format_location(profile_data: dict) -> str:
    """Format profile location for display.

    Args:
        profile_data: Profile data dictionary.

    Returns:
        Formatted location string.

    """
    return '{}, profile: "{}", deployed: {}'.format(
        profile_data["path"], profile_data["name"], profile_data["time"]
    )


def report_configurations(name: str, configs: list, is_ext: bool) -> None:
    """Report configuration payload status.

    Args:
        name: Configuration name.
        configs: List of configuration dictionaries.
        is_ext: Whether this is an extension configuration.

    """
    if len(configs) == 1:
        _print_success(f"Configuration payload {name} found")
    elif len(configs) == 0:
        if is_ext:
            _print_debug(f"Configuration payload {name} not found")
        else:
            _print_warning(f"Configuration payload {name} not found")
    elif len(configs) > 1:
        _print_warning(f"Multiple payloads {name} found")
        settings_map: dict = {}

        i = 1
        for config in configs:
            _print_debug(f"  {i}: {config}")

            for k, v in config["payload"].payload.items():
                if k in settings_map:
                    settings_list = settings_map[k]
                    settings_list.append({"settings": v, "config": config})
                else:
                    settings_list = [{"settings": v, "config": config}]
                    settings_map[k] = settings_list

            i += 1

        for k, values in settings_map.items():
            if len(values) > 1:
                _print_error(
                    f"Conflicting configuration payloads {name}, "
                    f"setting {k} will be lost fully or partially"
                )
                i = 1
                for v in values:
                    _print_debug("  {}: {} -> {}".format(i, v["config"], v["settings"]))
                    i += 1


def report(path_profiles: str, path_expected: str, path_tcc: str) -> None:  # noqa: PLR0912, PLR0915
    """Generate report on MDM profile status.

    Args:
        path_profiles: Path to profiles file.
        path_expected: Path to expected payloads file.
        path_tcc: Path to TCC overrides file.

    """
    map_profiles = parse_profiles(path_profiles)
    list_expected = parse_expected(path_expected)
    tcc = parse_tcc(path_tcc)

    for expected in list_expected:
        if expected in map_profiles:
            m = map_profiles[expected]

            t = None
            check_tcc = False

            is_tcc_type = (
                expected.payload_type == "com.apple.TCC.configuration-profile-policy"
                and expected.service_type == "SystemPolicyAllFiles"
            )
            if is_tcc_type:
                if tcc and expected in tcc:
                    t = tcc[expected]

                check_tcc = True

            if len(m) == 1:
                if expected.payload == m[0]["payload"].payload:
                    if not check_tcc or t == m[0]["payload"].payload:
                        _print_success(f"Found {expected} in {format_location(m[0])}")
                    else:
                        _print_error(
                            f"Found {expected} in {format_location(m[0])} "
                            f"but not in TCC database"
                        )
                else:
                    _print_error(
                        f"Found, but does not match expected {expected} "
                        f"in {format_location(m[0])}"
                    )
                    _print_debug("    Found: {}".format(m[0]["payload"].payload))
            else:
                _print_error(f"Duplicate definitions, only one of them is active: {expected}")

                n = 1
                for d in m:
                    if expected.payload == d["payload"].payload:
                        match_label = f"{tc.green}[Match]{tc.cancel}"
                    else:
                        match_label = f"{tc.red}[Mismatch]{tc.cancel}"

                    if check_tcc:
                        if t == d["payload"].payload:
                            tcc_label = f" {tc.green}[In TCC]{tc.cancel}"
                        else:
                            tcc_label = f" {tc.red}[Not in TCC]{tc.cancel}"
                    else:
                        tcc_label = ""

                    _print_debug(
                        f"    Candidate {n}: {format_location(d)} "
                        f"{tc.cancel}{match_label}{tcc_label}"
                    )
                    n += 1
        else:
            _print_error(f"Not provided: {expected}")

    # 'com.apple.ManagedClient.preferences'
    onboarding_infos: list = []
    configs: list = []
    configs_ext: list = []
    for k, v in map_profiles.items():
        if k.payload_type == "com.apple.ManagedClient.preferences/com.microsoft.wdav.atp":
            onboarding_infos += v
        elif k.payload_type == "com.apple.ManagedClient.preferences/com.microsoft.wdav":
            configs += v
        elif k.payload_type == "com.apple.ManagedClient.preferences/com.microsoft.wdav.ext":
            configs_ext += v

    if len(onboarding_infos) == 1:
        _print_success("Onboarding info found")
    elif len(onboarding_infos) == 0:
        _print_error("Onboarding info not found")
    else:
        _print_error("Conflicting onboarding info profiles found")
        i = 1
        for info in onboarding_infos:
            _print_debug(f"  {i}: {info}")
            i += 1

    report_configurations("com.microsoft.wdav", configs, False)
    report_configurations("com.microsoft.wdav.ext", configs_ext, True)


def main() -> int:
    """Analyze MDM profiles for Defender.

    Returns:
        Exit code (0 for success, non-zero for error).

    """
    parser = argparse.ArgumentParser(description="Validate MDM profiles for Defender")
    parser.add_argument("--template", type=str, help="Template file from mdatp-xplat repo")
    parser.add_argument("--in", type=str, help="Optional, read exported profiles from it")
    parser.add_argument("--tcc", type=str, help="Optional, read TCC overrides from it")
    args = parser.parse_args()

    if not args.template:
        args.template = os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "mdatp.mobileconfig"
        )

        if not os.path.exists(args.template):
            url = (
                "https://raw.githubusercontent.com/microsoft/mdatp-xplat/"
                "master/macos/mobileconfig/combined/mdatp.mobileconfig"
            )
            args.template = "/tmp/mdatp.mobileconfig"  # noqa: S108
            _print_debug(f"Downloading template from {url}")

            _print_debug("Using module urllib.request")

            try:
                with urllib.request.urlopen(url) as response:  # noqa: S310, SIM117
                    with open(args.template, "wb") as out_file:
                        shutil.copyfileobj(response, out_file)
            except urllib.error.URLError as e:
                _print_warning(
                    f"Your Python has issues with SSL validation, please fix it. "
                    f"Querying {url} with disabled validation. Error: {e}"
                )
                ssl._create_default_https_context = ssl._create_unverified_context

                with urllib.request.urlopen(url) as response:  # noqa: S310, SIM117
                    with open(args.template, "wb") as out_file:
                        shutil.copyfileobj(response, out_file)

    args.template = os.path.abspath(os.path.expanduser(args.template))

    in_file = getattr(args, "in")

    if not in_file:
        in_file = "/tmp/profiles.xml"  # noqa: S108

        if os.path.exists(in_file):
            _print_debug(f"{in_file} already exists, remove it first")
            subprocess.run(["sudo", "rm", "-f", in_file], check=False)

        _print_debug('Running "profiles" command, sudo password may be required...')
        subprocess.run(["sudo", "profiles", "show", "-output", in_file], check=True)

    in_file = os.path.abspath(os.path.expanduser(in_file))

    if not args.tcc:
        args.tcc = "/Library/Application Support/com.apple.TCC/MDMOverrides.plist"

    args.tcc = os.path.abspath(os.path.expanduser(args.tcc))

    report(in_file, args.template, args.tcc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
