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
from demo_framework.scenarios import VSCodeScenario, XcodeScenario, XcodeSimulatorScenario
from demo_framework.ui import print_error, print_info


def main():
    parser = argparse.ArgumentParser(
        description="MDE Performance Profiles Demo Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s vscode                          # Run VS Code build demo
    %(prog)s vscode --include-install        # Time npm install + compile in build phases
  %(prog)s vscode --repo ~/my-vscode       # Use custom repo path
  %(prog)s --help                          # Show all options
        """
    )

    parser.add_argument(
        "scenario",
        nargs="?",
        default=None,
        choices=["vscode", "xcode", "xcode-simulator"],
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

    parser.add_argument(
        "--include-install",
        action="store_true",
        help="For vscode scenario, include npm install in timed baseline/optimized build phases"
    )

    parser.add_argument(
        "--require-client-analyzer",
        action="store_true",
        help="Require XMDE Client Analyzer as a preflight prerequisite (prompt to install if missing)"
    )

    parser.add_argument(
        "--require-ghcp-cli",
        action="store_true",
        help="Require GitHub Copilot CLI as a preflight prerequisite (prompt to install if missing)"
    )

    parser.add_argument(
        "--hot-events-analysis",
        choices=["prompt", "python", "ghcp", "both"],
        default="prompt",
        help="Hot-event analysis mode for vscode scenario (default: prompt)"
    )

    parser.add_argument(
        "--profile-change-policy",
        choices=["prompt", "always", "never"],
        default="prompt",
        help="Consent policy for applying/removing profiles (default: prompt)"
    )

    args = parser.parse_args()

    if args.scenario is None:
        print_info("Select a demo scenario:")
        print("   1) vscode  - Microsoft VS Code build demo")
        print("   2) xcode   - FluentUI Apple Xcode build demo")
        print("   3) xcode-simulator - HelloDefender iOS simulator demo")
        choice = input("   Enter choice [1/2/3] (default: 1): ").strip()
        if choice == "2":
            args.scenario = "xcode"
        elif choice == "3":
            args.scenario = "xcode-simulator"
        else:
            args.scenario = "vscode"

    # Run preflight checks with scenario-aware requirements
    print_info("Checking prerequisites...")
    preflight = Preflight()
    require_node = args.scenario == "vscode"
    if not preflight.run_all(
        require_node=require_node,
        require_client_analyzer=args.require_client_analyzer,
        require_ghcp_cli=args.require_ghcp_cli,
    ):
        print_error("Preflight checks failed")
        return 1

    # Run selected scenario
    if args.scenario == "vscode":
        scenario = VSCodeScenario(
            repo_path=args.repo,
            include_install_in_build=args.include_install,
            hot_events_analysis_mode=args.hot_events_analysis,
            profile_change_policy=args.profile_change_policy,
        )
    elif args.scenario == "xcode":
        if args.include_install:
            print_info("--include-install is ignored for xcode scenario")
        if args.hot_events_analysis != "prompt":
            print_info("--hot-events-analysis is ignored for xcode scenario")
        scenario = XcodeScenario(
            repo_path=args.repo,
            profile_change_policy=args.profile_change_policy,
        )
    elif args.scenario == "xcode-simulator":
        if args.include_install:
            print_info("--include-install is ignored for xcode-simulator scenario")
        if args.hot_events_analysis != "prompt":
            print_info("--hot-events-analysis is ignored for xcode-simulator scenario")
        scenario = XcodeSimulatorScenario(
            repo_path=args.repo,
            profile_change_policy=args.profile_change_policy,
        )
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
