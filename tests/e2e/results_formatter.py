#!/usr/bin/env python3
"""results_formatter.py.

Formats test results into markdown summary tables and failure logs.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class TestResult:
    """Single test result for a distro."""

    distro: str
    version: str
    install_passed: bool
    onboarding_passed: bool
    uninstall_passed: bool
    duration_seconds: float
    failure_reason: Optional[str] = None
    timestamp: Optional[str] = None
    logs: Optional[Dict[str, str]] = None  # filename -> content


class ResultsFormatter:
    """Format and save test results."""

    def __init__(self, output_dir: str = "results"):
        """Initialize formatter with output directory."""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.results: List[TestResult] = []

    def add_result(self, result: TestResult) -> None:
        """Add a test result."""
        self.results.append(result)

    def _escape_markdown(self, text: str) -> str:
        """Escape special markdown characters."""
        return text.replace("|", "\\|").replace("\n", " ")

    def generate_summary_markdown(self) -> str:
        """Generate markdown summary table."""
        if not self.results:
            return "# E2E Test Results\n\nNo results to report.\n"

        lines = [
            "# E2E Test Results\n",
            f"Generated: {datetime.now().isoformat()}\n",
            f"Total Tests: {len(self.results)}\n",
            f"Passed: {sum(1 for r in self.results if r.install_passed)}\n",
            f"Failed: {sum(1 for r in self.results if not r.install_passed)}\n",
            "",
            "## Summary",
            "",
            "| Distro | Version | Install | Onboard | Uninstall | Duration | Status |",
            "|--------|---------|---------|---------|-----------|----------|--------|",
        ]

        for result in sorted(self.results, key=lambda x: (x.distro, x.version)):
            install_icon = "✅" if result.install_passed else "❌"
            onboard_icon = "✅" if result.onboarding_passed else "❌"
            uninstall_icon = "✅" if result.uninstall_passed else "❌"

            if not result.install_passed:
                status = f"FAILED: {self._escape_markdown(result.failure_reason or 'Unknown')}"
            elif not result.onboarding_passed:
                status = "ONBOARDING FAILED"
            elif not result.uninstall_passed:
                status = "UNINSTALL FAILED"
            else:
                status = "PASSED"

            duration_str = f"{result.duration_seconds:.1f}s"

            lines.append(
                f"| {result.distro} | {result.version} | {install_icon} | "
                f"{onboard_icon} | {uninstall_icon} | {duration_str} | {status} |"
            )

        # Add failure details section
        failures = [r for r in self.results if not r.install_passed or not r.onboarding_passed]
        if failures:
            lines.extend([
                "",
                "## Failures",
                "",
            ])
            for result in failures:
                lines.append(f"### {result.distro} {result.version}")
                if result.failure_reason:
                    lines.append(f"\n**Reason:** {self._escape_markdown(result.failure_reason)}\n")
                if result.timestamp:
                    lines.append(f"**Time:** {result.timestamp}\n")
                lines.append("**Log Files:** See `failures/` directory\n")
                lines.append("")

        lines.append("\n")
        return "\n".join(lines)

    def save_summary(self, filename: str = "summary.md") -> Path:
        """Save markdown summary to file."""
        summary_path = self.output_dir / filename
        summary_content = self.generate_summary_markdown()
        summary_path.write_text(summary_content)
        return summary_path

    def save_failure_logs(self, result: TestResult) -> None:
        """Save failure logs for a test."""
        if not result.failure_reason and result.install_passed:
            return  # No failure to log

        failures_dir = self.output_dir / "failures"
        failures_dir.mkdir(parents=True, exist_ok=True)

        # Create filename with distro, version, and timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_distro = result.distro.replace(".", "_").replace(" ", "_")
        safe_version = result.version.replace(".", "_")

        log_filename = f"{safe_distro}-{safe_version}-{timestamp}.log"
        log_path = failures_dir / log_filename

        # Write combined log
        log_lines = [
            "Test Failure Log",
            "================",
            "",
            f"Distro: {result.distro}",
            f"Version: {result.version}",
            f"Timestamp: {result.timestamp}",
            f"Duration: {result.duration_seconds:.1f}s",
            "",
            "Failure Reason:",
            "---------------",
            f"{result.failure_reason or 'Unknown'}",
            "",
        ]

        # Add captured logs
        if result.logs:
            log_lines.extend([
                "Captured Logs:",
                "==============",
                "",
            ])
            for log_name, log_content in sorted(result.logs.items()):
                log_lines.extend([
                    f"### {log_name}",
                    "```",
                    log_content,
                    "```",
                    "",
                ])

        log_path.write_text("\n".join(log_lines))

    def save_json_results(self, filename: str = "results.json") -> Path:
        """Save detailed results as JSON."""
        results_path = self.output_dir / filename

        results_data = {
            "generated": datetime.now().isoformat(),
            "summary": {
                "total": len(self.results),
                "passed": sum(1 for r in self.results if r.install_passed),
                "failed": sum(1 for r in self.results if not r.install_passed),
            },
            "results": [
                {
                    "distro": r.distro,
                    "version": r.version,
                    "install_passed": r.install_passed,
                    "onboarding_passed": r.onboarding_passed,
                    "uninstall_passed": r.uninstall_passed,
                    "duration_seconds": r.duration_seconds,
                    "failure_reason": r.failure_reason,
                    "timestamp": r.timestamp,
                    "has_logs": bool(r.logs),
                }
                for r in self.results
            ],
        }

        results_path.write_text(json.dumps(results_data, indent=2))
        return results_path

    def save_all(self, base_dir: str = "results") -> Dict[str, Path]:
        """Save all result formats."""
        self.output_dir = Path(base_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Save failure logs first
        for result in self.results:
            self.save_failure_logs(result)

        # Save summaries
        summary_path = self.save_summary()
        json_path = self.save_json_results()

        return {
            "summary": summary_path,
            "json": json_path,
            "failures_dir": self.output_dir / "failures",
        }


def main():
    """CLI for testing results formatter."""
    # Create sample results
    formatter = ResultsFormatter()

    formatter.add_result(TestResult(
        distro="ubuntu",
        version="22.04",
        install_passed=True,
        onboarding_passed=True,
        uninstall_passed=True,
        duration_seconds=145.2,
        timestamp=datetime.now().isoformat(),
    ))

    formatter.add_result(TestResult(
        distro="ubuntu",
        version="24.04",
        install_passed=True,
        onboarding_passed=True,
        uninstall_passed=False,
        duration_seconds=156.8,
        failure_reason="Uninstall failed: package removal error",
        timestamp=datetime.now().isoformat(),
        logs={"installer.log": "Sample installer output"},
    ))

    formatter.add_result(TestResult(
        distro="rocky",
        version="9",
        install_passed=False,
        onboarding_passed=False,
        uninstall_passed=False,
        duration_seconds=89.5,
        failure_reason="Installation failed: repo setup error",
        timestamp=datetime.now().isoformat(),
        logs={
            "installer.log": "Installation failed at repo configuration",
            "system.log": "Repo error details here",
        },
    ))

    # Save results
    formatter.save_all()


    # Print summary


if __name__ == "__main__":
    main()
