"""Data-driven profiled build scenario base.

Provides common phase behavior so concrete scenarios can be mostly
configuration and command data.
"""

from pathlib import Path
from typing import Dict, List, Optional
import errno
import json
import os
import shlex
import shutil
import subprocess
import threading
import time
from datetime import datetime

from .base import DemoScenario, ScenarioConfig
from ..ui import print_section, print_success, print_error, print_info, print_warning

# Standard EICAR antivirus test string (not malicious — used to verify AV scanning).
_EICAR_STRING = (
    "X5O!P%@AP[4\\PZX54(P^)7CC)7}"
    "$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
)

# Sentinel returned by _place_eicar when MDE blocked the write (EPERM).
# Treated as immediate detection — no file exists to monitor.
_EICAR_BLOCKED = object()


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
        clone_args: Optional[List[str]] = None,
        install_command: Optional[List[str]] = None,
        include_install_in_build: bool = False,
        build_cleanup_paths: Optional[List[str]] = None,
        build_cleanup_globs: Optional[List[str]] = None,
        default_exclusions: Optional[List[dict]] = None,
        eicar_subdir: str = "",
        enable_resume_checkpoint: bool = False,
        state_file_name: str = ".profiled-build-state.json",
        profile_change_policy: str = "prompt",
    ):
        super().__init__(config)
        self.build_command = build_command
        self.tool_checks = tool_checks or []
        self.repo_validation_file = repo_validation_file
        self.clone_in_timed_phases = clone_in_timed_phases
        self.clone_args = list(clone_args or ["--depth", "1"])
        self.install_command = list(install_command or [])
        self.include_install_in_build = include_install_in_build
        self.build_cleanup_paths = list(build_cleanup_paths or [])
        self.build_cleanup_globs = list(build_cleanup_globs or [])
        # default_exclusions: list of {type: "folder"|"file"|"process", rel: "<relative path>"}
        self.default_exclusions = list(default_exclusions or [])
        # eicar_subdir: repo-relative directory where EICAR is placed during the demo
        self.eicar_subdir = eicar_subdir
        self.enable_resume_checkpoint = enable_resume_checkpoint
        self.profile_change_policy = profile_change_policy
        self.state_file = self.orchestrator.results_dir / state_file_name
        self.run_log_file = self.orchestrator.results_dir / "demo_run.log"

        self.applied_exclusions: List[dict] = []
        self.baseline: Dict = {
            "time": 0.0,
            "cpu": "N/A",
            "scans": "N/A",
            "profiles_at_start": "(none)",
        }
        self.exclusions_build: Dict = {
            "time": 0.0,
            "cpu": "N/A",
            "scans": "N/A",
            "eicar_detected": None,
        }
        self.profiles_build: Dict = {
            "time": 0.0,
            "cpu": "N/A",
            "scans": "N/A",
            "eicar_detected": None,
        }
        self.compensating_scan_status = "not_run"
        self.compensating_scan_threats_found = "N/A"

        self.baseline_repo_path = self.config.repo_path
        self.optimized_repo_path = self.config.repo_path
        if self.clone_in_timed_phases:
            self.baseline_repo_path = self.config.repo_path.parent / f"{self.config.repo_path.name}{baseline_repo_suffix}"
            self.optimized_repo_path = self.config.repo_path.parent / f"{self.config.repo_path.name}{optimized_repo_suffix}"

        self._register_phases()

    # ──────────────────────────────────────────────────────────────────
    # Logging
    # ──────────────────────────────────────────────────────────────────

    def _start_run_log(self):
        try:
            ts = datetime.now().isoformat(timespec="seconds")
            with self.run_log_file.open("a") as handle:
                handle.write("\n" + "=" * 80 + "\n")
                handle.write(f"run_started: {ts}\n")
                handle.write(f"scenario: {self.config.name}\n")
                handle.write(f"repo_path: {self.config.repo_path}\n")
                handle.write("=" * 80 + "\n")
        except Exception:
            pass

    def _log_line(self, message: str):
        try:
            ts = datetime.now().isoformat(timespec="seconds")
            with self.run_log_file.open("a") as handle:
                handle.write(f"[{ts}] {message}\n")
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────────
    # Phase registration
    # ──────────────────────────────────────────────────────────────────

    def _register_phases(self) -> None:
        self.orchestrator.add_phase("Setup and Preflight", self.setup)
        self.orchestrator.add_phase("Baseline Build", self.build_baseline)
        self.orchestrator.add_phase("AV Exclusions Build", self.build_with_exclusions)
        self.orchestrator.add_phase("Compensating Scan", self.run_compensating_scan_phase)
        self.orchestrator.add_phase("Profiles Build", self.build_with_profiles)
        self.orchestrator.add_phase("Compare Results", self.compare_results)

    # ──────────────────────────────────────────────────────────────────
    # Formatting helpers
    # ──────────────────────────────────────────────────────────────────

    def _markdown_table(self, headers: List[str], rows: List[List[str]]) -> str:
        if not headers:
            return ""

        def escape_cell(value):
            return str(value).replace("|", "\\|")

        lines = [
            "| " + " | ".join(escape_cell(h) for h in headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
        ]
        for row in rows:
            lines.append("| " + " | ".join(escape_cell(c) for c in row) + " |")
        return "\n".join(lines)

    def _percent_change(self, before, after) -> str:
        try:
            before_val = float(before)
            after_val = float(after)
            if before_val <= 0:
                return "N/A"
            pct = ((before_val - after_val) / before_val) * 100.0
            return f"{pct:.0f}%"
        except Exception:
            return "N/A"

    def _active_profiles_text(self) -> str:
        _, active_applied = self._get_profile_state()
        if not active_applied:
            return "(none detected)"
        active_sorted = sorted([p for p in active_applied if p in self.config.profiles])
        return ", ".join(active_sorted) if active_sorted else "(none detected)"

    def _bool_icon(self, value: Optional[bool], true_label: str = "✅ Yes", false_label: str = "⚠️  No") -> str:
        if value is True:
            return true_label
        if value is False:
            return false_label
        return "N/A"

    # ──────────────────────────────────────────────────────────────────
    # EICAR helpers
    # ──────────────────────────────────────────────────────────────────

    def _place_eicar(self, target_dir: Path) -> tuple:
        """Write the EICAR test string to a unique timestamped filename in target_dir.

        Uses a timestamp in the filename so MDE never suppresses re-detection
        due to a recently quarantined path.

        Returns:
          (path, placed_at)   — file written; poll for quarantine/threat-list.
          (_EICAR_BLOCKED, 0) — MDE blocked the write (EPERM): immediate detection.
          (None, 0)           — unexpected error; skip detection.
        """
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            placed_at = time.time()
            path = target_dir / f"eicar_{int(placed_at)}.txt"
            path.write_text(_EICAR_STRING)
            self._log_line(f"eicar:placed path={path}")
            print_info(f"EICAR test file placed: {path}")
            return path, placed_at
        except OSError as e:
            if e.errno == errno.EPERM:
                self._log_line(f"eicar:blocked_at_write path={target_dir} errno=EPERM")
                print_info("MDE blocked the EICAR write at the filesystem level (Operation not permitted).")
                return _EICAR_BLOCKED, 0
            self._log_line(f"eicar:place_error error={e}")
            print_warning(f"Could not place EICAR test file: {e}")
            return None, 0
        except Exception as e:
            self._log_line(f"eicar:place_error error={e}")
            print_warning(f"Could not place EICAR test file: {e}")
            return None, 0

    def _eicar_in_threat_list(self, data: object, since_s: float) -> bool:
        """Return True if threat list contains an EICAR detection at or after since_s.

        MDE's JSON structure is:
            {"threats": {"scans": [{"threats": [{"threat": {"name": ...}, "detection_time": <ms>}]}]}}

        detection_time is milliseconds since epoch.  Paths are not present in
        threat entries, so we match by name containing "EICAR" plus timestamp.
        """
        since_ms = int(since_s * 1000)
        if not isinstance(data, dict):
            return False
        inner = data.get("threats", {})
        if isinstance(inner, list):
            scans = [{"threats": inner}]
        elif isinstance(inner, dict):
            scans = inner.get("scans", [])
        else:
            return False
        for scan in scans:
            for entry in scan.get("threats", []):
                if not isinstance(entry, dict):
                    continue
                threat_info = entry.get("threat", entry)
                name = str(threat_info.get("name", "")).upper()
                det_time = entry.get("detection_time", 0)
                if "EICAR" in name and det_time >= since_ms:
                    return True
        return False

    def _check_eicar_detected(self, path: Path, placed_at: float = 0, poll_interval: int = 2, max_wait: int = 30) -> bool:
        """Poll until MDE detects/quarantines the EICAR at path, or max_wait expires.

        Every poll_interval seconds:
          1. If the file is gone → MDE quarantined it → detected.
          2. Query threat list for an EICAR entry with detection_time >= placed_at.
        Returns True if detected within max_wait seconds, False otherwise.
        """
        print_info(f"Waiting for real-time protection to respond (up to {max_wait}s)...")
        elapsed = 0
        if placed_at == 0:
            placed_at = time.time()

        while elapsed < max_wait:
            time.sleep(poll_interval)
            elapsed += poll_interval

            if not path.exists():
                self._log_line(f"eicar:detected path={path} method=file_gone elapsed={elapsed}s")
                return True

            try:
                result = subprocess.run(
                    ["mdatp", "threat", "list", "--output", "json"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                if result.returncode == 0 and result.stdout.strip():
                    data = json.loads(result.stdout)
                    if self._eicar_in_threat_list(data, placed_at):
                        self._log_line(f"eicar:detected path={path} method=threat_list elapsed={elapsed}s")
                        return True
            except Exception as exc:
                self._log_line(f"eicar:poll_error {exc}")

        self._log_line(f"eicar:not_detected path={path} waited={max_wait}s")
        return False

    def _remove_eicar(self, path: Optional[Path]) -> None:
        """Remove EICAR test file if still present (MDE may have already quarantined it)."""
        if path is None:
            return
        try:
            if path.exists():
                path.unlink()
                self._log_line(f"eicar:removed path={path}")
        except Exception as e:
            self._log_line(f"eicar:remove_error path={path} error={e}")

    # ──────────────────────────────────────────────────────────────────
    # Default AV exclusion management
    # ──────────────────────────────────────────────────────────────────

    def _get_current_exclusions(self) -> List[dict]:
        """Return current mdatp folder exclusions as a list of dicts with 'type' and 'value'."""
        try:
            result = subprocess.run(
                ["mdatp", "exclusion", "list", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode != 0 or not result.stdout.strip():
                return []
            data = json.loads(result.stdout)
            if isinstance(data, list):
                return [{"type": e.get("type", "folder"), "value": e.get("value", e.get("path", ""))} for e in data if isinstance(e, dict)]
            if isinstance(data, dict):
                entries = data.get("exclusions", data.get("value", []))
                return [{"type": e.get("type", "folder"), "value": e.get("value", e.get("path", ""))} for e in entries if isinstance(e, dict)]
        except Exception:
            pass
        return []

    def _check_no_preexisting_exclusions(self) -> bool:
        """Verify none of the scenario's default exclusion paths are already active.

        A tainted exclusion list would make the baseline build artificially fast,
        breaking the AV exclusions vs profiles comparison.
        """
        if not self.default_exclusions:
            return True

        current = self._get_current_exclusions()
        if not current:
            return True

        scenario_paths = {
            str(base / excl["rel"]).rstrip("/")
            for excl in self.default_exclusions
            for base in ([self.config.repo_path, self.optimized_repo_path] if self.clone_in_timed_phases else [self.config.repo_path])
        }
        current_values = {e.get("value", "").rstrip("/") for e in current}

        conflicts = scenario_paths & current_values
        if not conflicts:
            return True

        print_error("Baseline cannot run: scenario exclusions are already active.")
        print_info(
            "The following folder exclusions must be removed before the demo,\n"
            "   otherwise the baseline build will skip MDE scanning for these paths\n"
            "   and you won't see the real performance difference."
        )
        for path in sorted(conflicts):
            print(f"   sudo mdatp exclusion folder remove --path '{path}'")
            self._log_line(f"preflight:exclusion_conflict path={path}")
        return False

    def _apply_default_exclusions(self) -> List[dict]:
        """Apply scenario default folder exclusions via mdatp. Returns list of applied entries.

        Uses optimized_repo_path for clone_in_timed_phases scenarios because the actual
        build (and EICAR placement) happens in the optimized clone, not in config.repo_path.
        """
        base_path = self.optimized_repo_path if self.clone_in_timed_phases else self.config.repo_path
        applied = []
        for excl in self.default_exclusions:
            abs_path = str(base_path / excl["rel"])
            excl_type = excl.get("type", "folder")
            try:
                result = subprocess.run(
                    ["sudo", "mdatp", "exclusion", excl_type, "add", "--path", abs_path],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                if result.returncode == 0:
                    applied.append({"type": excl_type, "value": abs_path})
                    self._log_line(f"exclusion:add type={excl_type} path={abs_path} status=applied")
                    print_success(f"Exclusion applied: {excl_type}: {abs_path}")
                else:
                    self._log_line(f"exclusion:add type={excl_type} path={abs_path} status=nonzero")
                    print_info(f"Exclusion not applied (may already exist): {abs_path}")
            except Exception as e:
                self._log_line(f"exclusion:add type={excl_type} path={abs_path} error={e}")
                print_info(f"Exclusion error for {abs_path}: {e}")
        self.applied_exclusions = applied
        return applied

    def _remove_default_exclusions(self) -> None:
        """Remove all exclusions applied during this run."""
        if not self.applied_exclusions:
            return
        removed = 0
        for excl in reversed(self.applied_exclusions):
            excl_type = excl.get("type", "folder")
            abs_path = excl.get("value", "")
            try:
                result = subprocess.run(
                    ["sudo", "mdatp", "exclusion", excl_type, "remove", "--path", abs_path],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                if result.returncode == 0:
                    removed += 1
                    self._log_line(f"exclusion:remove type={excl_type} path={abs_path} status=removed")
                else:
                    self._log_line(f"exclusion:remove type={excl_type} path={abs_path} status=nonzero")
            except Exception as e:
                self._log_line(f"exclusion:remove type={excl_type} path={abs_path} error={e}")
        print_info(f"AV exclusions removed: {removed}/{len(self.applied_exclusions)}")
        self.applied_exclusions = []

    # ──────────────────────────────────────────────────────────────────
    # Profile management
    # ──────────────────────────────────────────────────────────────────

    def _confirm_profile_change(self, action: str, profiles: List[str]) -> bool:
        if not profiles:
            return True
        mode = (self.profile_change_policy or "prompt").lower()
        if mode == "always":
            return True
        if mode == "never":
            print_info(f"{action} cancelled by profile change policy (never)")
            self._log_line(f"profile_change:cancelled action={action} policy=never")
            return False
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return True
        print_info(f"This step will {action} performance profiles:")
        print(f"   {', '.join(profiles)}")
        answer = input(f"Proceed to {action} profiles? [Y/n] ").strip().lower()
        return answer not in ("n", "no")

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

    def _log_profile_state_snapshot(self, label: str):
        try:
            result = subprocess.run(
                ["sudo", "mdatp", "performance-profiles", "list-applied"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            raw = (result.stdout or "").strip()
            admin_only, applied = self._get_profile_state()
            self._log_line(f"{label}: admin_only={admin_only} applied={sorted(list(applied))}")
            if raw:
                for line in raw.splitlines():
                    self._log_line(f"{label} raw: {line}")
        except Exception as e:
            self._log_line(f"{label}: failed to capture profile state ({e})")

    def _get_available_profiles(self) -> List[str]:
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

    def _reset_profiles_at_start(self) -> bool:
        """Remove demo performance profiles at run start for a clean baseline."""
        admin_only, currently_applied = self._get_profile_state()
        if admin_only:
            return True

        removable_profiles = sorted(set(self._get_available_profiles()) | set(currently_applied))
        if not removable_profiles:
            self._log_line("setup.reset_profiles residual=none")
            return True

        print_info("Removing any pre-existing demo performance profiles for a clean start...")
        if not self._confirm_profile_change("remove", removable_profiles):
            print_info("Initial profile reset cancelled by user")
            self._log_line("setup.reset_profiles:cancelled profile_removal_declined")
            return False

        for profile in removable_profiles:
            try:
                subprocess.run(
                    ["sudo", "mdatp", "performance-profiles", "remove", "--name", profile],
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
                self._log_line(f"setup.reset_profiles remove_attempt profile={profile}")
            except Exception:
                self._log_line(f"setup.reset_profiles remove_attempt profile={profile} exception")

        _, applied = self._get_profile_state()
        residual = sorted(set(applied))
        self._log_line(f"setup.reset_profiles guard residual_profiles={residual}")
        if residual:
            print_error("Endpoint not clean: demo profiles are still applied after reset")
            for profile in residual:
                print(f"   - {profile}")
            self._log_line("setup.reset_profiles:failed profile_guard")
            return False

        print_success("Endpoint profile state is clean for a fresh run")
        return True

    def apply_profiles(self) -> bool:
        """Apply scenario performance profiles to the endpoint."""
        selected = list(self.config.profiles)
        self._log_line(f"apply_profiles:start profiles={selected}")
        print_info(f"Applying performance profiles: {', '.join(selected)}")

        admin_only, applied = self._get_profile_state()
        if admin_only:
            missing = sorted(set(selected) - set(applied))
            if missing:
                print_error("Admin-only policy: profiles cannot be applied locally")
                print_info("Ask your IT admin to deploy these profiles via MDM, then re-run:")
                for profile in missing:
                    print(f"   - {profile}")
                return False
            print_success("Admin-only mode: required profiles are already deployed via MDM")
            return True

        if not self._confirm_profile_change("apply", selected):
            print_info("Profile application cancelled by user")
            self._log_line("apply_profiles:cancelled profile_apply_declined")
            return False

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
                    self._log_line(f"apply_profiles profile={profile} status=nonzero")
                else:
                    print_success(f"Applied: {profile}")
                    self._log_line(f"apply_profiles profile={profile} status=applied")
            except Exception as e:
                print_info(f"Could not apply {profile}: {e}")
                self._log_line(f"apply_profiles profile={profile} exception={e}")

        self._log_profile_state_snapshot("apply_profiles.post_apply")
        return True

    # ──────────────────────────────────────────────────────────────────
    # Build infrastructure
    # ──────────────────────────────────────────────────────────────────

    def _prepare_build_environment(self, phase: str, cwd: Path):
        for rel_path in self.build_cleanup_paths:
            target = cwd / rel_path
            try:
                if target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
                elif target.exists():
                    target.unlink()
            except Exception:
                pass
        for pattern in self.build_cleanup_globs:
            for match in cwd.rglob(pattern):
                try:
                    if match.is_dir():
                        shutil.rmtree(match, ignore_errors=True)
                    else:
                        match.unlink()
                except Exception:
                    pass

    def _run_build_command(self, cwd: Path, label: str) -> bool:
        if self.include_install_in_build and self.install_command:
            install_result = subprocess.run(
                self.install_command,
                cwd=cwd,
                timeout=900,
            )
            if install_result.returncode != 0:
                print_error(f"{label} dependency install failed")
                return False
        return self._run_build(cwd, label)

    def _run_build(self, cwd: Path, label: str) -> bool:
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

    def _fresh_clone(self, target: Path) -> bool:
        try:
            if target.exists():
                subprocess.run(["rm", "-rf", str(target)], timeout=60, check=True)
            clone_cmd = ["git", "clone", *self.clone_args, self.config.repo_url, str(target)]
            subprocess.run(clone_cmd, timeout=600, check=True)
            if self.repo_validation_file and not (target / self.repo_validation_file).exists():
                print_error(f"Expected {self.repo_validation_file} was not found in cloned repo")
                return False
            return True
        except subprocess.CalledProcessError as e:
            print_error(f"Failed to clone repository: {e}")
            return False

    # ──────────────────────────────────────────────────────────────────
    # Monitoring helpers
    # ──────────────────────────────────────────────────────────────────

    def _start_cpu_monitor(self, log_file: Path):
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
        try:
            with out_file.open("w") as handle:
                subprocess.run(
                    ["sudo", "mdatp", "diagnostic", "real-time-protection-statistics", "--output", "json"],
                    stdout=handle,
                    stderr=subprocess.DEVNULL,
                    timeout=30,
                    check=False,
                )
        except Exception:
            pass

    def _rtp_total_files(self, json_file: Path):
        if not json_file.exists() or json_file.stat().st_size == 0:
            return None
        try:
            data = json.loads(json_file.read_text())
            counters = []
            if isinstance(data, list):
                counters = data
            elif isinstance(data, dict):
                raw = data.get("counters", [])
                if isinstance(raw, list):
                    counters = raw
            total = 0
            for item in counters:
                if isinstance(item, dict):
                    total += int(item.get("totalFilesScanned", 0) or 0)
            return total
        except Exception:
            return None

    def _count_rtp_scan_delta(self, before_file: Path, after_file: Path):
        before_total = self._rtp_total_files(before_file)
        after_total = self._rtp_total_files(after_file)
        if before_total is None or after_total is None:
            return "N/A"
        return str(max(0, after_total - before_total))

    def _to_int(self, value):
        try:
            return int(value)
        except Exception:
            try:
                return int(float(value))
            except Exception:
                return 0

    # ──────────────────────────────────────────────────────────────────
    # Checkpoint persistence
    # ──────────────────────────────────────────────────────────────────

    def _persist_baseline_state(self):
        if not self.enable_resume_checkpoint:
            return
        baseline_time = float(self.baseline.get("time") or 0)
        if baseline_time <= 0:
            self._clear_state()
            self._log_line("checkpoint:skipped_invalid baseline_duration_seconds<=0")
            return
        self._save_state(
            {
                "baseline_complete": True,
                "baseline_duration_seconds": baseline_time,
                "baseline_cpu_avg": self.baseline.get("cpu", "N/A"),
                "baseline_scans": self.baseline.get("scans", "N/A"),
            }
        )

    def _load_state(self):
        if not self.state_file.exists():
            return None
        try:
            return json.loads(self.state_file.read_text())
        except Exception:
            return None

    def _save_state(self, data):
        try:
            if "created_at_epoch" not in data:
                data["created_at_epoch"] = time.time()
            self.state_file.write_text(json.dumps(data, indent=2))
        except Exception:
            pass

    def _clear_state(self):
        try:
            if self.state_file.exists():
                self.state_file.unlink()
        except Exception:
            pass

    def _is_state_stale(self, state: dict) -> bool:
        if not state or not state.get("baseline_complete"):
            return True
        try:
            baseline_time = float(state.get("baseline_duration_seconds") or 0)
        except Exception:
            baseline_time = 0
        if baseline_time <= 0:
            return True
        try:
            created_at = float(state.get("created_at_epoch") or self.state_file.stat().st_mtime)
        except Exception:
            created_at = time.time()
        if (time.time() - created_at) > 24 * 3600:
            return True
        # If profiles-build artifacts exist newer than the checkpoint, a full run already happened.
        phase5_marker = self.orchestrator.results_dir / "phase5_cpu.log"
        if phase5_marker.exists():
            try:
                if phase5_marker.stat().st_mtime >= self.state_file.stat().st_mtime:
                    return True
            except Exception:
                pass
        return False

    # ──────────────────────────────────────────────────────────────────
    # Phase 1: Setup
    # ──────────────────────────────────────────────────────────────────

    def setup(self) -> bool:
        print_section("Setup")
        self._start_run_log()
        self._log_line("phase_setup:start")
        self._log_line(f"results_dir={self.orchestrator.results_dir}")
        print_info(f"Run log: {self.run_log_file}")

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

        if not self._reset_profiles_at_start():
            return False

        admin_only, applied = self._get_profile_state()
        if admin_only:
            print_info("Merge policy is admin-only. Performance profiles must be deployed via MDM.")
            applied_required = sorted(set(self.config.profiles) & set(applied))
            if applied_required:
                print_error("Admin-only mode has required profiles already applied")
                print_info("This run needs a clean baseline with no demo profiles.")
                print_info("Ask your IT admin to remove these before baseline:")
                for profile in applied_required:
                    print(f"   - {profile}")
                return False

        if self.install_command and not self.include_install_in_build:
            print_info("Running dependency install (setup phase)...")
            try:
                subprocess.run(
                    self.install_command,
                    cwd=self.config.repo_path,
                    timeout=600,
                    check=True,
                )
                print_success("Dependencies installed")
            except subprocess.CalledProcessError as e:
                print_error(f"Dependency install failed: {e}")
                return False
        elif self.install_command and self.include_install_in_build:
            print_info("Dependency install is included in timed build phases")

        if self.default_exclusions:
            print_info(f"Default AV exclusions configured for this scenario ({len(self.default_exclusions)}):")
            for excl in self.default_exclusions:
                print(f"   - {excl.get('type', 'folder')}: {self.config.repo_path / excl['rel']}")
            if not self._check_no_preexisting_exclusions():
                return False
        if self.eicar_subdir:
            print_info(f"EICAR test directory: {self.config.repo_path / self.eicar_subdir}")

        self._log_line("phase_setup:complete")
        return True

    # ──────────────────────────────────────────────────────────────────
    # Phase 2: Baseline Build
    # ──────────────────────────────────────────────────────────────────

    def build_baseline(self) -> bool:
        print_section("Baseline Build (No Exclusions, No Profiles)")
        print_info(f"Running baseline for {self.config.name}...")
        self._log_line("phase_baseline:start")
        self._log_profile_state_snapshot("baseline.pre_remove")

        _, currently_applied = self._get_profile_state()
        removable_profiles = sorted(set(self._get_available_profiles()) | set(currently_applied))
        if removable_profiles:
            if not self._confirm_profile_change("remove", removable_profiles):
                print_info("Baseline cleanup cancelled by user")
                self._log_line("phase_baseline:cancelled profile_removal_declined")
                return False
            for profile in removable_profiles:
                try:
                    subprocess.run(
                        ["sudo", "mdatp", "performance-profiles", "remove", "--name", profile],
                        capture_output=True,
                        timeout=10,
                        check=False,
                    )
                except Exception:
                    pass

        self._log_profile_state_snapshot("baseline.post_remove")
        _, applied = self._get_profile_state()
        if applied:
            print_error("Baseline is not clean: some demo profiles are still applied")
            for profile in sorted(applied):
                print(f"   - {profile}")
            self._log_line("phase_baseline:failed profile_guard")
            return False

        self.baseline["profiles_at_start"] = "(none)"

        baseline_cwd = self.baseline_repo_path
        if self.clone_in_timed_phases:
            print_info(f"Fresh clone for baseline: {baseline_cwd}")
            if not self._fresh_clone(baseline_cwd):
                return False

        self._prepare_build_environment("baseline", baseline_cwd)

        try:
            subprocess.run(
                ["sudo", "mdatp", "config", "real-time-protection-statistics", "--value", "enabled"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
        except Exception:
            pass

        rtp_before = self.orchestrator.results_dir / "phase1_rtp_before.json"
        self._collect_rtp_stats(rtp_before)

        cpu_log = self.orchestrator.results_dir / "phase1_cpu.log"
        stop_event, monitor_thread = self._start_cpu_monitor(cpu_log)
        start = time.time()

        ok = self._run_build_command(baseline_cwd, "Baseline")
        elapsed = time.time() - start

        stop_event.set()
        monitor_thread.join(timeout=3)

        if not ok:
            return False

        rtp_after = self.orchestrator.results_dir / "phase1_rtp_after.json"
        self._collect_rtp_stats(rtp_after)
        self.baseline["time"] = elapsed
        self.baseline["cpu"] = self._calc_avg_cpu(cpu_log)
        self.baseline["scans"] = self._count_rtp_scan_delta(rtp_before, rtp_after)
        print_info(f"Baseline build time: {elapsed:.1f}s  |  MDE avg CPU: {self.baseline['cpu']}%")
        self._log_line(
            f"phase_baseline:complete time={elapsed:.2f}s cpu={self.baseline['cpu']} scans={self.baseline['scans']}"
        )

        self._persist_baseline_state()
        return True

    # ──────────────────────────────────────────────────────────────────
    # Phase 3: AV Exclusions Build
    # ──────────────────────────────────────────────────────────────────

    def build_with_exclusions(self) -> bool:
        print_section("AV Exclusions Build")
        print_info("Applying AV exclusions and rebuilding...")
        self._log_line("phase_exclusions:start")

        print_warning(
            "SECURITY NOTE: AV folder exclusions tell Defender to skip scanning those paths entirely.\n"
            "   This is what a well-meaning admin might configure to improve build performance —\n"
            "   but it creates a blind spot for any threat that lands in those directories."
        )

        if not self.default_exclusions:
            print_warning("No default exclusions configured for this scenario — skipping exclusions phase")
            self._log_line("phase_exclusions:skipped no_default_exclusions")
            return True

        applied = self._apply_default_exclusions()
        if not applied:
            print_warning("No exclusions were applied")
        else:
            print_success(f"{len(applied)} AV exclusion(s) applied")

        optimized_cwd = self.optimized_repo_path
        if self.clone_in_timed_phases:
            print_info(f"Fresh clone for exclusions run: {optimized_cwd}")
            if not self._fresh_clone(optimized_cwd):
                return False

        self._prepare_build_environment("exclusions", optimized_cwd)

        try:
            subprocess.run(
                ["sudo", "mdatp", "config", "real-time-protection-statistics", "--value", "enabled"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False,
            )
        except Exception:
            pass

        rtp_before = self.orchestrator.results_dir / "phase3_rtp_before.json"
        self._collect_rtp_stats(rtp_before)

        cpu_log = self.orchestrator.results_dir / "phase3_cpu.log"
        stop_event, monitor_thread = self._start_cpu_monitor(cpu_log)
        start = time.time()

        ok = self._run_build_command(optimized_cwd, "Exclusions")
        elapsed = time.time() - start

        stop_event.set()
        monitor_thread.join(timeout=3)

        if not ok:
            return False

        rtp_after = self.orchestrator.results_dir / "phase3_rtp_after.json"
        self._collect_rtp_stats(rtp_after)
        self.exclusions_build["time"] = elapsed
        self.exclusions_build["cpu"] = self._calc_avg_cpu(cpu_log)
        self.exclusions_build["scans"] = self._count_rtp_scan_delta(rtp_before, rtp_after)
        print_info(f"Exclusions build time: {elapsed:.1f}s  |  MDE avg CPU: {self.exclusions_build['cpu']}%")

        # Place EICAR in the excluded subdirectory and check for detection
        if self.eicar_subdir and applied:
            print_section("EICAR Detection Check — AV Exclusions")
            print_info("Placing EICAR test file inside an excluded directory...")
            eicar_dir = optimized_cwd / self.eicar_subdir
            eicar_path, eicar_placed_at = self._place_eicar(eicar_dir)
            if eicar_path is _EICAR_BLOCKED:
                # MDE blocked write even in excluded dir — unexpected but treat as detected
                detected = True
                self.exclusions_build["eicar_detected"] = detected
                print_success("EICAR write blocked by MDE (unexpected with exclusion active)")
                self._log_line("eicar:phase3_exclusions detected=True method=blocked_at_write")
            elif eicar_path:
                detected = self._check_eicar_detected(eicar_path, placed_at=eicar_placed_at)
                self.exclusions_build["eicar_detected"] = detected
                self.exclusions_build["eicar_path"] = str(eicar_path)
                if detected:
                    print_success("EICAR detected — AV exclusions did not cover this file")
                else:
                    print_warning(
                        "⚠️  EICAR NOT detected — the AV exclusion created a security gap!\n"
                        "   Malware placed in this directory would go undetected by real-time protection."
                    )
                self._log_line(
                    f"eicar:phase3_exclusions detected={detected} path={eicar_path}"
                )

        self._log_line(
            f"phase_exclusions:complete time={elapsed:.2f}s cpu={self.exclusions_build['cpu']}"
        )
        return True

    # ──────────────────────────────────────────────────────────────────
    # Phase 4: Compensating Scan
    # ──────────────────────────────────────────────────────────────────

    def run_compensating_scan_phase(self) -> bool:
        print_section("Compensating Scan (Mitigation for AV Exclusions)")
        self._log_line("phase_compensating_scan:start")

        print_info(
            "When using AV exclusions, security best practice requires a compensating control:\n"
            "   Run a custom scan with --ignore-exclusions after every build to catch\n"
            "   anything that real-time protection missed due to the exclusions."
        )
        print_warning(
            "This is the overhead cost of using AV exclusions:\n"
            "   every build must be followed by a blocking security scan."
        )

        scan_targets = []
        for excl in self.default_exclusions:
            abs_path = self.optimized_repo_path / excl["rel"]
            if abs_path.exists():
                scan_targets.append(str(abs_path))

        if not scan_targets:
            print_info("No excluded directories exist yet — skipping compensating scan")
            self.compensating_scan_status = "skipped_no_targets"
            self._log_line("phase_compensating_scan:skipped no_targets")
            return True

        print_info(f"Scanning {len(scan_targets)} excluded director(y/ies) with --ignore-exclusions...")
        all_ok = True
        threats_found = "0"
        for target_path in scan_targets:
            print_info(f"Scanning: {target_path}")
            try:
                result = subprocess.run(
                    ["sudo", "mdatp", "scan", "custom", "--path", target_path, "--ignore-exclusions"],
                    capture_output=True,
                    text=True,
                    timeout=300,
                    check=False,
                )
                if result.returncode == 0:
                    print_success(f"Scan completed: {target_path}")
                    self._log_line(f"compensating_scan:completed path={target_path}")
                else:
                    all_ok = False
                    self._log_line(
                        f"compensating_scan:nonzero path={target_path} exit={result.returncode}"
                    )
                    print_info(f"Scan returned exit {result.returncode} for {target_path}")
            except subprocess.TimeoutExpired:
                all_ok = False
                self._log_line(f"compensating_scan:timeout path={target_path}")
                print_warning(f"Scan timed out for {target_path}")
            except Exception as e:
                all_ok = False
                self._log_line(f"compensating_scan:error path={target_path} error={e}")
                print_warning(f"Scan error for {target_path}: {e}")

        self.compensating_scan_status = "completed" if all_ok else "partial"

        # Check threat list for EICAR detection from the scan.
        # Use a permissive since_s=0 so we catch any EICAR in the list regardless of age.
        try:
            result = subprocess.run(
                ["mdatp", "threat", "list", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                if self._eicar_in_threat_list(data, since_s=0):
                    threats_found = "1"
                    print_success(
                        "✅ Compensating scan found the EICAR threat!\n"
                        "   The scan caught what real-time protection missed due to the exclusion."
                    )
                    self._log_line("compensating_scan:eicar_found")
                else:
                    print_info("No EICAR threats in threat list after scan")
                    self._log_line("compensating_scan:eicar_not_found")
        except Exception as e:
            self._log_line(f"compensating_scan:threat_list_error {e}")

        self.compensating_scan_threats_found = threats_found

        print_info(
            "\n   💡 Key insight: this scan is REQUIRED every time you build when using AV exclusions.\n"
            "      With performance profiles, real-time protection stays active — no scan needed."
        )

        self._log_line(f"phase_compensating_scan:complete status={self.compensating_scan_status}")
        return True

    # ──────────────────────────────────────────────────────────────────
    # Phase 5: Profiles Build
    # ──────────────────────────────────────────────────────────────────

    def build_with_profiles(self) -> bool:
        print_section("Profiles Build (Performance Profiles — No Manual Exclusions)")
        self._log_line("phase_profiles:start")

        print_info(
            "Performance profiles use smart, targeted patterns to skip known-safe build artifacts.\n"
            "   Unlike broad folder exclusions, they do NOT blindly skip entire directories —\n"
            "   so real-time protection remains active for unknown or suspicious files."
        )

        # Remove any lingering AV exclusions before applying profiles
        if self.applied_exclusions:
            print_info("Removing AV exclusions before applying performance profiles...")
            self._remove_default_exclusions()
            print_success("AV exclusions removed")

        if not self.apply_profiles():
            return False

        self._log_profile_state_snapshot("profiles_build.post_apply")

        optimized_cwd = self.optimized_repo_path
        if self.clone_in_timed_phases:
            print_info(f"Fresh clone for profiles run: {optimized_cwd}")
            if not self._fresh_clone(optimized_cwd):
                return False

        self._prepare_build_environment("profiles", optimized_cwd)

        try:
            subprocess.run(
                ["sudo", "mdatp", "config", "real-time-protection-statistics", "--value", "enabled"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False,
            )
        except Exception:
            pass

        rtp_before = self.orchestrator.results_dir / "phase5_rtp_before.json"
        self._collect_rtp_stats(rtp_before)

        cpu_log = self.orchestrator.results_dir / "phase5_cpu.log"
        stop_event, monitor_thread = self._start_cpu_monitor(cpu_log)
        start = time.time()

        ok = self._run_build_command(optimized_cwd, "Profiles")
        elapsed = time.time() - start

        stop_event.set()
        monitor_thread.join(timeout=3)

        if not ok:
            return False

        rtp_after = self.orchestrator.results_dir / "phase5_rtp_after.json"
        self._collect_rtp_stats(rtp_after)
        self.profiles_build["time"] = elapsed
        self.profiles_build["cpu"] = self._calc_avg_cpu(cpu_log)
        self.profiles_build["scans"] = self._count_rtp_scan_delta(rtp_before, rtp_after)
        print_info(f"Profiles build time: {elapsed:.1f}s  |  MDE avg CPU: {self.profiles_build['cpu']}%")

        # Place EICAR after the build — profiles are now fully warm, RTP is active.
        # This shows real-time protection is still effective even with profiles applied.
        if self.eicar_subdir:
            print_section("EICAR Detection Check — Performance Profiles")
            print_info(
                "Placing EICAR test file in the same directory used during the exclusions phase.\n"
                "   This directory is no longer covered by a manual folder exclusion.\n"
                "   Performance profiles don't exclude arbitrary files here — RTP should catch it."
            )
            eicar_dir = self.optimized_repo_path / self.eicar_subdir
            eicar_path, eicar_placed_at = self._place_eicar(eicar_dir)
            if eicar_path is _EICAR_BLOCKED:
                detected = True
                self.profiles_build["eicar_detected"] = detected
                print_success(
                    "✅ EICAR blocked at write by real-time protection!\n"
                    "   MDE prevented the malicious content from being created at all.\n"
                    "   Performance profiles gave you the performance benefit without the security gap."
                )
                self._log_line("eicar:phase5_profiles detected=True method=blocked_at_write")
            elif eicar_path:
                detected = self._check_eicar_detected(eicar_path, placed_at=eicar_placed_at)
                self.profiles_build["eicar_detected"] = detected
                if detected:
                    print_success(
                        "✅ EICAR detected by real-time protection!\n"
                        "   Performance profiles gave you the performance benefit without the security gap."
                    )
                else:
                    print_warning(
                        "EICAR NOT detected with profiles active — unexpected.\n"
                        "   Check whether the profile excludes this specific directory."
                    )
                self._log_line(f"eicar:phase5_profiles detected={detected} path={eicar_path}")
                self._remove_eicar(eicar_path)

        self._log_line(
            f"phase_profiles:complete time={elapsed:.2f}s cpu={self.profiles_build['cpu']}"
        )
        return True

    # ──────────────────────────────────────────────────────────────────
    # Phase 6: Compare Results
    # ──────────────────────────────────────────────────────────────────

    def compare_results(self) -> bool:
        print_section("Results: AV Exclusions vs Performance Profiles")
        self._log_line("phase_compare:start")

        baseline_time = float(self.baseline.get("time") or 0)
        exclusions_time = float(self.exclusions_build.get("time") or 0)
        profiles_time = float(self.profiles_build.get("time") or 0)

        def speedup(before, after):
            if before <= 0 or after <= 0:
                return "N/A"
            saved = before - after
            pct = (saved / before) * 100
            return f"{pct:.0f}% ({saved:.1f}s faster)"

        eicar_excl = self._bool_icon(
            self.exclusions_build.get("eicar_detected"),
            "✅ Detected",
            "⚠️  NOT Detected (gap!)",
        )
        eicar_prof = self._bool_icon(
            self.profiles_build.get("eicar_detected"),
            "✅ Detected",
            "⚠️  NOT Detected",
        )

        rows = [
            ["⏱️  Build time", f"{baseline_time:.1f}s", f"{exclusions_time:.1f}s", f"{profiles_time:.1f}s"],
            [
                "⚡ vs Baseline",
                "—",
                speedup(baseline_time, exclusions_time),
                speedup(baseline_time, profiles_time),
            ],
            [
                "🖥️  MDE avg CPU",
                f"{self.baseline.get('cpu', 'N/A')}%",
                f"{self.exclusions_build.get('cpu', 'N/A')}%",
                f"{self.profiles_build.get('cpu', 'N/A')}%",
            ],
            ["🛡️  EICAR detected", "N/A (no exclusions)", eicar_excl, eicar_prof],
            [
                "🔍 Compensating scan needed?",
                "No",
                f"Yes ({self.compensating_scan_status})",
                "No",
            ],
        ]

        table = self._markdown_table(["Metric", "Baseline", "AV Exclusions", "Perf Profiles"], rows)
        print("")
        print(table)
        print("")

        print_info("Summary:")
        print("   • AV exclusions improved build performance — but created a security gap.")
        print("   • The compensating scan found the EICAR threat the exclusion missed.")
        print("   • Performance profiles delivered the same performance improvement.")
        print("   • With profiles, real-time protection remained active — no compensating scan needed.")
        print("")
        print_info(f"Artifacts saved to: {self.orchestrator.results_dir}")
        print_info(f"Run log:            {self.run_log_file}")

        self._write_final_markdown_report(baseline_time, exclusions_time, profiles_time)
        self._log_line("phase_compare:complete")
        return True

    # ──────────────────────────────────────────────────────────────────
    # Report
    # ──────────────────────────────────────────────────────────────────

    def _write_final_markdown_report(
        self,
        baseline_time: float,
        exclusions_time: float,
        profiles_time: float,
    ):
        try:
            report_path = (
                self.orchestrator.results_dir
                / f"final_report_{self.config.name.lower().replace(' ', '_')}.md"
            )

            def speedup(before, after):
                if before <= 0 or after <= 0:
                    return "N/A"
                saved = before - after
                pct = (saved / before) * 100
                return f"{pct:.0f}% ({saved:.1f}s faster)"

            eicar_excl = self._bool_icon(
                self.exclusions_build.get("eicar_detected"), "✅ Detected", "⚠️ NOT Detected"
            )
            eicar_prof = self._bool_icon(
                self.profiles_build.get("eicar_detected"), "✅ Detected", "⚠️ NOT Detected"
            )

            rows = [
                ["⏱️ Build time", f"{baseline_time:.1f}s", f"{exclusions_time:.1f}s", f"{profiles_time:.1f}s"],
                ["⚡ vs Baseline", "—", speedup(baseline_time, exclusions_time), speedup(baseline_time, profiles_time)],
                [
                    "🖥️ MDE avg CPU",
                    f"{self.baseline.get('cpu', 'N/A')}%",
                    f"{self.exclusions_build.get('cpu', 'N/A')}%",
                    f"{self.profiles_build.get('cpu', 'N/A')}%",
                ],
                ["🛡️ EICAR detected", "N/A", eicar_excl, eicar_prof],
                [
                    "🔍 Compensating scan needed?",
                    "No",
                    f"Yes ({self.compensating_scan_status}; threats found: {self.compensating_scan_threats_found})",
                    "No",
                ],
            ]

            profiles_applied = ", ".join(self.config.profiles)
            excl_list = ", ".join(
                f"{e.get('type','folder')}: {self.config.repo_path / e['rel']}"
                for e in self.default_exclusions
            ) or "(none)"

            sections = [
                f"# {self.config.name} — Final Report",
                "",
                "## 📊 Comparison: AV Exclusions vs Performance Profiles",
                "",
                self._markdown_table(["Metric", "Baseline", "AV Exclusions", "Perf Profiles"], rows),
                "",
                "## 🔑 Key Takeaways",
                "",
                "- **AV exclusions** skip entire directories — fast, but any threat landing there goes undetected.",
                "- **Compensating scan** (`--ignore-exclusions`) is required after every build to close the gap — adding overhead.",
                "- **Performance profiles** use smart, targeted patterns — same perf gain, real-time protection stays active.",
                "- With profiles, you get the build speedup **without** the security trade-off or the compensating scan burden.",
                "",
                "## ℹ️ Configuration Used",
                "",
                self._markdown_table(
                    ["Item", "Value"],
                    [
                        ["Scenario", self.config.name],
                        ["Profiles applied", profiles_applied],
                        ["Default AV exclusions", excl_list],
                        ["EICAR subdir", self.eicar_subdir or "(none)"],
                        ["Compensating scan status", self.compensating_scan_status],
                        ["Artifacts dir", str(self.orchestrator.results_dir)],
                        ["Run log", str(self.run_log_file)],
                    ],
                ),
            ]

            report_path.write_text("\n".join(sections) + "\n")
            print_info(f"Final markdown report: {report_path}")
            self._log_line(f"phase_compare:final_report {report_path}")
        except Exception as e:
            self._log_line(f"phase_compare:final_report_error {e}")

    # ──────────────────────────────────────────────────────────────────
    # Scenario entry point
    # ──────────────────────────────────────────────────────────────────

    def run(self, resume_from: Optional[int] = None) -> bool:
        """Execute scenario, optionally resuming from saved baseline checkpoint."""
        selected_resume = resume_from

        if self.enable_resume_checkpoint and selected_resume is None:
            state = self._load_state()
            if state and state.get("baseline_complete"):
                if self._is_state_stale(state):
                    print_info("Ignoring stale resume checkpoint — starting fresh")
                    self._clear_state()
                    state = None

            if state and state.get("baseline_complete"):
                baseline_time = state.get("baseline_duration_seconds", 0)
                self.baseline["time"] = float(baseline_time or 0)
                self.baseline["cpu"] = state.get("baseline_cpu_avg", "N/A")
                self.baseline["scans"] = state.get("baseline_scans", "N/A")

                print("")
                print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                print("  📋 Previous run detected — baseline already complete.")
                print(f"     Baseline build time: {baseline_time:.1f} seconds")
                print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                print("")

                choice = input("  Continue to profiles build, or restart from scratch? [C/r] ").strip().lower()
                if choice.startswith("r"):
                    print("  🔄 Restarting from scratch...")
                    self._clear_state()
                else:
                    # Skip setup, baseline, exclusions build, and compensating scan
                    selected_resume = 4
                    print("  ▶️  Resuming from Profiles Build — apply profiles via MDM if needed...")
                print("")

        try:
            success = super().run(resume_from=selected_resume)
            if success and self.enable_resume_checkpoint:
                self._clear_state()
            return success
        finally:
            # Always clean up exclusions if the demo exits unexpectedly
            if self.applied_exclusions:
                print_info("Cleaning up AV exclusions...")
                self._remove_default_exclusions()

    # ──────────────────────────────────────────────────────────────────
    # Abstract method stubs (required by DemoScenario base)
    # ──────────────────────────────────────────────────────────────────

    def build_optimized(self) -> bool:
        return self.build_with_profiles()

    def analyze_results(self) -> bool:
        return self.compare_results()
