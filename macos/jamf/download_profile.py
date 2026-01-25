#!/usr/bin/env python3
"""Download macOS configuration profiles from JAMF server.

This script authenticates with a JAMF server and downloads
the specified macOS configuration profile in XML format.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import logging
import sys
import urllib.parse
import urllib.request
import xml.dom.minidom
from typing import NoReturn
from urllib.error import HTTPError, URLError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class JamfError(Exception):
    """Exception raised for JAMF-related errors."""

    pass


def create_auth_header(user: str, password: str) -> str:
    """Create a Basic authentication header value.

    Args:
        user: JAMF username.
        password: JAMF password.

    Returns:
        Base64-encoded credentials for Basic auth.
    """
    credentials = f"{user}:{password}".encode("utf-8")
    encoded = base64.b64encode(credentials).decode("ascii")
    return f"Basic {encoded}"


def query_jamf_profile(url: str, user: str, password: str, name: str) -> bytes:
    """Query JAMF server for a configuration profile.

    Args:
        url: JAMF server URL.
        user: JAMF username.
        password: JAMF password.
        name: Profile name to download.

    Returns:
        Raw response content from JAMF server.

    Raises:
        JamfError: If the request fails.
    """
    encoded_name = urllib.parse.quote(name)
    full_url = f"{url}/JSSResource/osxconfigurationprofiles/name/{encoded_name}"

    logger.debug("Requesting profile from: %s", full_url)

    req = urllib.request.Request(full_url)
    req.add_header("Accept", "application/json")
    req.add_header("Authorization", create_auth_header(user, password))

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read()
    except HTTPError as e:
        if e.code == 401:
            raise JamfError("Authentication failed. Check username and password.") from e
        elif e.code == 404:
            raise JamfError(f"Profile not found: {name}") from e
        else:
            raise JamfError(f"HTTP error {e.code}: {e.reason}") from e
    except URLError as e:
        raise JamfError(f"Failed to connect to JAMF server: {e.reason}") from e


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Download macOS configuration profiles from JAMF server.",
        epilog="Example: %(prog)s --server https://instance.jamfcloud.com --name 'Defender onboarding' --user admin",
    )
    parser.add_argument(
        "-s",
        "--server",
        type=str,
        required=True,
        help="JAMF server URL (e.g., https://instance.jamfcloud.com)",
    )
    parser.add_argument(
        "-n",
        "--name",
        type=str,
        required=True,
        help="macOS Configuration Profile name",
    )
    parser.add_argument(
        "-u",
        "--user",
        type=str,
        required=True,
        help="JAMF username",
    )
    parser.add_argument(
        "-p",
        "--password",
        type=str,
        default=None,
        help="JAMF password (will prompt if not provided)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )
    return parser.parse_args()


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, non-zero for error).
    """
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Prompt for password if not provided
    password = args.password
    if not password:
        try:
            password = getpass.getpass("JAMF Password: ")
        except (KeyboardInterrupt, EOFError):
            logger.error("Password input cancelled")
            return 1

    if not password:
        logger.error("Password is required")
        return 1

    try:
        content = query_jamf_profile(args.server, args.user, password, args.name)
    except JamfError as e:
        logger.error("Failed to download profile: %s", e)
        return 1

    try:
        data = json.loads(content)
        payloads = data["os_x_configuration_profile"]["general"]["payloads"]
        dom = xml.dom.minidom.parseString(payloads)
        print(dom.toprettyxml())
    except (json.JSONDecodeError, KeyError) as e:
        logger.error("Failed to parse JAMF response: %s", e)
        return 1
    except Exception as e:
        logger.error("Failed to format XML output: %s", e)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
