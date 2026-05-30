"""Data-driven profiled build scenario base.

Provides common phase behavior so concrete scenarios can be mostly
configuration and command data.
"""

from pathlib import Path
from typing import List, Optional
import subprocess

from .base import DemoScenario, ScenarioConfig
from ..ui import print_section, print_success, print_error, print_info


class ProfiledBuildScenario(DemoScenario):
    """Reusable base for clone/build/apply/analyze profile demos."""

    def __init__(
        self,
        config: ScenarioConfig,
        build_command: List[str],
        tool_checks: Optional[List[List[str]]] = None,
        repo_validation_file: Optional[str] = None,
        clone_in_timed_phases: bool = False,
        baseline_repo_suffix: str = "-baseline",
        optimized_repo_suffix: str = "-optimized",
    ):
        super().__init__(config)
        self.build_command = build_command
        self.tool_checks = tool_checks or []
        self.repo_validation_file = repo_validation_file
        self.clone_in_timed_phases = clone_in_timed_phases
        self.recommended_profiles = list(self.config.profiles or [])
        self.recommendation_source = "default"

        self.baseline_repo_path = self.config.repo_path
        self.optimized_repo_path = self.config.repo_path
        if self.clone_in_timed_phases:
            self.baseline_repo_path = self.config.repo_path.parent / f"{self.config.repo_path.name}{baseline_repo_suffix}"
            self.optimized_repo_path = self.config.repo_path.parent / f"{self.config.repo_path.name}{optimized_repo_suffix}"

        self._register_phases()

    def _register_phases(self) -> None:
        self.orchestrator.add_phase("Setup and Preflight", self.setup)
        self.orchestrator.add_phase("Baseline Build (No Profiles)", self.build_baseline)
        self.orchestrator.add_phase("Apply Performance Profiles", self.apply_profiles)
        self.orchestrator.add_phase("Optimized Build (With Profiles)", self.build_optimized)
        self.orchestrator.add_phase("Analyze Impact", self.analyze_results)

    def _fresh_clone(self, target: Path) -> bool:
        """Clone a fresh copy of repository for a timed phase."""
        try:
            if target.exists():
                subprocess.run(["rm", "-rf", str(target)], timeout=60, check=True)

            subprocess.run(
                ["git", "clone", "--depth", "1", self.config.repo_url, str(target)],
                timeout=600,
                check=True,
            )

            if self.repo_validation_file and not (target / self.repo_validation_file).exists():
                print_error(f"Expected {self.repo_validation_file} was not found in cloned repo")
                return False
            return True
        except subprocess.CalledProcessError as e:
            print_error(f"Failed to clone repository: {e}")
            return False

    def _get_profile_state(self):
        """Return (admin_only, applied_profiles) from mdatp list-applied output."""
        try:
            result = subprocess.run(
                ["sudo", "mdatp", "performance-profiles", "list-applied"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            output = result.stdout or ""
            lines = [line.strip() for line in output.splitlines() if line.strip()]

            admin_only = any(
                line.lower().startswith("merge policy:") and "admin" in line.lower()
                for line in lines
            )

            applied = set()
            for line in lines:
                lower = line.lower()
                if lower.startswith("merge policy:"):
                    continue
                if line in ("---", "====================================="):
                    continue
                if lower.startswith("no applied performance profiles"):
                    continue
                applied.add(line.split()[0])

            return admin_only, applied
        except Exception:
            return False, set()

    def _run_build(self, cwd: Path, label: str) -> bool:
        """Run build command in cwd."""
        try:
            result = subprocess.run(self.build_command, cwd=cwd, timeout=1800)
            if result.returncode != 0:
                print_error(f"{label} build failed")
                return False
            print_success(f"{label} build completed")
            return True
        except subprocess.TimeoutExpired:
            print_error("Build timed out")
            return False

    def setup(self) -> bool:
        print_section("Setup")

        self.config.repo_path.parent.mkdir(parents=True, exist_ok=True)

        for check in self.tool_checks:
            try:
                result = subprocess.run(check, capture_output=True, text=True, timeout=10)
                if result.returncode != 0:
                    print_error(f"Required tool check failed: {' '.join(check)}")
                    return False
            except Exception:
                print_error(f"Required tool check failed: {' '.join(check)}")
                return False

        if not self.clone_in_timed_phases:
            if not self.config.repo_path.exists():
                print_info(f"Cloning {self.config.repo_url}...")
                if not self._fresh_clone(self.config.repo_path):
                    return False
                print_success(f"Cloned to {self.config.repo_path}")

            if self.repo_validation_file and not (self.config.repo_path / self.repo_validation_file).exists():
                print_error(f"Expected {self.repo_validation_file} was not found in repo")
                return False

            print_success("Repository is ready")
        else:
            print_success("Tooling is ready")
            print_info("Clone is included in baseline/optimized timed phases")

        return True

    def build_baseline(self) -> bool:
        print_section("Baseline Build (No Profiles)")
        print_info(f"Running baseline for {self.config.name}...")

        for profile in self.config.profiles:
            try:
                subprocess.run(
                    ["sudo", "mdatp", "performance-profiles", "remove", "--name", profile],
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
            except Exception:
                pass

        _, applied = self._get_profile_state()
        residual = sorted(set(self.config.profiles) & set(applied))
        if residual:
            print_error("Baseline is not clean: some demo profiles are still applied")
            for profile in residual:
                print(f"   - {profile}")
            return False

        baseline_cwd = self.baseline_repo_path
        if self.clone_in_timed_phases:
            print_info(f"Fresh clone for baseline: {baseline_cwd}")
            if not self._fresh_clone(baseline_cwd):
                return False

        return self._run_build(baseline_cwd, "Baseline")

    def apply_profiles(self) -> bool:
        print_section("Applying Profiles")

        selected = self.recommended_profiles or list(self.config.profiles)
        print_info(f"Selected profile set ({self.recommendation_source}): {', '.join(selected)}")

        admin_only, applied = self._get_profile_state()
        if admin_only:
            missing = sorted(set(selected) - set(applied))
            if missing:
                print_error("Admin-only policy detected: profiles cannot be applied locally")
                print_info("Ask your IT admin to deploy these profiles via MDM, then re-run:")
                for profile in missing:
                    print(f"   - {profile}")
                return False
            print_success("Admin-only mode: required profiles are already deployed via MDM")
            return True

        for profile in selected:
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
        print_info(f"Running optimized build for {self.config.name}...")

        optimized_cwd = self.optimized_repo_path
        if self.clone_in_timed_phases:
            print_info(f"Fresh clone for optimized run: {optimized_cwd}")
            if not self._fresh_clone(optimized_cwd):
                return False

        return self._run_build(optimized_cwd, "Optimized")

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
            print(f"   Baseline time:          {baseline:.1f}s")
        if optimized is not None:
            print(f"   Optimized time:         {optimized:.1f}s")
        if baseline and optimized:
            saved = baseline - optimized
            speedup = ((saved / baseline) * 100) if baseline > 0 else 0
            print(f"   Speedup:                {speedup:.0f}% ({saved:.1f}s saved)")

        print_info("Profiles applied:")
        print(f"   Recommendation source:  {self.recommendation_source}")
        print(f"   Selected profiles:      {', '.join(self.recommended_profiles or self.config.profiles)}")
        _, active_applied = self._get_profile_state()
        if active_applied:
            active_sorted = sorted([p for p in active_applied if p in self.config.profiles])
            print(f"   Active on endpoint:     {', '.join(active_sorted)}")
        else:
            print("   Active on endpoint:     (none detected)")

        print_success("Analysis complete")
        return True
