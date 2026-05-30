"""Data-driven profiled build scenario base.

Provides common phase behavior so concrete scenarios can be mostly
configuration and command data.
"""

from pathlib import Path
from typing import List, Optional
import json
import os
import re
import shutil
import subprocess
import threading
import time

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
        self.hot_event_duration = 60

        self.baseline_repo_path = self.config.repo_path
        self.optimized_repo_path = self.config.repo_path
        if self.clone_in_timed_phases:
            self.baseline_repo_path = self.config.repo_path.parent / f"{self.config.repo_path.name}{baseline_repo_suffix}"
            self.optimized_repo_path = self.config.repo_path.parent / f"{self.config.repo_path.name}{optimized_repo_suffix}"

        self._register_phases()

    def _register_phases(self) -> None:
        self.orchestrator.add_phase("Setup and Preflight", self.setup)
        self.orchestrator.add_phase("Baseline Build (No Profiles)", self.build_baseline)
        self.orchestrator.add_phase("Analyze Baseline Telemetry", self.analyze_baseline_telemetry)
        self.orchestrator.add_phase("Apply Performance Profiles", self.apply_profiles)
        self.orchestrator.add_phase("Optimized Build (With Profiles)", self.build_optimized)
        self.orchestrator.add_phase("Analyze Impact", self.analyze_results)

    def analyze_baseline_telemetry(self) -> bool:
        """Common phase 3: analyze baseline telemetry and prepare profile recommendation."""
        print_section("Analyze Baseline Telemetry")
        if not self.recommended_profiles:
            self.recommended_profiles = list(self.config.profiles or [])
            self.recommendation_source = "default"
        print_info(f"Phase 4 will apply ({self.recommendation_source}): {', '.join(self.recommended_profiles)}")
        return True

    def _collect_diagnostics(self) -> bool:
        """Backward-compatible alias for old tests/callers."""
        return self.analyze_baseline_telemetry()
        return True

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

    def _to_int(self, value):
        """Best-effort int conversion for mixed numeric fields."""
        try:
            return int(value)
        except Exception:
            try:
                return int(float(value))
            except Exception:
                return 0

    def _load_hot_event_entries(self, path: Path):
        """Load and normalize hot-event-source entries from JSON artifact."""
        if not path.exists() or path.stat().st_size == 0:
            return []
        try:
            data = json.loads(path.read_text())
            entries = data.get("eventSource", [])
            normalized = []
            for e in entries:
                if not isinstance(e, dict):
                    continue
                auth = self._to_int(e.get("authCount", 0))
                notify = self._to_int(e.get("notifyCount", 0))
                normalized.append(
                    {
                        "path": e.get("path", "?"),
                        "auth": auth,
                        "notify": notify,
                        "total": auth + notify,
                    }
                )
            normalized.sort(key=lambda x: x["total"], reverse=True)
            return normalized
        except Exception:
            return []

    def _hot_event_aggregate(self, path: Path):
        """Return aggregate auth/notify/total counts from a hot-event artifact."""
        entries = self._load_hot_event_entries(path)
        if not entries:
            return None
        auth = sum(e["auth"] for e in entries)
        notify = sum(e["notify"] for e in entries)
        return {"auth": auth, "notify": notify, "total": auth + notify}

    def _has_ghcp_cli(self):
        """Return True when GitHub CLI Copilot command appears available."""
        try:
            if shutil.which("gh") is None:
                return False
            res = subprocess.run(
                ["gh", "copilot", "--help"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            return res.returncode == 0
        except Exception:
            return False

    def _get_available_profiles(self) -> List[str]:
        """Read available performance profiles from mdatp CLI with fallback."""
        try:
            result = subprocess.run(
                ["sudo", "mdatp", "performance-profiles", "list-available"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
            parsed = []
            for line in lines:
                lower = line.lower()
                if lower.startswith("merge policy:"):
                    continue
                if lower.startswith("no available performance profiles"):
                    continue
                if lower.startswith("available profiles"):
                    continue
                if line in ("---", "====================================="):
                    continue

                first = line.split()[0].strip("-*\t")
                if first in self.config.profiles and first not in parsed:
                    parsed.append(first)

            return parsed or list(self.config.profiles)
        except Exception:
            return list(self.config.profiles)

    def _parse_ghcp_recommended_profiles(self, output_text: str, allowed_profiles: List[str]) -> List[str]:
        """Parse GHCP response into an ordered, allowed profile list for phase 4."""
        if not output_text:
            return []

        allowed_lower = {p.lower(): p for p in allowed_profiles}

        for line in output_text.splitlines():
            if line.strip().upper().startswith("RECOMMENDED_PROFILES:"):
                rhs = line.split(":", 1)[1]
                tokens = [t.strip().lower() for t in rhs.split(",") if t.strip()]
                picks = []
                for token in tokens:
                    profile = allowed_lower.get(token)
                    if profile and profile not in picks:
                        picks.append(profile)
                if picks:
                    return picks

        try:
            obj = json.loads(output_text)
            arr = obj.get("recommended_profiles") if isinstance(obj, dict) else None
            if isinstance(arr, list):
                picks = []
                for item in arr:
                    if not isinstance(item, str):
                        continue
                    profile = allowed_lower.get(item.strip().lower())
                    if profile and profile not in picks:
                        picks.append(profile)
                if picks:
                    return picks
        except Exception:
            pass

        text = output_text.lower()
        picks = []
        for profile in allowed_profiles:
            if re.search(r"\b" + re.escape(profile.lower()) + r"\b", text) and profile not in picks:
                picks.append(profile)
        return picks

    def _ghcp_profile_recommendations(self, hot_events: Path, available_profiles: Optional[List[str]] = None) -> List[str]:
        """Ask GH Copilot CLI to pick profile names from known profile list."""
        if not self._has_ghcp_cli():
            return []

        entries = self._load_hot_event_entries(hot_events)
        if not entries:
            return []

        top = entries[:10]
        top_text = "\n".join(
            [f"- total={e['total']} auth={e['auth']} notify={e['notify']} path={e['path']}" for e in top]
        )
        allowed_profiles = list(available_profiles or self.config.profiles)
        allowed = ", ".join(allowed_profiles)
        prompt = (
            f"Analyze this MDE hot-event telemetry from a {self.config.name} build and recommend which available "
            "performance profiles should be applied.\n"
            f"Available profiles: {allowed}.\n"
            "Return your final recommendation in this exact machine-readable line:\n"
            "RECOMMENDED_PROFILES: <comma-separated profile names from the available list>\n"
            "You may include brief reasoning before that final line.\n\n"
            f"Hot event sources:\n{top_text}\n"
        )

        try:
            res = subprocess.run(
                ["gh", "copilot", "suggest", "-t", "shell", prompt],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if res.returncode != 0:
                return []
            return self._parse_ghcp_recommended_profiles(res.stdout or "", allowed_profiles)
        except Exception:
            return []

    def _python_profile_recommendations(self, hot_events: Path, available_profiles: Optional[List[str]] = None) -> List[str]:
        """Default python recommendation hook; scenarios can override."""
        return []

    def _select_profiles_for_phase4(self, hot_events: Path):
        """Choose profile set to apply based on phase 3 telemetry artifacts."""
        available_profiles = self._get_available_profiles()
        python_recs = self._python_profile_recommendations(hot_events, available_profiles)
        ghcp_recs = self._ghcp_profile_recommendations(hot_events, available_profiles)

        if ghcp_recs:
            selected = ghcp_recs
            source = "ghcp"
        elif python_recs:
            selected = python_recs
            source = "python"
        else:
            selected = list(available_profiles)
            source = "default"

        self.recommended_profiles = selected
        self.recommendation_source = source

    def _start_cpu_monitor(self, log_file: Path):
        """Start background CPU sampling for wdavdaemon_unprivileged."""
        stop_event = threading.Event()

        def _run():
            with log_file.open("w") as handle:
                while not stop_event.is_set():
                    try:
                        result = subprocess.run(
                            ["ps", "-eo", "pid,%cpu,comm"],
                            capture_output=True,
                            text=True,
                            timeout=3,
                            check=False,
                        )
                        for line in result.stdout.splitlines():
                            if "wdavdaemon_unprivileged" in line:
                                parts = line.split()
                                if len(parts) >= 2:
                                    handle.write(f"{int(time.time())} {parts[1]}\n")
                                    handle.flush()
                                break
                    except Exception:
                        pass
                    stop_event.wait(2)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return stop_event, thread

    def _calc_avg_cpu(self, log_file: Path):
        """Compute average sampled CPU from monitor log."""
        if not log_file.exists() or log_file.stat().st_size == 0:
            return "N/A"
        vals = []
        for line in log_file.read_text().splitlines():
            try:
                vals.append(float(line.split()[1]))
            except Exception:
                continue
        if not vals:
            return "N/A"
        return f"{sum(vals)/len(vals):.1f}"

    def _collect_rtp_stats(self, out_file: Path):
        """Capture RTP statistics JSON snapshot."""
        try:
            with out_file.open("w") as handle:
                subprocess.run(
                    [
                        "sudo",
                        "mdatp",
                        "diagnostic",
                        "real-time-protection-statistics",
                        "--output",
                        "json",
                    ],
                    stdout=handle,
                    stderr=subprocess.DEVNULL,
                    timeout=30,
                    check=False,
                )
        except Exception:
            pass

    def _count_rtp_scans(self, json_file: Path):
        """Return total scanned files from RTP stats JSON."""
        if not json_file.exists() or json_file.stat().st_size == 0:
            return "N/A"
        try:
            data = json.loads(json_file.read_text())
            total = 0
            for item in data:
                if isinstance(item, dict):
                    total += int(item.get("totalFilesScanned", 0) or 0)
            return str(total)
        except Exception:
            return "N/A"

    def _start_hot_event_collection(self, cwd: Optional[Path] = None):
        """Start hot-event collection to run concurrently with an active build."""
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return None, set()
        try:
            scan_dir = cwd or self.config.repo_path
            existing = {str(p.resolve()) for p in scan_dir.glob("hot_event_source_*.json")}
            proc = subprocess.Popen(
                [
                    "sudo",
                    "mdatp",
                    "diagnostic",
                    "hot-event-sources",
                    f"--time={self.hot_event_duration}",
                ],
                cwd=scan_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return proc, existing
        except Exception:
            return None, set()

    def _finalize_hot_event_collection(self, proc, existing_paths, out_file: Path, cwd: Optional[Path] = None):
        """Finalize hot-event capture and persist the newest produced artifact."""
        if proc is None:
            return False
        try:
            proc.wait(timeout=self.hot_event_duration + 20)
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass

        scan_dir = cwd or self.config.repo_path
        candidates = sorted(scan_dir.glob("hot_event_source_*.json"), key=lambda p: p.stat().st_mtime)
        if not candidates:
            return False

        new_candidates = [p for p in candidates if str(p.resolve()) not in existing_paths]
        picked = new_candidates[-1] if new_candidates else candidates[-1]
        try:
            shutil.copy2(picked, out_file)
            return True
        except Exception:
            return False

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
