#!/usr/bin/env python3
"""Analyze auditd logs for MDE-related syscalls.

This script parses audit log files to identify which processes are
triggering MDE auditd rules, helping diagnose performance issues.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from collections import Counter
from pathlib import Path
from typing import TextIO

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Default audit log path on Linux
DEFAULT_AUDIT_PATH = "/var/log/audit/audit.log"

# Regex pattern to extract exe= field from audit log lines
EXE_PATTERN = re.compile(r'\bexe="?([^"\s]+)"?')


class AuditAnalyzerError(Exception):
    """Exception raised for audit analyzer errors."""

    pass


def extract_executable(line: str) -> str | None:
    """Extract the executable path from an audit log line.

    Args:
        line: A single line from the audit log.

    Returns:
        The executable path if found, None otherwise.
    """
    match = EXE_PATTERN.search(line)
    if match:
        return match.group(1)
    return None


def is_mdatp_syscall_line(line: str) -> bool:
    """Check if a line is an MDE-related SYSCALL audit entry.

    Args:
        line: A single line from the audit log.

    Returns:
        True if the line matches MDE audit criteria.
    """
    return 'key="mdatp"' in line and "type=SYSCALL" in line


def analyze_audit_file(audit_file: TextIO) -> Counter[str]:
    """Analyze an audit log file and count executables.

    Args:
        audit_file: File object for the audit log.

    Returns:
        Counter of executable paths.
    """
    executables: list[str] = []

    for line in audit_file:
        if is_mdatp_syscall_line(line):
            exe = extract_executable(line)
            if exe:
                executables.append(exe)

    return Counter(executables)


def format_results(counts: Counter[str], top: int | None = None) -> str:
    """Format the analysis results as a table.

    Args:
        counts: Counter of executable paths.
        top: Maximum number of results to show (None for all).

    Returns:
        Formatted string table.
    """
    if not counts:
        return "No MDE-related audit entries found."

    # Get sorted items
    items = counts.most_common(top)

    # Calculate column widths
    max_proc_len = max(len(proc) for proc, _ in items)
    max_proc_len = max(max_proc_len, len("Process"))

    # Build table
    lines = []
    lines.append(f"{'Process':<{max_proc_len}}  {'Count':>10}")
    lines.append("-" * (max_proc_len + 12))

    for process, count in items:
        lines.append(f"{process:<{max_proc_len}}  {count:>10}")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Analyze auditd logs for MDE-related syscalls.",
        epilog="Example: %(prog)s --file /var/log/audit/audit.log --top 20",
    )
    parser.add_argument(
        "-f",
        "--file",
        type=str,
        default=DEFAULT_AUDIT_PATH,
        help=f"Path to audit log file (default: {DEFAULT_AUDIT_PATH})",
    )
    parser.add_argument(
        "-t",
        "--top",
        type=int,
        default=None,
        help="Limit the number of results (default: all)",
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

    audit_path = Path(args.file)

    if not audit_path.exists():
        logger.error("Audit file not found: %s", audit_path)
        return 1

    if not audit_path.is_file():
        logger.error("Path is not a file: %s", audit_path)
        return 1

    logger.debug("Analyzing audit file: %s", audit_path)

    try:
        with open(audit_path, encoding="utf-8", errors="replace") as audit_file:
            counts = analyze_audit_file(audit_file)
    except PermissionError:
        logger.error(
            "Permission denied reading %s. Try running with sudo.", audit_path
        )
        return 1
    except OSError as e:
        logger.error("Failed to read audit file: %s", e)
        return 1

    output = format_results(counts, args.top)
    print(output)

    logger.debug("Found %d unique executables in %d total entries", len(counts), sum(counts.values()))

    return 0


if __name__ == "__main__":
    sys.exit(main())
