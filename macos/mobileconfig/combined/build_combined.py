#!/usr/bin/env python3
"""Merge individual MDM profiles into a single combined profile.

This script combines multiple macOS .mobileconfig files into a single
combined profile, merging TCC configurations as needed.
"""

from __future__ import annotations

import argparse
import os
import plistlib
import re
import sys
import uuid


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


def _print_warning(msg: str) -> None:
    """Print a warning message.

    Args:
        msg: Warning message to print.

    """
    pass


def _print_success(msg: str) -> None:
    """Print a success message.

    Args:
        msg: Success message to print.

    """
    pass


def _print_error(msg: str) -> None:
    """Print an error message.

    Args:
        msg: Error message to print.

    """
    pass


def _print_debug(msg: str) -> None:
    """Print a debug message.

    Args:
        msg: Debug message to print.

    """
    pass


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


def write_plist(path: str, plist: dict) -> None:
    """Write a plist dictionary to a file.

    Args:
        path: Path to write the plist file.
        plist: Dictionary to write.

    """
    _print_debug(f"Saving {path}...")

    if "dumps" in plistlib.__all__:
        s = plistlib.dumps(plist).decode("UTF-8")
    else:
        s = plistlib.writePlistToString(plist)

    output_file = os.path.abspath(os.path.expanduser(path))
    header_prefix1 = "<?xml"
    header_prefix2 = "<!DOCTYPE"
    re_indent = re.compile("[ \t]+<")
    re_replace = "<"
    output_type = "w"
    if isinstance(s, bytes):
        output_type = "wb"
        header_prefix1 = header_prefix1.encode()
        header_prefix2 = header_prefix2.encode()
        re_indent = re.compile(b"[ \t]+<")
        re_replace = b"<"

    with open(output_file, output_type) as f:
        for line in s.splitlines():
            cleaned_line = re_indent.sub(re_replace, line)
            f.write(cleaned_line)
            if cleaned_line.startswith(header_prefix1) or cleaned_line.startswith(header_prefix2):
                f.write("\n")


parser = argparse.ArgumentParser(
    description="Merge individual MDM profiles into a single combined profile"
)
parser.add_argument("--in", type=str, nargs="+", help="Individual .mobileconfig profiles to read")
parser.add_argument("--template", type=str, help="Template to use for output")
parser.add_argument(
    "--out", type=str, help="Optional, writes combined profile to this .mobileconfig"
)
args = parser.parse_args()

try:
    plist_template = read_plist(args.template)
except (OSError, plistlib.InvalidFileException) as e:
    _print_error(f"Cannot read template {args.template}: {e}")
    sys.exit(1)

plist_template["PayloadContent"] = []
plist_template["PayloadIdentifier"] = plist_template["PayloadUUID"] = str(uuid.uuid1()).upper()

tcc_payload = None
for f_in in getattr(args, "in"):
    try:
        plist = read_plist(f_in)
        for payload in plist["PayloadContent"]:

            # JAMF doesn't like multiple TCC configuration profiles,
            # so combine into a single one
            if payload["PayloadType"] == "com.apple.TCC.configuration-profile-policy":
                if tcc_payload is None:
                    tcc_payload = payload
                else:
                    # Merge the new TCC profile with the existing one.
                    tcc_payload["Services"].update(payload["Services"])
                # Don't append TCC until all profiles have been examined
                continue

            plist_template["PayloadContent"].append(payload)
    except (OSError, plistlib.InvalidFileException, KeyError) as e:
        _print_error(f"Cannot read input file {f_in}: {e}")

if tcc_payload is not None:
    plist_template["PayloadContent"].append(tcc_payload)

out_file = args.out

if out_file:
    write_plist(out_file, plist_template)
else:
    _print_debug(str(plist_template))
