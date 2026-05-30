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
            build_command="swift build -c release",
            profiles=["xcode", "xcode-ide-tree", "git"],
            estimated_duration_minutes=20,
        )
        super().__init__(config)
        self.baseline_repo_path = self.config.repo_path.parent / f"{self.config.repo_path.name}-baseline"
        self.optimized_repo_path = self.config.repo_path.parent / f"{self.config.repo_path.name}-optimized"
        self._register_phases()

    def _register_phases(self) -> None:
        self.orchestrator.add_phase("Setup and Preflight", self.setup)
        self.orchestrator.add_phase("Baseline Build (No Profiles)", self.build_baseline)
        self.orchestrator.add_phase("Apply Performance Profiles", self.apply_profiles)
        self.orchestrator.add_phase("Optimized Build (With Profiles)", self.build_optimized)
        self.orchestrator.add_phase("Analyze Impact", self.analyze_results)

    def _build_command(self) -> list:
        return ["swift", "build", "-c", "release"]

    def _fresh_clone(self, target: Path) -> bool:
        """Clone a fresh copy of fluentui-apple for a timed phase."""
        try:
            if target.exists():
                subprocess.run(["rm", "-rf", str(target)], timeout=60, check=True)

            subprocess.run(
                ["git", "clone", "--depth", "1", self.config.repo_url, str(target)],
                timeout=600,
                check=True,
            )

            if not (target / "Package.swift").exists():
                print_error("Expected Package.swift was not found in cloned repo")
                return False
            return True
        except subprocess.CalledProcessError as e:
            print_error(f"Failed to clone repository: {e}")
            return False

    def setup(self) -> bool:
        print_section("Setup")

        self.config.repo_path.parent.mkdir(parents=True, exist_ok=True)

        # Clone is part of measured phases; setup validates required tooling only.
        git_check = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=10)
        if git_check.returncode != 0:
            print_error("git is required but was not found")
            return False

        swift_check = subprocess.run(["swift", "--version"], capture_output=True, text=True, timeout=10)
        if swift_check.returncode != 0:
            print_error("swift is required but was not found")
            return False

        print_success("Tooling is ready (git + swift)")
        print_info("Clone is included in baseline/optimized timed phases to show git profile impact")
        return True

    def build_baseline(self) -> bool:
        print_section("Baseline Build (No Profiles)")
        print_info("Cloning and building fluentui-apple without performance profiles...")

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
            print_info(f"Fresh clone for baseline: {self.baseline_repo_path}")
            if not self._fresh_clone(self.baseline_repo_path):
                return False

            result = subprocess.run(self._build_command(), cwd=self.baseline_repo_path, timeout=1800)
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
                    ["sudo", "mdatp", "performance-profiles", "apply", "--name", profile],
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
        print_info("Cloning and building fluentui-apple with performance profiles...")

        try:
            print_info(f"Fresh clone for optimized run: {self.optimized_repo_path}")
            if not self._fresh_clone(self.optimized_repo_path):
                return False

            result = subprocess.run(self._build_command(), cwd=self.optimized_repo_path, timeout=1800)
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
        baseline = None
        optimized = None
        for result in self.orchestrator.results:
            if result.name == "Baseline Build (No Profiles)":
                baseline = result.duration_seconds
            if result.name == "Optimized Build (With Profiles)":
                optimized = result.duration_seconds

        print_info("Comparison summary:")
        if baseline is not None:
            print(f"   Baseline (clone + build):  {baseline:.1f}s")
        if optimized is not None:
            print(f"   Optimized (clone + build): {optimized:.1f}s")
        if baseline and optimized:
            saved = baseline - optimized
            speedup = ((saved / baseline) * 100) if baseline > 0 else 0
            print(f"   Speedup:                   {speedup:.0f}% ({saved:.1f}s saved)")
        print_success("Analysis complete")
        return True
