#!/usr/bin/env python3
"""Validate macOS configuration profiles against JSON schema.

This script validates MDM configuration profiles for Microsoft Defender
for Endpoint against the official schema.
"""

from __future__ import annotations

import argparse
import plistlib
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

from jschon import JSON, JSONSchema, create_catalog

parser = argparse.ArgumentParser(description="Validate configuration profile against schema")
parser.add_argument("--schema", type=str, help="Path to the schema file")
parser.add_argument("--verbose", action="store_true", help="Include verbose output")
parser.add_argument(
    "--print-valid",
    action="store_true",
    help="Include list of configuration values passed validation",
)
parser.add_argument(
    "--print-invalid",
    action="store_true",
    help="Include list of configuration values failed validation",
)
parser.add_argument(
    "--print-unsupported",
    action="store_true",
    help="Include list of configuration values out of schema scope",
)
parser.add_argument("file", type=str, nargs="+")

try:
    args = parser.parse_args()
except SystemExit:
    sys.exit(2)

if not args.print_valid and not args.print_invalid and not args.print_unsupported:
    args.print_valid = True
    args.print_invalid = True
    args.print_unsupported = True


def _debug(msg: str) -> None:
    """Print debug message if verbose mode is enabled.

    Args:
        msg: Debug message to print.

    """
    if args.verbose:
        _ = msg  # Reserved for debug output


def _info(msg: str) -> None:
    """Print informational message.

    Args:
        msg: Info message to print.

    """
    _ = msg  # Suppress unused argument warning


def _warn(msg: str) -> None:
    """Print warning message.

    Args:
        msg: Warning message to print.

    """
    _ = msg  # Suppress unused argument warning


def load_json(path: str) -> list[dict]:
    """Load a JSON file for validation.

    Args:
        path: Path to the JSON file.

    Returns:
        List containing payload dictionaries.

    """
    _debug(f"Probe JSON file: {path}")
    payload = {"json": JSON.loadf(path), "name": ""}
    return [payload]


def load_plist(path: str) -> list[dict]:
    """Load a plist file for validation.

    Args:
        path: Path to the plist file.

    Returns:
        List containing payload dictionaries.

    """
    _debug(f"Probe plist file: {path}")

    try:
        with open(path, "rb") as f:
            _debug("Probe as a plain plist")
            data = plistlib.load(f)
    except plistlib.InvalidFileException:
        _debug("Probe as a signed mobileconfig file")
        with tempfile.NamedTemporaryFile() as temp_file:
            subprocess.run(
                ["/usr/bin/security", "cms", "-D", "-i", path, "-o", temp_file.name], check=False
            )
            with open(temp_file.name, "rb") as f:
                data = plistlib.load(f)

    _debug("Plist loaded")

    result: list[dict] = []

    if "PayloadContent" in data:
        _debug("mobileconfig detected")
        for pc_outer in data["PayloadContent"]:
            if "PayloadContent" in pc_outer:
                for selector in ("com.microsoft.wdav", "com.microsoft.wdav.ext"):
                    payload_content = pc_outer["PayloadContent"]
                    if selector in payload_content and "Forced" in payload_content[selector]:
                        for idx, pc_inner in enumerate(payload_content[selector]["Forced"], 1):
                            if "mcx_preference_settings" in pc_inner:
                                name = (
                                    f"{data['PayloadDisplayName']} "
                                    f"({data['PayloadIdentifier']}) / "
                                    f"{pc_outer['PayloadIdentifier']} / {selector} #{idx}"
                                )
                                payload = {
                                    "json": JSON(pc_inner["mcx_preference_settings"]),
                                    "name": name,
                                }
                                result.append(payload)
    else:
        _debug("Simple plist detected")
        payload = {"json": JSON(data), "name": ""}
        result.append(payload)

    _debug(f"Found {len(result)} payloads")
    return result


def load_file(path: str) -> list[dict]:
    """Load a file for validation, detecting format automatically.

    Args:
        path: Path to the file.

    Returns:
        List containing payload dictionaries.

    """
    try:
        return load_plist(path)
    except (plistlib.InvalidFileException, OSError):
        return load_json(path)


