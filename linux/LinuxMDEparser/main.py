#!/usr/bin/env python3
"""Linux MDE Log Parser - Convert MDE logs to CSV format.

This script provides a command-line interface to convert various
Microsoft Defender for Endpoint log files to CSV format for analysis.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from json2excel import ConversionError, Json2Excel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        prog="LinuxMDEparser",
        description="Convert MDE log files to CSV format for analysis.",
        epilog="Example: %(prog)s wdavhistory --convert",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        title="Commands",
        help="Choose log file type to convert",
        required=True,
    )

    # wdavhistory sub menu
    wdav_parser = subparsers.add_parser(
        "wdavhistory",
        help="Convert wdavhistory file (found in /var/opt/microsoft/mdatp/)",
    )
    wdav_parser.add_argument(
        "--convert",
        action="store_true",
        help="Convert wdavhistory to wdavhistory.csv",
    )
    wdav_parser.add_argument(
        "--input",
        type=str,
        default="wdavhistory",
        help="Input file path (default: wdavhistory)",
    )
    wdav_parser.add_argument(
        "--output",
        type=str,
        default="wdavhistory.csv",
        help="Output file path (default: wdavhistory.csv)",
    )

    # real-time-protection.json sub menu
    rtp_parser = subparsers.add_parser(
        "real-time-protection",
        help="Convert real-time protection statistics",
    )
    rtp_parser.add_argument(
        "--convert",
        action="store_true",
        help="Convert real_time_protection.json to real_time_protection.csv",
    )
    rtp_parser.add_argument(
        "--input",
        type=str,
        default="real_time_protection.json",
        help="Input file path (default: real_time_protection.json)",
    )
    rtp_parser.add_argument(
        "--output",
        type=str,
        default="real_time_protection.csv",
        help="Output file path (default: real_time_protection.csv)",
    )

    return parser.parse_args()


def validate_path(path: Path, must_exist: bool = False, must_be_file: bool = False) -> Path:
    """Validate and sanitize a file path.

    Args:
        path: The path to validate.
        must_exist: If True, path must already exist.
        must_be_file: If True, path must be a regular file.

    Returns:
        The validated, resolved path.

    Raises:
        ValueError: If path validation fails.
    """
    # Convert to absolute path
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError) as e:
        raise ValueError(f"Invalid path: {path}") from e

    # Check for path traversal attempts
    path_str = str(resolved)
    if ".." in str(path):
        raise ValueError(f"Path traversal not allowed: {path}")

    # Check for shell metacharacters
    dangerous_chars = set(";|&$`(){}[]<>!")
    if any(c in path_str for c in dangerous_chars):
        raise ValueError(f"Path contains invalid characters: {path}")

    if must_exist and not resolved.exists():
        raise ValueError(f"Path does not exist: {resolved}")

    if must_be_file and must_exist and not resolved.is_file():
        raise ValueError(f"Path is not a file: {resolved}")

    return resolved


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, non-zero for error).
    """
    args = parse_args()

    if not args.convert:
        logger.error("Please specify --convert to perform the conversion")
        return 1

    # Validate input and output paths (CQ-PY-007)
    try:
        input_file = validate_path(Path(args.input), must_exist=True, must_be_file=True)
        output_file = validate_path(Path(args.output), must_exist=False)
    except ValueError as e:
        logger.error("Path validation failed: %s", e)
        return 1

    try:
        converter = Json2Excel(input_file, output_file)
        success = converter.convert()
        return 0 if success else 1
    except ConversionError as e:
        logger.error("Conversion failed: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
