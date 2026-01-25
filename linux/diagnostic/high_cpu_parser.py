#!/usr/bin/env python3
"""Parse MDE scan measures to identify high CPU usage processes.

This script processes JSON output from MDE diagnostics to identify
processes that trigger the most file scans.

Usage:
    mdatp diagnostic real-time-protection-statistics --output json | python high_cpu_parser.py [--group] [--top N]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class ParseError(Exception):
    """Exception raised for parsing errors."""

    pass


def get_scan_count(entry: dict[str, Any]) -> int:
    """Extract the scan count from an entry, handling different key names.

    Args:
        entry: Dictionary containing scan data.

    Returns:
        The total files scanned count.
    """
    if "totalFilesScanned" in entry:
        return int(entry["totalFilesScanned"])
    elif "total_files_scanned" in entry:
        return int(entry["total_files_scanned"])
    else:
        return 0


def process_grouped(
    vals: list[dict[str, Any]], top: int
) -> list[tuple[str, int, str]]:
    """Process and group scan data by process name.

    Args:
        vals: List of scan entries.
        top: Maximum number of results to return.

    Returns:
        List of tuples (name, count, path) sorted by count descending.
    """
    groups: dict[str, list[int | str]] = {}

    for v in vals:
        name = v.get("name", "unknown")
        path = v.get("path", "")
        cnt = get_scan_count(v)

        if name not in groups:
            groups[name] = [cnt, path]
        else:
            groups[name][0] = int(groups[name][0]) + cnt

    sorted_names = sorted(groups.keys(), key=lambda k: groups[k][0], reverse=True)
    return [(name, groups[name][0], groups[name][1]) for name in sorted_names[:top]]


def process_ungrouped(
    vals: list[dict[str, Any]], top: int
) -> list[dict[str, Any]]:
    """Process scan data without grouping.

    Args:
        vals: List of scan entries.
        top: Maximum number of results to return.

    Returns:
        List of entries sorted by scan count descending.
    """
    sorted_vals = sorted(vals, key=lambda k: get_scan_count(k), reverse=True)
    return [v for v in sorted_vals[:top] if get_scan_count(v) != 0]


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Process MDE scan measures to identify high CPU usage processes.",
        epilog="Example: mdatp diagnostic real-time-protection-statistics --output json | python %(prog)s --group --top 10",
    )
    parser.add_argument(
        "--group",
        action="store_true",
        help="Group results by process name",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        help="Limit the number of results (default: all)",
    )
    return parser.parse_args()


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, non-zero for error).
    """
    args = parse_args()

    # Input validation (CQ-PY-007)
    if args.top is not None:
        if args.top <= 0:
            logger.error("--top must be a positive integer, got: %d", args.top)
            return 1
        top = args.top
    else:
        top = sys.maxsize

    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse JSON input: %s", e)
        return 1

    # Validate input data structure
    if not isinstance(data, dict):
        logger.error("Invalid input: expected JSON object, got %s", type(data).__name__)
        return 1

    if "counters" not in data:
        logger.error("Invalid input: missing 'counters' key in JSON data")
        return 1

    vals = data["counters"]

    if not isinstance(vals, list):
        logger.error("Invalid input: 'counters' must be a list")
        return 1

    if args.group:
        results = process_grouped(vals, top)
        for name, count, _ in results:
            print(f"{name}\t{count}")
    else:
        results = process_ungrouped(vals, top)
        for v in results:
            cnt_key = "totalFilesScanned" if "totalFilesScanned" in v else "total_files_scanned"
            print(f"{v.get('id', 'N/A')}\t{v.get('name', 'unknown')}\t{v[cnt_key]}\t{v.get('path', '')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
