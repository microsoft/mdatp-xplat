"""
Xcode build demo scenario.

Shows the impact of MDE performance profiles on a Swift/Xcode build process.
"""

from pathlib import Path
from typing import Optional
import subprocess

from .base import DemoScenario, ScenarioConfig
from ..ui import print_section, print_success, print_error, print_info


class XcodeScenario(DemoScenario):
    """Demo scenario for building microsoft/fluentui-apple."""

    def __init__(self, repo_path: Optional[Path] = None):
        config = ScenarioConfig(
            name="FluentUI Apple Xcode Build Demo",
            description="Demo showing MDE impact on Xcode/Swift builds",
            repo_url="https://github.com/microsoft/fluentui-apple.git",
            repo_path=repo_path or (Path.home() / "demo" / "fluentui-apple"),
            build_command="xcodebuild -workspace FluentUI.xcworkspace -scheme FluentUI-macOS -destination 'platform=macOS' clean build",
            profiles=["xcode", "xcode-ide-tree", "git"],
            estimated_duration_minutes=20,
        )
        super().__init__(config)
        self._register_phases()

    def _register_phases(self) -> None:
        self.orchestrator.add_phase("Setup and Preflight", self.setup)
        self.orchestrator.add_phase("Baseline Build (No Profiles)", self.build_baseline)
        self.orchestrator.add_phase("Apply Performance Profiles", self.apply_profiles)
        self.orchestrator.add_phase("Optimized Build (With Profiles)", self.build_optimized)
        self.orchestrator.add_phase("Analyze Impact", self.analyze_results)

    def _build_command(self) -> list:
        return [
            "xcodebuild",
            "-workspace",
            "FluentUI.xcworkspace",
            "-scheme",
            "FluentUI-macOS",
            "-destination",
            "platform=macOS",
            "clean",
            "build",
        ]

    def setup(self) -> bool:
        print_section("Setup")

        if not self.config.repo_path.exists():
            print_info(f"Cloning {self.config.repo_url}...")
            try:
                subprocess.run(
                    ["git", "clone", "--depth", "1", self.config.repo_url, str(self.config.repo_path)],
                    timeout=300,
                    check=True,
                )
                print_success(f"Cloned to {self.config.repo_path}")
            except subprocess.CalledProcessError as e:
                print_error(f"Failed to clone: {e}")
                return False

        if not (self.config.repo_path / "FluentUI.xcworkspace").exists():
            print_error("Expected FluentUI.xcworkspace was not found in repo")
            return False

        print_success("Repository is ready")
        return True

    def build_baseline(self) -> bool:
        print_section("Baseline Build (No Profiles)")
        print_info("Building fluentui-apple without performance profiles...")

        for profile in self.config.profiles:
            try:
                subprocess.run(
                    ["sudo", "mdatp", "performance-profiles", "remove", "--name", profile],
                    capture_output=True,
                    timeout=10,
                )
            except Exception:
                pass

        try:
            result = subprocess.run(self._build_command(), cwd=self.config.repo_path, timeout=1800)
            if result.returncode != 0:
                print_error("Baseline build failed")
                return False
            print_success("Baseline build completed")
            return True
        except subprocess.TimeoutExpired:
            print_error("Build timed out")
            return False

    def apply_profiles(self) -> bool:
        print_section("Applying Profiles")

        for profile in self.config.profiles:
            print_info(f"Applying profile: {profile}...")
            try:
                result = subprocess.run(
                    ["sudo", "mdatp", "performance-profiles", "add", "--name", profile],
                    capture_output=True,
                    timeout=10,
                    text=True,
                )
                if result.returncode != 0:
                    print_info(f"Profile {profile} may already be applied or not available")
                else:
                    print_success(f"Applied: {profile}")
            except Exception as e:
                print_info(f"Could not apply {profile}: {e}")

        return True

    def build_optimized(self) -> bool:
        print_section("Optimized Build (With Profiles)")
        print_info("Building fluentui-apple with performance profiles...")

        try:
            result = subprocess.run(self._build_command(), cwd=self.config.repo_path, timeout=1800)
            if result.returncode != 0:
                print_error("Optimized build failed")
                return False
            print_success("Optimized build completed")
            return True
        except subprocess.TimeoutExpired:
            print_error("Build timed out")
            return False

    def analyze_results(self) -> bool:
        print_section("Analysis")
        print_info("Comparing baseline vs. optimized build times...")
        print_info("Impact data would be displayed here (CPU usage, build time, I/O patterns)")
        print_success("Analysis complete")
        return True