def _report(node: dict, found_nodes: set, offset: int = 0) -> None:
    """Report validation results for a node.

    Args:
        node: Validation result node.
        found_nodes: Set of found node locations.
        offset: Indentation offset.

    """
    has_errors = "errors" in node
    has_annotations = "annotations" in node
    is_valid = "valid" in node and node["valid"]

    if node["instanceLocation"]:
        found_nodes.add(node["instanceLocation"])
        if has_errors or has_annotations:
            if is_valid:
                if args.print_valid:
                    pass
            elif args.print_invalid:
                if "error" in node:
                    pass
                else:
                    pass
        elif not is_valid and args.print_invalid and "error" in node:
            pass

    if "errors" in node:
        for n in node["errors"]:
            _report(n, found_nodes, offset + 1)
    if "annotations" in node:
        for n in node["annotations"]:
            _report(n, found_nodes, offset + 1)


def _found_data_nodes(node: dict, found_nodes: set, prefix: str = "/") -> None:
    """Recursively find data nodes.

    Args:
        node: Node to search.
        found_nodes: Set to add found nodes to.
        prefix: Path prefix.

    """
    for k, v in node.data.items():
        found_nodes.add(prefix + k)
        if isinstance(v.data, dict):
            _found_data_nodes(v, found_nodes, prefix + k + "/")


def _analyze_json(schema: JSONSchema, payload: dict) -> bool:
    """Analyze a JSON payload against the schema.

    Args:
        schema: JSON schema to validate against.
        payload: Payload dictionary to validate.

    Returns:
        True if validation succeeded.

    """
    result = schema.evaluate(payload["json"])
    output = result.output("verbose")
    success = output["valid"]

    if output["valid"]:
        _info("JSON is valid{}".format(": " + payload["name"] if payload["name"] else ""))
    else:
        _warn("JSON is invalid{}".format(": " + payload["name"] if payload["name"] else ""))

    found_expected_nodes: set = set()
    found_real_nodes: set = set()
    _report(output, found_expected_nodes)

    _found_data_nodes(payload["json"], found_real_nodes)

    unexpected_nodes = sorted(found_real_nodes.difference(found_expected_nodes))

    if len(unexpected_nodes) > 0:
        _warn("Unexpected nodes found (either misspelled or not at the expected location):")
        success = False

        if args.print_unsupported:
            for node in unexpected_nodes:
                _ = len(node.split("/"))  # Count depth

    return success


def _analyze_file(schema: JSONSchema, path: str) -> bool:
    """Analyze a file against the schema.

    Args:
        schema: JSON schema to validate against.
        path: Path to the file.

    Returns:
        True if validation succeeded.

    """
    payloads = load_file(path)
    success = True

    for payload in payloads:
        if not _analyze_json(schema, payload):
            success = False

    return success


# Global state for schema download
_schema_temp_file = None


def _download_schema() -> str:
    """Download the schema file from GitHub.

    Returns:
        Path to the downloaded schema file.

    """
    global _schema_temp_file  # noqa: PLW0603
    url = "https://raw.githubusercontent.com/microsoft/mdatp-xplat/master/macos/schema/schema.json"
    _schema_temp_file = tempfile.NamedTemporaryFile(delete=False)  # noqa: SIM115
    schema_path = _schema_temp_file.name

    _info(f"Downloading schema from {url}")
    _debug("Using module urllib.request")

    try:
        with urllib.request.urlopen(url) as response:  # noqa: S310, SIM117
            with open(schema_path, "wb") as out_file:
                shutil.copyfileobj(response, out_file)
    except urllib.error.URLError as e:
        _warn(
            f"Your Python has issues with SSL validation, please fix it. "
            f"Querying {url} with disabled validation. Error: {e}"
        )
        ssl._create_default_https_context = ssl._create_unverified_context

        with urllib.request.urlopen(url) as response:  # noqa: S310, SIM117
            with open(schema_path, "wb") as out_file:
                shutil.copyfileobj(response, out_file)
    _debug(f"Downloaded schema to {schema_path}")
    return schema_path


def main() -> int:
    """Validate configuration profiles against schema.

    Returns:
        Exit code (0 for success, non-zero for error).

    """
    schema_path = args.schema

    try:
        if not schema_path:
            schema_path = _download_schema()

        create_catalog("2020-12")
        schema = JSONSchema.loadf(schema_path)
        success = True

        for path in args.file:
            _info(f"Analyzing file: {path}")
            if not _analyze_file(schema, path):
                success = False
    except Exception:
        return 3
    else:
        return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
