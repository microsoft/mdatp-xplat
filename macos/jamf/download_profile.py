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
from urllib.error import HTTPError, URLError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# HTTP status codes
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404


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
    credentials = f"{user}:{password}".encode()
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

    req = urllib.request.Request(full_url)  # noqa: S310
    req.add_header("Accept", "application/json")
    req.add_header("Authorization", create_auth_header(user, password))

    try:
        with urllib.request.urlopen(req, timeout=30) as response:  # noqa: S310
            return response.read()
    except HTTPError as e:
        if e.code == HTTP_UNAUTHORIZED:
            raise JamfError(name) from e
        if e.code == HTTP_NOT_FOUND:
            raise JamfError(name) from e
        raise JamfError(name) from e
    except URLError as e:
        raise JamfError(name) from e


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace.

    """
    parser = argparse.ArgumentParser(
        description="Download macOS configuration profiles from JAMF server.",
        epilog="Example: %(prog)s --server https://instance.jamfcloud.com --name test",
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
    """Run the main entry point.

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
            logger.exception("Password input cancelled")
            return 1

    if not password:
        logger.error("Password is required")
        return 1

    try:
        content = query_jamf_profile(args.server, args.user, password, args.name)
    except JamfError:
        logger.exception("Failed to download profile")
        return 1

    try:
        data = json.loads(content)
        payloads = data["os_x_configuration_profile"]["general"]["payloads"]
        xml.dom.minidom.parseString(payloads)  # noqa: S318
    except (json.JSONDecodeError, KeyError):
        logger.exception("Failed to parse JAMF response")
        return 1
    except Exception:
        logger.exception("Failed to format XML output")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
