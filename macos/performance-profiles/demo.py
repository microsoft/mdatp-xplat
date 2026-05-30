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
from demo_framework.scenarios import VSCodeScenario, XcodeScenario
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
        default=None,
        choices=["vscode", "xcode"],
        help="Demo scenario to run (if omitted, you'll be prompted)"
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

    if args.scenario is None:
        print_info("Select a demo scenario:")
        print("   1) vscode  - Microsoft VS Code build demo")
        print("   2) xcode   - FluentUI Apple Xcode build demo")
        choice = input("   Enter choice [1/2] (default: 1): ").strip()
        args.scenario = "xcode" if choice == "2" else "vscode"

    # Run preflight checks with scenario-aware requirements
    print_info("Checking prerequisites...")
    preflight = Preflight()
    require_node = args.scenario == "vscode"
    if not preflight.run_all(require_node=require_node):
        print_error("Preflight checks failed")
        return 1

    # Run selected scenario
    if args.scenario == "vscode":
        scenario = VSCodeScenario(repo_path=args.repo)
    elif args.scenario == "xcode":
        scenario = XcodeScenario(repo_path=args.repo)
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
