#!/usr/bin/env python3
"""
MDE Performance Profiles Demo - Main Entry Point

Run a demo scenario showing how MDE performance profiles impact build times.

Usage:
    python demo.py vscode              # Run VS Code demo
    python demo.py --help              # Show options
"""

import sys
import argparse
from pathlib import Path

from demo_framework.preflight import Preflight
from demo_framework.scenarios import VSCodeScenario
from demo_framework.ui import print_error, print_info


def main():
    parser = argparse.ArgumentParser(
        description="MDE Performance Profiles Demo Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s vscode                          # Run VS Code build demo
  %(prog)s vscode --repo ~/my-vscode       # Use custom repo path
  %(prog)s --help                          # Show all options
        """
    )

    parser.add_argument(
        "scenario",
        nargs="?",
        default="vscode",
        choices=["vscode", "xcode"],
        help="Demo scenario to run (default: vscode)"
    )

    parser.add_argument(
        "--repo",
        type=Path,
        help="Override repo path"
    )

    parser.add_argument(
        "--resume-from",
        type=int,
        help="Resume from phase N (0-indexed)"
    )

    args = parser.parse_args()

    # Run preflight checks
    print_info("Checking prerequisites...")
    preflight = Preflight()
    if not preflight.run_all():
        print_error("Preflight checks failed")
        return 1

    # Run selected scenario
    if args.scenario == "vscode":
        scenario = VSCodeScenario(repo_path=args.repo)
    else:
        print_error(f"Unknown scenario: {args.scenario}")
        return 1

    try:
        success = scenario.run(resume_from=args.resume_from)
        summary = scenario.get_summary()
        
        print_info(f"\n{'=' * 70}")
        print_info(f"Demo: {summary['name']}")
        print_info(f"Phases completed: {summary['completed']}/{summary['total_phases']}")
        print_info(f"Total duration: {summary['total_duration']:.1f}s")
        print_info(f"{'=' * 70}\n")
        
        return 0 if success else 1
    except KeyboardInterrupt:
        print_error("Demo interrupted by user")
        return 130


if __name__ == "__main__":
    sys.exit(main())
