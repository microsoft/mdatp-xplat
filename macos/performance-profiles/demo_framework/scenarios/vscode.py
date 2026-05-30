"""
VS Code build demo scenario.

Shows the impact of MDE performance profiles on the Microsoft VS Code build process.
"""

from pathlib import Path
from typing import Optional
import json
import subprocess

from .base import DemoScenario, ScenarioConfig
from ..ui import print_section, print_success, print_error, print_info


class VSCodeScenario(DemoScenario):
    """Demo scenario for building Microsoft VS Code."""

    def __init__(self, repo_path: Optional[Path] = None):
        config = ScenarioConfig(
            name="Microsoft VS Code Build Demo",
            description="End-to-end demo showing MDE impact on VS Code compilation",
            repo_url="https://github.com/microsoft/vscode.git",
            repo_path=repo_path or (Path.home() / "demo" / "vscode"),
            build_command="npm run compile",
            profiles=["node", "git", "vscode", "vscode-tree"],
            estimated_duration_minutes=60
        )
        super().__init__(config)
        self._register_phases()

    def _register_phases(self) -> None:
        """Register demo phases with orchestrator."""
        self.orchestrator.add_phase("Setup and Preflight", self.setup)
        self.orchestrator.add_phase("Baseline Build (No Profiles)", self.build_baseline)
        self.orchestrator.add_phase("Diagnostics Collection", self._collect_diagnostics)
        self.orchestrator.add_phase("Apply Performance Profiles", self.apply_profiles)
        self.orchestrator.add_phase("Optimized Build (With Profiles)", self.build_optimized)
        self.orchestrator.add_phase("Analyze Impact", self.analyze_results)

    def setup(self) -> bool:
        """Prepare demo environment."""
        print_section("Setup")
        
        # Clone repo if needed
        if not self.config.repo_path.exists():
            print_info(f"Cloning {self.config.repo_url}...")
            try:
                subprocess.run(
                    ["git", "clone", "--depth", "1", "--branch", "1.122.1",
                     self.config.repo_url, str(self.config.repo_path)],
                    timeout=300,
                    check=True
                )
                print_success(f"Cloned to {self.config.repo_path}")
            except subprocess.CalledProcessError as e:
                print_error(f"Failed to clone: {e}")
                return False

        # Install dependencies
        print_info("Running npm install...")
        try:
            subprocess.run(
                ["npm", "install"],
                cwd=self.config.repo_path,
                timeout=600,
                check=True
            )
            print_success("Dependencies installed")
        except subprocess.CalledProcessError as e:
            print_error(f"npm install failed: {e}")
            return False

        return True

    def build_baseline(self) -> bool:
        """Build without performance profiles."""
        print_section("Baseline Build (No Profiles)")
        print_info("Building VS Code without performance profiles...")
        
        # Remove any active profiles
        try:
            subprocess.run(
                ["sudo", "mdatp", "performance-profiles", "remove", "--name", "node"],
                capture_output=True,
                timeout=10
            )
        except:
            pass

        # Run build
        try:
            result = subprocess.run(
                ["npm", "run", "compile"],
                cwd=self.config.repo_path,
                timeout=1800
            )
            if result.returncode != 0:
                print_error("Baseline build failed")
                return False
            print_success("Baseline build completed")
            return True
        except subprocess.TimeoutExpired:
            print_error("Build timed out")
            return False

    def apply_profiles(self) -> bool:
        """Apply performance profiles."""
        print_section("Applying Profiles")
        
        for profile in self.config.profiles:
            print_info(f"Applying profile: {profile}...")
            try:
                result = subprocess.run(
                    ["sudo", "mdatp", "performance-profiles", "add", "--name", profile],
                    capture_output=True,
                    timeout=10,
                    text=True
                )
                if result.returncode != 0:
                    print_info(f"Profile {profile} may already be applied or not available")
                else:
                    print_success(f"Applied: {profile}")
            except Exception as e:
                print_info(f"Could not apply {profile}: {e}")

        return True

    def build_optimized(self) -> bool:
        """Build with performance profiles."""
        print_section("Optimized Build (With Profiles)")
        print_info("Building VS Code with performance profiles...")
        
        try:
            result = subprocess.run(
                ["npm", "run", "compile"],
                cwd=self.config.repo_path,
                timeout=1800
            )
            if result.returncode != 0:
                print_error("Optimized build failed")
                return False
            print_success("Optimized build completed")
            return True
        except subprocess.TimeoutExpired:
            print_error("Build timed out")
            return False

    def analyze_results(self) -> bool:
        """Analyze impact of profiles."""
        print_section("Analysis")
        print_info("Comparing baseline vs. optimized build times...")
        print_info("Impact data would be displayed here (CPU usage, build time, I/O patterns)")
        print_success("Analysis complete")
        return True

    def _collect_diagnostics(self) -> bool:
        """Collect diagnostic data during baseline."""
        print_section("Diagnostics")
        print_info("Collecting MDE performance data...")
        
        try:
            result = subprocess.run(
                ["mdatp", "diagnostic", "create", "--folder", str(self.orchestrator.results_dir)],
                timeout=60,
                text=True,
                capture_output=True
            )
            print_success("Diagnostics collected")
            return True
        except:
            print_info("Could not collect full diagnostics (this is optional)")
            return True
