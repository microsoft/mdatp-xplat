"""Data-driven profiled build scenario base.

Provides common phase behavior so concrete scenarios can be mostly
configuration and command data.
"""

from pathlib import Path
from typing import Dict, List, Optional
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from datetime import datetime

from .base import DemoScenario, ScenarioConfig
from ..ui import print_section, print_success, print_error, print_info, print_warning


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
        recommend_keywords: Optional[Dict[str, List[str]]] = None,
        hot_events_analysis_mode: str = "none",
        enable_client_analyzer: bool = False,
        enable_exclusion_workflow: Optional[bool] = None,
        analyzer_dir: Optional[Path] = None,
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
        self.recommend_keywords = dict(recommend_keywords or {})
        self.hot_events_analysis_mode = hot_events_analysis_mode
        self.enable_client_analyzer = enable_client_analyzer
        self.enable_exclusion_workflow = enable_client_analyzer if enable_exclusion_workflow is None else enable_exclusion_workflow
        self.analyzer_dir = analyzer_dir or (Path.home() / "demo" / "analyzer" / "XMDEClientAnalyzerBinary")
        self.enable_resume_checkpoint = enable_resume_checkpoint
        self.profile_change_policy = profile_change_policy
        self.state_file = self.orchestrator.results_dir / state_file_name
        self.run_log_file = self.orchestrator.results_dir / "demo_run.log"
        self.recommended_profiles = list(self.config.profiles or [])
        self.recommendation_source = "default"
        self.hot_event_duration = 60
        self.client_analyzer_last_error = None
        self.client_analyzer_log_file = None
        self.recommended_exclusions = []
        self.applied_temp_exclusions = []
        self.exclusion_recommendation_source = "none"
        self.exclusions_before = []
        self.exclusions_after_optimized = []
        self.exclusions_after_cleanup = []
        self.compensating_scan_started = False
        self.compensating_scan_target = None
        self.compensating_scan_status = "not_run"
        self.compensating_scan_files_scanned = "N/A"
        self.compensating_scan_threats_found = "N/A"
        self.baseline = {
            "time": 0.0,
            "cpu": "N/A",
            "scans": "N/A",
            "profiles_at_start": "(unknown)",
            "client_analyzer": None,
        }
        self.optimized = {"time": 0.0, "cpu": "N/A", "scans": "N/A"}
        self.phase6_hotspot_analysis = ""
        self.phase3_ghcp_analysis = ""

        self.baseline_repo_path = self.config.repo_path
        self.optimized_repo_path = self.config.repo_path
        if self.clone_in_timed_phases:
            self.baseline_repo_path = self.config.repo_path.parent / f"{self.config.repo_path.name}{baseline_repo_suffix}"
            self.optimized_repo_path = self.config.repo_path.parent / f"{self.config.repo_path.name}{optimized_repo_suffix}"

        self._register_phases()

    def _start_run_log(self):
        """Start a new run section in the shared run log file."""
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
        """Append a timestamped line to the run log file."""
        try:
            ts = datetime.now().isoformat(timespec="seconds")
            with self.run_log_file.open("a") as handle:
                handle.write(f"[{ts}] {message}\n")
        except Exception:
            pass

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
        print_info("Collecting MDE performance data...")

        hot_before = self.orchestrator.results_dir / "phase2_hot_events.json"
        hot_before_available = hot_before.exists() and hot_before.stat().st_size > 0

        print_info("Step 1/2: Collect baseline logs")
        if hot_before_available:
            entries = self._load_hot_event_entries(hot_before)
            print_info(f"Hot-event telemetry entries loaded: {len(entries)}")
        else:
            print_info("Hot-event telemetry missing/empty")

        print_info("Client Analyzer logs (optional)")
        self._run_phase3_optional_diagnostics()

        print_info("Step 2/2: Analyze telemetry and choose profiles")
        if hot_before_available:
            self._select_profiles_for_phase4(hot_before)
        else:
            self.recommended_profiles = self._get_available_profiles()
            self.recommendation_source = "default"

        if self.baseline.get("client_analyzer"):
            print_info("Skipping MDE diagnostic bundle export (covered by Client Analyzer output)")
        else:
            print_info("Exporting MDE diagnostic bundle (fallback artifact)")
            try:
                subprocess.run(
                    ["mdatp", "diagnostic", "create", "--folder", str(self.orchestrator.results_dir)],
                    timeout=60,
                    text=True,
                    capture_output=True,
                    check=False,
                )
            except Exception:
                pass

        self._persist_phase3_state()
        print_info(f"Phase 4 will apply ({self.recommendation_source}): {', '.join(self.recommended_profiles)}")
        return True

    def _collect_diagnostics(self) -> bool:
        """Backward-compatible alias for old tests/callers."""
        return self.analyze_baseline_telemetry()

    def _run_phase3_optional_diagnostics(self):
        """Scenario hook for phase 3 optional diagnostics."""
        if not self.enable_client_analyzer:
            print_info("Client Analyzer disabled by configuration; skipping optional logs")
            return None

        print_info("Starting optional Client Analyzer capture (~10s, requires sudo credentials)")
        analyzer_zip = self._run_client_analyzer("phase3")
        if self.client_analyzer_log_file:
            print_info(f"Client Analyzer log: {self.client_analyzer_log_file}")
        if analyzer_zip:
            self.baseline["client_analyzer"] = analyzer_zip
            print_success(f"Client Analyzer report: {analyzer_zip}")
            print_info("Optional diagnostics complete")
        elif self.enable_client_analyzer:
            if self.client_analyzer_last_error:
                print_info(f"Client Analyzer skipped: {self.client_analyzer_last_error}")
            else:
                print_info("Client Analyzer not available (skipping)")
            print_info("Optional diagnostics complete")
        return None

    def _parse_ghcp_exclusion_candidates(self, output_text: str):
        """Parse GHCP exclusion candidates into normalized [{type, value}] entries."""
        if not output_text:
            return []

        parsed = []
        lines = output_text.splitlines()
        raw_tokens = []

        for idx, raw_line in enumerate(lines):
            line = raw_line.strip().strip("*_`")
            heading_match = re.search(r"EXCLUSION[\s_-]*CANDIDATES\s*:\s*(.*)", line, flags=re.IGNORECASE)
            if not heading_match:
                continue

            rhs = heading_match.group(1).strip()
            rhs = re.split(r"\bRECOMMENDED[\s_-]*PROFILES\s*:", rhs, maxsplit=1, flags=re.IGNORECASE)[0].strip()
            if rhs and rhs.lower() != "none":
                raw_tokens.extend([item.strip() for item in re.split(r"[,;]", rhs) if item.strip()])

            for follow in lines[idx + 1 :]:
                follow_line = follow.strip().strip("*_`")
                if not follow_line:
                    if raw_tokens:
                        break
                    continue
                if re.match(r"RECOMMENDED[\s_-]*PROFILES\s*:", follow_line, flags=re.IGNORECASE):
                    break
                if re.match(r"ANALYSIS\s*:", follow_line, flags=re.IGNORECASE):
                    break
                if re.match(r"EXCLUSION[\s_-]*CANDIDATES\s*:", follow_line, flags=re.IGNORECASE):
                    break
                if follow_line.startswith(("-", "*")):
                    raw_tokens.append(follow_line.lstrip("-* ").strip())
                else:
                    raw_tokens.extend([item.strip() for item in re.split(r"[,;]", follow_line) if item.strip()])
            break

        if not raw_tokens:
            return []

        for raw in raw_tokens:
            token = raw.strip().strip("`").strip()
            token = re.sub(r"\bRECOMMENDED[\s_-]*PROFILES\s*:.*$", "", token, flags=re.IGNORECASE).strip()
            token = re.sub(r"\bANALYSIS\s*:.*$", "", token, flags=re.IGNORECASE).strip()
            token_lower = token.lower()
            exclusion_type = "folder"

            if token_lower.startswith("folder:"):
                exclusion_type = "folder"
                token = token.split(":", 1)[1].strip()
            elif token_lower.startswith("file:"):
                exclusion_type = "file"
                token = token.split(":", 1)[1].strip()
            elif token_lower.startswith("process:"):
                exclusion_type = "process"
                token = token.split(":", 1)[1].strip()

            if not token or token.lower() == "none":
                continue
            if token.startswith("<repo>/"):
                token = str(self.config.repo_path / token[len("<repo>/") :])
            elif token.startswith("./"):
                token = str(self.config.repo_path / token[2:])
            elif token.startswith("~"):
                token = os.path.expanduser(token)

            if token.endswith("/") and token != "/":
                token = token.rstrip("/")

            if exclusion_type == "process":
                candidate = {"type": exclusion_type, "value": token}
                if candidate not in parsed:
                    parsed.append(candidate)
                continue

            if not token.startswith("/"):
                continue

            candidate = {"type": exclusion_type, "value": token}
            if candidate not in parsed:
                parsed.append(candidate)

        return parsed[:5]

    def _print_markdown_analysis(self, title: str, text: str, max_lines: int = 40):
        """Render GHCP analysis as Markdown-style text in terminal output."""
        if not text:
            return None

        lines = text.splitlines()
        if max_lines and len(lines) > max_lines:
            text = "\n".join(lines[:max_lines] + ["... (truncated)"])

        try:
            from rich.console import Console
            from rich.markdown import Markdown

            print_info(f"{title} (markdown)")
            console = Console()
            console.print(Markdown(text))
        except Exception:
            print_info(f"{title} (markdown)")
            for line in text.splitlines():
                print(f"   {line}")
        return None

    def _markdown_table(self, headers: List[str], rows: List[List[str]]) -> str:
        """Build a simple GitHub-flavored Markdown table."""
        if not headers:
            return ""

        def escape_cell(value):
            return str(value).replace("|", "\\|")

        lines = [
            "| " + " | ".join(escape_cell(header) for header in headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
        ]
        for row in rows:
            lines.append("| " + " | ".join(escape_cell(cell) for cell in row) + " |")
        return "\n".join(lines)

    def _format_delta(self, after, before) -> str:
        """Format a numeric delta when both values are present."""
        try:
            if after is None or before is None:
                return "N/A"
            return f"{int(after) - int(before):+d}"
        except Exception:
            return "N/A"

    def _percent_change(self, before, after) -> str:
        """Return percent reduction/increase text for numeric before/after values."""
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
        """Return a stable textual summary of active profiles on the endpoint."""
        _, active_applied = self._get_profile_state()
        if not active_applied:
            return "(none detected)"
        active_sorted = sorted([p for p in active_applied if p in self.config.profiles])
        return ", ".join(active_sorted) if active_sorted else "(none detected)"

    def _format_hotspot_analysis_for_report(self, text: str) -> str:
        """Wrap hotspot analysis text for inclusion in the final markdown report."""
        if not text:
            return ""

        lines = ["### 🔎 Hotspots", ""]
        lines.extend(text.splitlines())
        return "\n".join(lines)

    def _confirm_exclusion_change(self, exclusions: List[dict]) -> bool:
        """Apply configured consent policy for temporary exclusion changes."""
        if not exclusions:
            return True

        mode = (self.profile_change_policy or "prompt").lower()
        if mode == "always":
            return True
        if mode == "never":
            print_info("Temporary exclusions cancelled by profile change policy (never)")
            self._log_line("temporary_exclusions:cancelled policy=never")
            return False

        if os.environ.get("PYTEST_CURRENT_TEST"):
            return True

        print_info("This step can apply temporary AV exclusions for the optimized retest:")
        for candidate in exclusions:
            print(f"   - {candidate['type']}: {candidate['value']}")
        answer = input("Proceed to apply temporary exclusions? [Y/n] ").strip().lower()
        return answer not in ("n", "no")

    def _apply_recommended_exclusions(self):
        """Apply recommended AV exclusions temporarily for optimized build retest."""
        if not self.enable_exclusion_workflow:
            print_info("Temporary AV exclusion workflow is disabled")
            return None

        if not self.baseline.get("client_analyzer"):
            print_info("Client Analyzer archive not found; using telemetry/GHCP exclusion candidates only")

        candidates = list(self.recommended_exclusions or [])
        if not candidates:
            print_info("No temporary AV exclusion candidates were recommended")
            return None

        candidate_text = ", ".join([f"{c['type']}:{c['value']}" for c in candidates])

        print_info(
            "Temporary AV exclusion recommendation set "
            f"({self.exclusion_recommendation_source}): "
            f"{candidate_text}"
        )

        if not self._confirm_exclusion_change(candidates):
            print_info("Temporary AV exclusions cancelled by user")
            self._log_line("temporary_exclusions:cancelled user_declined")
            return None

        self.applied_temp_exclusions = []
        for candidate in candidates:
            exclusion_type = candidate.get("type")
            value = candidate.get("value")
            if exclusion_type not in {"folder", "file", "process"} or not value:
                continue

            try:
                result = subprocess.run(
                    ["sudo", "mdatp", "exclusion", exclusion_type, "add", "--path", value],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                if result.returncode == 0:
                    self.applied_temp_exclusions.append({"type": exclusion_type, "value": value})
                    self._log_line(f"temporary_exclusion:add type={exclusion_type} value={value} status=applied")
                    print_success(f"Temporary exclusion applied: {exclusion_type}:{value}")
                else:
                    self._log_line(f"temporary_exclusion:add type={exclusion_type} value={value} status=nonzero")
                    print_info(f"Temporary exclusion not applied: {exclusion_type}:{value}")
            except Exception as e:
                self._log_line(f"temporary_exclusion:add type={exclusion_type} value={value} exception={e}")
                print_info(f"Temporary exclusion error for {exclusion_type}:{value}: {e}")

        return None

    def _cleanup_temporary_exclusions(self):
        """Remove exclusions added by this run so endpoint state is restored."""
        if not self.applied_temp_exclusions:
            return None

        removed = 0
        for candidate in reversed(self.applied_temp_exclusions):
            exclusion_type = candidate.get("type")
            value = candidate.get("value")
            try:
                result = subprocess.run(
                    ["sudo", "mdatp", "exclusion", exclusion_type, "remove", "--path", value],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                if result.returncode == 0:
                    removed += 1
                    self._log_line(f"temporary_exclusion:remove type={exclusion_type} value={value} status=removed")
                else:
                    self._log_line(f"temporary_exclusion:remove type={exclusion_type} value={value} status=nonzero")
            except Exception as e:
                self._log_line(f"temporary_exclusion:remove type={exclusion_type} value={value} exception={e}")
                print_info(f"Temporary exclusion cleanup error for {exclusion_type}:{value}: {e}")

        print_info(f"Temporary AV exclusions removed: {removed}/{len(self.applied_temp_exclusions)}")
        self.applied_temp_exclusions = []
        return None

    def _get_exclusion_snapshot(self) -> List[str]:
        """Return current exclusion entries in a compact, stable text format."""
        commands = [
            ["sudo", "mdatp", "exclusion", "list"],
            ["mdatp", "exclusion", "list"],
        ]
        output = ""
        for command in commands:
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                output = (result.stdout or "").strip()
                if result.returncode == 0 and output:
                    break
            except Exception:
                continue

        if not output:
            return []

        entries = []
        for raw in output.splitlines():
            line = raw.strip()
            if not line:
                continue
            lower = line.lower()
            if lower in {
                "no exclusions",
                "exclusion list is empty",
                "exclusions list is empty",
            }:
                return []
            if line.startswith("===") or line.startswith("---"):
                continue
            entries.append(line)
        return entries

    @staticmethod
    def _format_exclusion_snapshot(entries: List[str]) -> str:
        """Render exclusion entries for summary output."""
        if not entries:
            return "(none)"
        return ", ".join(entries)

    def _run_compensating_scan(self, target: Path):
        """Start a compensating custom scan that ignores exclusions."""
        self.compensating_scan_target = str(target)
        self.compensating_scan_files_scanned = "N/A"
        self.compensating_scan_threats_found = "N/A"
        try:
            result = subprocess.run(
                [
                    "sudo",
                    "mdatp",
                    "scan",
                    "custom",
                    "--path",
                    str(target),
                    "--ignore-exclusions",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode == 0:
                self.compensating_scan_started = True
                self.compensating_scan_status = "started"
                self._collect_compensating_scan_summary()
                self._log_line(f"phase5:compensating_scan started path={target}")
                print_success("Compensating custom scan started (--ignore-exclusions)")
            else:
                self.compensating_scan_started = False
                self.compensating_scan_status = f"failed_exit_{result.returncode}"
                self._log_line(
                    f"phase5:compensating_scan failed path={target} exit={result.returncode} stderr={result.stderr.strip()}"
                )
                print_info("Compensating custom scan did not start (see run log)")
        except Exception as e:
            self.compensating_scan_started = False
            self.compensating_scan_status = "error"
            self._log_line(f"phase5:compensating_scan exception={e}")
            print_info(f"Compensating custom scan error: {e}")
        return None

    def _collect_compensating_scan_summary(self):
        """Best-effort capture of files-scanned and threats-found from scan list output."""
        def _pick_from_entry(entry):
            if not isinstance(entry, dict):
                return None, None

            file_keys = [
                "filesScanned",
                "totalFilesScanned",
                "files_scanned",
                "scannedFiles",
            ]
            threat_keys = [
                "threatsFound",
                "threatCount",
                "malwareFound",
                "threats_found",
            ]

            files = next((entry.get(k) for k in file_keys if entry.get(k) is not None), None)
            threats = next((entry.get(k) for k in threat_keys if entry.get(k) is not None), None)
            return files, threats

        try:
            result = subprocess.run(
                ["mdatp", "scan", "list", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                candidates = []
                if isinstance(data, list):
                    candidates = data
                elif isinstance(data, dict):
                    for key in ["scans", "scanEntries", "items", "data", "value"]:
                        value = data.get(key)
                        if isinstance(value, list):
                            candidates = value
                            break
                    if not candidates:
                        candidates = [data]

                for entry in candidates:
                    files, threats = _pick_from_entry(entry)
                    if files is not None or threats is not None:
                        if files is not None:
                            self.compensating_scan_files_scanned = str(files)
                        if threats is not None:
                            self.compensating_scan_threats_found = str(threats)
                        return None
        except Exception:
            pass

        try:
            result = subprocess.run(
                ["mdatp", "scan", "list"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0 and result.stdout:
                files_match = re.search(r"files\s+scanned\s*[:=]\s*(\d+)", result.stdout, re.IGNORECASE)
                threats_match = re.search(r"threats\s+found\s*[:=]\s*(\d+)", result.stdout, re.IGNORECASE)
                if files_match:
                    self.compensating_scan_files_scanned = files_match.group(1)
                if threats_match:
                    self.compensating_scan_threats_found = threats_match.group(1)
        except Exception:
            pass
        return None

    def _write_final_markdown_report(self, baseline: float, optimized: float):
        """Persist a concise markdown report to the results directory."""
        try:
            speedup_saved = baseline - optimized
            speedup_pct = ((speedup_saved / baseline) * 100) if baseline > 0 else 0
            report_path = self.orchestrator.results_dir / f"final_report_{self.config.name.lower().replace(' ', '_')}.md"
            exclusion_candidates_text = ", ".join(
                [f"{c['type']}:{c['value']}" for c in self.recommended_exclusions]
            ) or "(none)"
            temporary_exclusions_text = ", ".join(
                [f"{c['type']}:{c['value']}" for c in self.applied_temp_exclusions]
            ) or "(none)"
            scan_target = self.optimized_repo_path if self.optimized_repo_path.exists() else self.config.repo_path
            before_agg = self._hot_event_aggregate(self.orchestrator.results_dir / "phase2_hot_events.json")
            after_agg = self._hot_event_aggregate(self.orchestrator.results_dir / "phase5_hot_events.json")
            before_hot_total = (before_agg or {}).get("total")
            after_hot_total = (after_agg or {}).get("total")
            selected_profiles = ", ".join(self.recommended_profiles or self.config.profiles)
            analysis_text = (self.phase3_ghcp_analysis or self.phase6_hotspot_analysis or "(GHCP analysis unavailable)").strip()
            speedup_text = f"{speedup_pct:.0f}% ({speedup_saved:.1f}s saved)"

            summary_rows = [
                ["⏱️ Build time", f"{baseline:.1f}s", f"{optimized:.1f}s", speedup_text],
                [
                    "🖥️ MDE avg CPU",
                    f"{self.baseline.get('cpu', 'N/A')}%",
                    f"{self.optimized.get('cpu', 'N/A')}%",
                    self._percent_change(self.baseline.get("cpu"), self.optimized.get("cpu")),
                ],
                [
                    "📁 Scans",
                    str(self.baseline.get("scans", "N/A")),
                    str(self.optimized.get("scans", "N/A")),
                    self._percent_change(self.baseline.get("scans"), self.optimized.get("scans")),
                ],
                [
                    "⚡ Hot events (total)",
                    str(before_hot_total if before_hot_total is not None else "N/A"),
                    str(after_hot_total if after_hot_total is not None else "N/A"),
                    self._percent_change(before_hot_total, after_hot_total),
                ],
                ["🧩 Profiles applied", self.baseline.get("profiles_at_start", "(unknown)"), self._active_profiles_text(), "N/A"],
                [
                    "🔹 AV exclusions",
                    self._format_exclusion_snapshot(self.exclusions_before),
                    self._format_exclusion_snapshot(self.exclusions_after_optimized),
                    "N/A",
                ],
                ["🧪 Temp exclusions used", "(none)", temporary_exclusions_text, "N/A"],
            ]

            report_sections = [
                f"# {self.config.name} - Final Report",
                "",
                "## 📋 Analysis",
                "",
                "### ℹ️ Summary",
                self._markdown_table(["Metric", "Before", "After", "Impact"], summary_rows),
                "",
                "### 🧠 Analysis",
                analysis_text,
                "",
                "AI caveat: GitHub Copilot recommendations use AI; review all recommendations before applying.",
                "",
                "### 📦 Artifacts",
                self._markdown_table(
                    ["Item", "Value"],
                    [
                        ["📦 Artifacts", str(self.orchestrator.results_dir)],
                        ["📝 Run log", str(self.run_log_file)],
                        ["📊 Client Analyzer (base)", str(self.baseline.get('client_analyzer', '(none)'))],
                        ["📊 Client Analyzer (opt)", str(self.optimized.get('client_analyzer', '(none)'))],
                    ],
                ),
            ]

            report_sections.extend(
                [
                    "",
                    "### ⚠️ SECURITY CAUTION",
                    "Exclusions or performance profiles reduce Defender protection.",
                    "Use exclusions sparingly and keep profile/exclusion scope as narrow as possible.",
                    "Mitigation: run compensating scans after build/retest to reduce supply-chain risk.",
                    "",
                    "### ℹ️ Compensating scan recommendation",
                    f"1. One-time post-build custom scan (ignore exclusions):\n   `sudo mdatp scan custom --path {shlex.quote(str(scan_target))} --ignore-exclusions`",
                    "2. Optional quick scan immediately after custom scan:\n   `sudo mdatp scan quick`",
                    "3. Check scan status and completion:\n   `mdatp scan list`",
                    "",
                    "### 🛡️ Compensating scan status",
                    self._markdown_table(
                        ["Field", "Value"],
                        [
                            ["Status", self.compensating_scan_status],
                            ["Target", self.compensating_scan_target or "(none)"],
                            ["Files scanned", self.compensating_scan_files_scanned],
                            ["Threats found", self.compensating_scan_threats_found],
                        ],
                    ),
                    "",
                    f"*Temporary exclusions applied:* {temporary_exclusions_text}",
                    f"*Exclusion candidates:* {exclusion_candidates_text}",
                    f"*Selected profiles:* {selected_profiles}",
                ]
            )

            report_path.write_text("\n".join(report_sections) + "\n")
            print_info(f"Final markdown report: {report_path}")
            self._log_line(f"phase_analysis:final_report {report_path}")
        except Exception as e:
            self._log_line(f"phase_analysis:final_report_error {e}")
        return None

    def _persist_phase3_state(self):
        """Scenario hook for persisting phase 3 state/checkpoints."""
        if not self.enable_resume_checkpoint:
            return None

        baseline_time = float(self.baseline.get("time") or 0)
        if baseline_time <= 0:
            # Do not keep unusable resume checkpoints that trigger noisy prompts.
            self._clear_state()
            self._log_line("checkpoint:skipped_invalid baseline_duration_seconds<=0")
            return None

        self._save_state(
            {
                "baseline_complete": True,
                "baseline_duration_seconds": baseline_time,
                "baseline_cpu_avg": self.baseline.get("cpu", "N/A"),
                "baseline_scans": self.baseline.get("scans", "N/A"),
                "baseline_client_analyzer": self.baseline.get("client_analyzer"),
                "recommended_profiles": self.recommended_profiles,
                "recommendation_source": self.recommendation_source,
            }
        )
        return None

    def _prepare_build_environment(self, phase: str, cwd: Path):
        """Scenario hook to clean/build prep before baseline/optimized build."""
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
        return None

    def _run_build_command(self, cwd: Path, label: str) -> bool:
        """Run build command in cwd. Scenarios can override for custom steps."""
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

    def _confirm_profile_change(self, action: str, profiles: List[str]) -> bool:
        """Apply configured consent policy for profile removals/applications."""
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

    def _post_analysis_hook(self, before_hot: Path, after_hot: Path):
        """Scenario hook for extra phase 6 analysis output."""
        mode = self.hot_events_analysis_mode

        if mode == "prompt" and not os.environ.get("PYTEST_CURRENT_TEST"):
            mode = self._prompt_hot_events_mode()

        if mode in ("python", "both"):
            self._hot_event_python_summary(before_hot, after_hot)
        if mode in ("ghcp", "both"):
            self._hot_event_ghcp_analysis(before_hot, after_hot)
        return None

    def _prompt_hot_events_mode(self) -> str:
        """Interactively ask the user which hot-event analysis to run."""
        has_ghcp = self._has_ghcp_cli()
        print()
        print("📊 Hot event sources were collected.  Run analysis?")
        options = [
            ("1", "python", "Python heuristic summary (fast, no AI)"),
        ]
        if has_ghcp:
            options.append(("2", "ghcp", "GitHub Copilot CLI analysis (AI-powered)"))
            options.append(("3", "both", "Both Python + GHCP"))
        options.append(("0", "none", "Skip analysis"))

        for key, _, label in options:
            print(f"  {key}) {label}")

        valid = {key: val for key, val, _ in options}
        while True:
            choice = input(f"Choose [{'/'.join(valid.keys())}] (default: 0): ").strip()
            if choice == "":
                return "none"
            if choice in valid:
                return valid[choice]
            print(f"  Please enter one of: {', '.join(valid.keys())}")

    def _run_client_analyzer(self, phase_tag: str = "phase3"):
        """Run XMDE Client Analyzer performance capture if available."""
        if not self.enable_client_analyzer:
            return None

        self.client_analyzer_last_error = None
        self.client_analyzer_log_file = None
        tool = self._client_analyzer_tool()
        if not tool or os.environ.get("PYTEST_CURRENT_TEST"):
            return None

        try:
            sudo_check = subprocess.run(
                ["sudo", "-n", "true"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
            if sudo_check.returncode != 0:
                self.client_analyzer_last_error = "sudo credentials required (run `sudo -v` first)"
                return None

            log_path = self.orchestrator.results_dir / f"{phase_tag}_client_analyzer.log"
            self.client_analyzer_log_file = str(log_path)
            print_info("Running Client Analyzer.....")
            started_at = time.time()
            with log_path.open("w") as log_handle:
                proc = subprocess.Popen(
                    ["sudo", "-n", str(tool), "--bypass-disclaimer", "performance", "--length", "10"],
                    cwd=self.orchestrator.results_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                try:
                    if proc.stdout is not None:
                        for line in proc.stdout:
                            log_handle.write(line)
                            log_handle.flush()
                            sys.stdout.write(line)
                            sys.stdout.flush()
                    run_result = proc.wait(timeout=600)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                    self.client_analyzer_last_error = "client analyzer timed out after 600s"
                    return None
            if run_result != 0:
                self.client_analyzer_last_error = (
                    f"client analyzer failed (exit={run_result}; see {self.client_analyzer_log_file})"
                )
                return None

            archive_hint = None
            try:
                log_text = log_path.read_text(errors="replace")
                match = re.search(r"Archive created at:\s*(\S+\.zip)", log_text)
                if match:
                    archive_hint = Path(match.group(1))
            except Exception:
                archive_hint = None

            zips = sorted(
                [
                    *self.orchestrator.results_dir.glob("MDESupportTool_*.zip"),
                    *self.orchestrator.results_dir.glob("support_tool_output_*.zip"),
                    *self.orchestrator.results_dir.glob("*_output.zip"),
                ],
                key=lambda p: p.stat().st_mtime,
            )

            if not zips and archive_hint and archive_hint.exists():
                copied = self.orchestrator.results_dir / archive_hint.name
                try:
                    shutil.copy2(archive_hint, copied)
                    zips.append(copied)
                except Exception:
                    zips.append(archive_hint)

            if not zips:
                tmp_candidates = []
                for pattern in ("*_output.zip", "support_tool_output_*.zip", "MDESupportTool_*.zip"):
                    for p in Path("/tmp").glob(pattern):
                        try:
                            if p.stat().st_mtime >= (started_at - 120):
                                tmp_candidates.append(p)
                        except Exception:
                            continue
                tmp_candidates = sorted(tmp_candidates, key=lambda p: p.stat().st_mtime)
                if tmp_candidates:
                    newest = tmp_candidates[-1]
                    copied = self.orchestrator.results_dir / newest.name
                    try:
                        shutil.copy2(newest, copied)
                        zips.append(copied)
                    except Exception:
                        zips.append(newest)

            if zips:
                return str(zips[-1])

            self.client_analyzer_last_error = (
                f"client analyzer output archive not found (see {self.client_analyzer_log_file})"
            )
        except Exception:
            self.client_analyzer_last_error = "client analyzer execution failed"
            pass
        return None

    def _load_state(self):
        """Load saved scenario state from disk."""
        if not self.state_file.exists():
            return None
        try:
            return json.loads(self.state_file.read_text())
        except Exception:
            return None

    def _save_state(self, data):
        """Persist scenario state to disk."""
        try:
            if "created_at_epoch" not in data:
                data["created_at_epoch"] = time.time()
            self.state_file.write_text(json.dumps(data, indent=2))
        except Exception:
            pass

    def _clear_state(self):
        """Remove saved scenario state after successful completion."""
        try:
            if self.state_file.exists():
                self.state_file.unlink()
        except Exception:
            pass

    def _is_state_stale(self, state: dict) -> bool:
        """Return True when saved resume state is too old or superseded by completed outputs."""
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

        # Expire interrupted checkpoints after 24h to avoid repeated stale prompts.
        if (time.time() - created_at) > 24 * 3600:
            return True

        # If optimized artifacts exist newer than the checkpoint, a full run likely already happened.
        phase5_marker = self.orchestrator.results_dir / "phase5_hot_events.json"
        if phase5_marker.exists():
            try:
                if phase5_marker.stat().st_mtime >= self.state_file.stat().st_mtime:
                    return True
            except Exception:
                pass

        return False

    def _hot_event_python_summary(self, before: Path, after: Optional[Path] = None):
        """Generate local Python summary for hot event sources."""
        before_entries = self._load_hot_event_entries(before)
        if not before_entries:
            print_info("Hot event source analysis unavailable (before file missing/empty)")
            return

        print_info("Hot event source analysis (Python):")
        print("   Top 10 sources (before profiles):")
        for e in before_entries[:10]:
            print(
                f"   {e['total']:>7} total | auth={e['auth']:>6} notify={e['notify']:>6} | {e['path']}"
            )

        b_auth = sum(e["auth"] for e in before_entries)
        b_notify = sum(e["notify"] for e in before_entries)
        print(f"   Aggregate before: auth={b_auth} notify={b_notify} total={b_auth + b_notify}")

        if after and after.exists():
            after_entries = self._load_hot_event_entries(after)
            if after_entries:
                a_auth = sum(e["auth"] for e in after_entries)
                a_notify = sum(e["notify"] for e in after_entries)
                print(f"   Aggregate after:  auth={a_auth} notify={a_notify} total={a_auth + a_notify}")
                delta = (a_auth + a_notify) - (b_auth + b_notify)
                print(f"   Delta (after-before): {delta:+d} events")

    def _hot_event_ghcp_analysis(self, before: Path, after: Optional[Path] = None):
        """Ask GitHub Copilot CLI for a textual interpretation of hot-event data."""
        if not self._has_ghcp_cli():
            print_info("GH Copilot CLI not detected; skipping GHCP analysis")
            return

        before_entries = self._load_hot_event_entries(before)
        if not before_entries:
            print_info("GHCP analysis skipped (before hot-event file missing/empty)")
            return

        before_top = before_entries[:8]
        before_text = "\n".join(
            [
                f"- total={e['total']} auth={e['auth']} notify={e['notify']} path={e['path']}"
                for e in before_top
            ]
        )

        after_text = "(not available)"
        if after and after.exists():
            after_entries = self._load_hot_event_entries(after)
            after_top = after_entries[:8]
            if after_top:
                after_text = "\n".join(
                    [
                        f"- total={e['total']} auth={e['auth']} notify={e['notify']} path={e['path']}"
                        for e in after_top
                    ]
                )

        prompt = (
            f"Analyze these MDE hot event source summaries from a {self.config.name} build. "
            "Explain likely hotspots and which performance profiles matter most.\n\n"
            f"{self._ghcp_developer_best_practices_context()}\n\n"
            f"Before profiles:\n{before_text}\n\nAfter profiles:\n{after_text}\n"
        )

        print_info("Requesting GH Copilot CLI analysis of hot events...")
        try:
            res = self._run_ghcp_suggest(prompt, timeout=60)
            if res is None:
                return
            text = self._extract_ghcp_assistant_text(res.stdout or "")
            if res.returncode == 0 and text:
                self.phase6_hotspot_analysis = text
                self._print_markdown_analysis("GHCP analysis", text, max_lines=60)
            else:
                print_info("GHCP analysis command did not return usable output")
        except Exception as e:
            print_info(f"GHCP analysis failed: {e}")

    def _fresh_clone(self, target: Path) -> bool:
        """Clone a fresh copy of repository for a timed phase."""
        try:
            if target.exists():
                subprocess.run(["rm", "-rf", str(target)], timeout=60, check=True)

            clone_cmd = ["git", "clone", *self.clone_args, self.config.repo_url, str(target)]
            subprocess.run(
                clone_cmd,
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

    def _log_profile_state_snapshot(self, label: str):
        """Capture raw and parsed profile state for audit logging."""
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
            else:
                self._log_line(f"{label} raw: (empty output)")
        except Exception as e:
            self._log_line(f"{label}: failed to capture profile state ({e})")

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
        """Return True when a working `copilot` CLI binary is available."""
        copilot_bin = shutil.which("copilot")
        if not copilot_bin:
            return False

        try:
            res = subprocess.run(
                [copilot_bin, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                stdin=subprocess.DEVNULL,
                check=False,
            )
            output = (res.stdout or "") + "\n" + (res.stderr or "")
            if res.returncode != 0:
                return False
            if "cannot find github copilot cli" in output.lower():
                return False
            return "github copilot cli" in output.lower()
        except Exception:
            return False

    def _client_analyzer_tool(self) -> Optional[Path]:
        """Return Client Analyzer entrypoint path if available."""
        candidates = [
            self.analyzer_dir / "mde_support_tool.sh",
            self.analyzer_dir / "MDESupportTool",
        ]
        for tool in candidates:
            if tool.exists() and tool.is_file():
                return tool
        return None

    def _has_client_analyzer(self) -> bool:
        """Return True when a supported Client Analyzer entrypoint is present."""
        return self._client_analyzer_tool() is not None

    def _report_optional_capabilities(self):
        """Show optional capability status in setup without blocking the run."""
        if self._has_ghcp_cli():
            print_info("GitHub Copilot CLI: available (optional)")
        else:
            print_info("GitHub Copilot CLI: not available (optional; using python/default recommendations)")

        if self.enable_client_analyzer:
            tool = self._client_analyzer_tool()
            if tool:
                print_info(f"Client Analyzer: available (optional) at {tool}")
            else:
                print_info("Client Analyzer: not available (optional; skipping phase-3 analyzer capture)")

        if self.enable_exclusion_workflow:
            print_info("Temporary AV exclusion workflow: enabled (recommend/apply/retest/remove)")
        else:
            print_info("Temporary AV exclusion workflow: disabled")

    def _run_ghcp_suggest(self, prompt: str, timeout: int = 60):
        """Run Copilot CLI in non-interactive prompt mode with per-call consent."""
        answer = input("Allow GitHub Copilot CLI for this step? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            self._log_line("phase3.ghcp consent=declined")
            print_info("GHCP invocation declined; falling back to python/default behavior")
            return None

        self._log_line("phase3.ghcp consent=accepted")

        return subprocess.run(
            [
                "copilot",
                "-p",
                prompt,
                "--output-format",
                "json",
                "--allow-all-tools",
                "--no-ask-user",
                "--no-color",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            check=False,
        )

    def _extract_ghcp_assistant_text(self, output_text: str) -> str:
        """Extract final assistant content from Copilot JSONL output."""
        if not output_text:
            return ""

        assistant_content = ""
        for raw in output_text.splitlines():
            line = raw.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except Exception:
                continue

            if event.get("type") == "assistant.message":
                data = event.get("data", {})
                content = data.get("content")
                if isinstance(content, str) and content.strip():
                    assistant_content = content.strip()

        return assistant_content

    def _extract_ghcp_analysis(self, output_text: str) -> str:
        """Extract human-readable analysis lines from GHCP output."""
        if not output_text:
            return ""

        lines = []
        for raw in output_text.splitlines():
            line = raw.strip()
            if not line:
                continue
            upper = line.upper()
            if upper.startswith("RECOMMENDED_PROFILES:"):
                continue
            if upper.startswith("EXCLUSION_CANDIDATES:"):
                continue
            if upper.startswith("ANALYSIS:"):
                line = line.split(":", 1)[1].strip()
            lines.append(line)

        return "\n".join(lines)

    def _read_text_from_zip(self, zip_path: Path, member_name: str) -> str:
        """Read a UTF-8-ish text member from a zip archive; return empty when unavailable."""
        try:
            with zipfile.ZipFile(zip_path, "r") as archive:
                with archive.open(member_name) as handle:
                    return handle.read().decode("utf-8", errors="replace")
        except Exception:
            return ""

    def _summarize_client_analyzer_for_ghcp(self) -> str:
        """Build compact analyzer metrics context for GHCP prompts when archive is available."""
        archive_path = self.baseline.get("client_analyzer")
        if not archive_path:
            return ""

        zip_path = Path(str(archive_path))
        if not zip_path.exists() or not zip_path.is_file():
            return ""

        lines: List[str] = []

        top_summary = self._read_text_from_zip(zip_path, "top_summary.txt")
        if top_summary:
            max_cpu = {}
            for raw in top_summary.splitlines():
                line = raw.strip()
                if not line.startswith("{"):
                    continue
                try:
                    obj = json.loads(line)
                    command = str(obj.get("command", ""))
                    cpu = float(obj.get("%CPU", 0) or 0)
                except Exception:
                    continue
                command_lower = command.lower()
                if "wdavdaemon" not in command_lower and "epsext" not in command_lower:
                    continue
                current = max_cpu.get(command, 0.0)
                if cpu > current:
                    max_cpu[command] = cpu
            if max_cpu:
                top_cpu = sorted(max_cpu.items(), key=lambda item: item[1], reverse=True)[:3]
                metric = ", ".join([f"{cmd}={cpu:.1f}%" for cmd, cpu in top_cpu])
                lines.append(f"- Client Analyzer MDE CPU peaks: {metric}")

        rtp_stats = self._read_text_from_zip(zip_path, "rtp_statistics.txt")
        if rtp_stats:
            entries = []
            pid = name = path = None
            files_scanned = scan_ns = 0
            for raw in rtp_stats.splitlines():
                line = raw.strip()
                if line.startswith("Process id:"):
                    pid = line.split(":", 1)[1].strip()
                elif line.startswith("Name:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("Path:"):
                    path = line.split(":", 1)[1].strip().strip('"')
                elif line.startswith("Total files scanned:"):
                    try:
                        files_scanned = int(line.split(":", 1)[1].strip())
                    except Exception:
                        files_scanned = 0
                elif line.startswith("Scan time (ns):"):
                    try:
                        scan_ns = int(re.search(r"(\d+)", line).group(1))
                    except Exception:
                        scan_ns = 0
                elif line.startswith("Status:") and pid is not None:
                    entries.append({"name": name or "Unknown", "path": path or "Unknown", "files": files_scanned})
                    pid = name = path = None
                    files_scanned = scan_ns = 0
            if entries:
                top_entries = sorted(entries, key=lambda item: item["files"], reverse=True)[:3]
                metric = ", ".join([f"{item['name']}({item['files']} files)" for item in top_entries])
                lines.append(f"- RTP top scanned processes: {metric}")

        event_stats = self._read_text_from_zip(zip_path, "mde_event_statistics.txt")
        if event_stats:
            wanted = {
                "Auth event count",
                "AUTH_OPEN",
                "AUTH_READDIR",
                "Blocking open request count",
                "Hold request count",
            }
            found = {}
            for raw in event_stats.splitlines():
                if ":" not in raw:
                    continue
                key, value = raw.split(":", 1)
                key = key.strip()
                if key in wanted:
                    found[key] = value.strip()
            if found:
                metric = ", ".join(
                    [
                        f"auth_events={found.get('Auth event count', 'n/a')}",
                        f"auth_open={found.get('AUTH_OPEN', 'n/a')}",
                        f"auth_readdir={found.get('AUTH_READDIR', 'n/a')}",
                        f"blocking_open={found.get('Blocking open request count', 'n/a')}",
                        f"hold={found.get('Hold request count', 'n/a')}",
                    ]
                )
                lines.append(f"- MDE event counters: {metric}")

        exclusions = self._read_text_from_zip(zip_path, "exclusions.txt")
        if exclusions:
            exclusion_lines = []
            for raw in exclusions.splitlines():
                line = raw.strip()
                if not line or line.startswith("==="):
                    continue
                if line.lower() == "no exclusions":
                    exclusion_lines = []
                    break
                exclusion_lines.append(line)
            if exclusion_lines:
                preview = ", ".join(exclusion_lines[:5])
                if len(exclusion_lines) > 5:
                    preview += ", ..."
                lines.append(f"- Existing AV exclusions: {preview}")
            else:
                lines.append("- Existing AV exclusions: none")

        return "\n".join(lines)

    def _ghcp_developer_best_practices_context(self) -> str:
        """Return prompt context that nudges GHCP toward developer-safe recommendations."""
        guidance = [
            "Developer best-practices constraints:",
            "- Use least-privilege ordering: identify narrow temporary AV exclusion opportunities first.",
            "- Exclusions must be specific (high-churn build outputs/caches/temp paths or explicit build processes).",
            "- Do not suggest broad exclusions (entire repo, home directory, or system paths).",
            "- Respect existing exclusions and suggest only additive deltas when justified by telemetry.",
            "- After exclusion candidates, recommend the minimum performance profiles needed from the available list.",
            "- Tie recommendations to observed telemetry evidence.",
            "- Include a compensating post-build scan recommendation because profiles/exclusions reduce protection.",
        ]
        analyzer = self._summarize_client_analyzer_for_ghcp()
        if analyzer:
            guidance.append("Client Analyzer signal summary:")
            guidance.append(analyzer)
        return "\n".join(guidance)

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
            "performance profiles should be applied using a least-privilege strategy.\n"
            f"Available profiles: {allowed}.\n"
            "Do not run tools or inspect files; use only the provided telemetry.\n"
            f"{self._ghcp_developer_best_practices_context()}\n"
            "Return both of the following:\n"
            "ANALYSIS: <short rationale of hotspots, exclusion candidates, and profile choices>\n"
            "EXCLUSION_CANDIDATES: <comma-separated narrow path/process candidates or none>\n"
            "Then your final machine-readable profile recommendation in this exact line:\n"
            "RECOMMENDED_PROFILES: <comma-separated profile names from the available list>\n"
            f"Hot event sources:\n{top_text}\n"
        )

        try:
            res = self._run_ghcp_suggest(prompt, timeout=60)
            if res is None or res.returncode != 0:
                self.recommended_exclusions = []
                self.exclusion_recommendation_source = "none"
                return []

            output = self._extract_ghcp_assistant_text(res.stdout or "")
            analysis = self._extract_ghcp_analysis(output)
            self.phase3_ghcp_analysis = analysis or ""
            self.recommended_exclusions = self._parse_ghcp_exclusion_candidates(output)
            self.exclusion_recommendation_source = "ghcp" if self.recommended_exclusions else "none"
            if analysis:
                self._print_markdown_analysis("GHCP analysis (phase 3)", analysis, max_lines=40)
            if self.recommended_exclusions:
                print_info(
                    "GHCP temporary exclusion candidates: "
                    + ", ".join([f"{c['type']}:{c['value']}" for c in self.recommended_exclusions])
                )

            return self._parse_ghcp_recommended_profiles(output, allowed_profiles)
        except Exception:
            self.recommended_exclusions = []
            self.exclusion_recommendation_source = "none"
            return []

    def _python_profile_recommendations(self, hot_events: Path, available_profiles: Optional[List[str]] = None) -> List[str]:
        """Derive profile recommendations from hot-event path heuristics."""
        entries = self._load_hot_event_entries(hot_events)
        if not entries or not self.recommend_keywords:
            return []

        allowed = list(available_profiles or self.config.profiles)
        scores = {profile: 0 for profile in allowed}
        for e in entries:
            path_text = str(e.get("path", "")).lower()
            total = self._to_int(e.get("total", 0))
            for profile, words in self.recommend_keywords.items():
                if profile in scores and any(word in path_text for word in words):
                    scores[profile] += total

        ranked = [
            profile for profile, score in sorted(scores.items(), key=lambda item: item[1], reverse=True) if score > 0
        ]
        return ranked

    def _choose_profile_recommendations(
        self,
        ghcp_recs: List[str],
        python_recs: List[str],
        available_profiles: List[str],
    ):
        """Select recommendation set from consolidated recommendation options."""
        allowed = list(available_profiles or self.config.profiles)

        def normalize(items: List[str]) -> List[str]:
            ordered = []
            for profile in allowed:
                if profile in items and profile not in ordered:
                    ordered.append(profile)
            return ordered

        ghcp = normalize(ghcp_recs or [])
        python = normalize(python_recs or [])
        inter = [p for p in allowed if p in ghcp and p in python]
        scenario_default = normalize(self.config.profiles)
        union = []
        for profile in ghcp + python:
            if profile not in union:
                union.append(profile)
        union = normalize(union)

        self._log_line(
            "phase3.recommendations "
            f"ghcp={ghcp} python={python} intersection={inter} union={union} scenario_default={scenario_default}"
        )

        source_label = {
            "ghcp": "GHCP",
            "python": "Python",
            "intersection": "Intersection",
            "union": "Union",
            "scenario-default": "Defaults",
        }
        candidates = []
        if ghcp:
            candidates.append(("ghcp", ghcp))
        if python:
            candidates.append(("python", python))
        if inter:
            candidates.append(("intersection", inter))
        if union:
            candidates.append(("union", union))
        if scenario_default:
            candidates.append(("scenario-default", scenario_default))

        consolidated = []
        for src, profiles in candidates:
            canonical_profiles = normalize(profiles)
            key = tuple(canonical_profiles)
            existing = next((opt for opt in consolidated if opt["key"] == key), None)
            if existing:
                existing["sources"].append(src)
            else:
                consolidated.append(
                    {
                        "key": key,
                        "profiles": canonical_profiles,
                        "sources": [src],
                    }
                )

        if not consolidated:
            selected, source = normalize(allowed), "default"
            self._log_line(f"phase3.recommendations.selected source={source} selected={selected}")
            return selected, source

        if len(consolidated) == 1:
            only = consolidated[0]
            selected = only["profiles"]
            source = "+".join(only["sources"])
            self._log_line(f"phase3.recommendations.selected source={source} selected={selected}")
            return selected, source

        print_info("Recommendation choices (consolidated):")
        for idx, option in enumerate(consolidated, start=1):
            labels = "/".join(source_label.get(src, src) for src in option["sources"])
            print(f"   {idx}) {labels}: {', '.join(option['profiles'])}")

        choice = input(f"Choose recommendation source [1-{len(consolidated)}] (default: 1): ").strip()
        try:
            selected_idx = int(choice) - 1 if choice else 0
        except ValueError:
            selected_idx = 0
        if selected_idx < 0 or selected_idx >= len(consolidated):
            selected_idx = 0

        chosen = consolidated[selected_idx]
        selected = chosen["profiles"]
        source = "+".join(chosen["sources"])

        self._log_line(f"phase3.recommendations.selected source={source} selected={selected}")
        return selected, source

    def _select_profiles_for_phase4(self, hot_events: Path):
        """Choose profile set to apply based on phase 3 telemetry artifacts."""
        available_profiles = self._get_available_profiles()
        python_recs = self._python_profile_recommendations(hot_events, available_profiles)
        ghcp_recs = self._ghcp_profile_recommendations(hot_events, available_profiles)

        selected, source = self._choose_profile_recommendations(
            ghcp_recs,
            python_recs,
            available_profiles,
        )

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

    def _rtp_total_files(self, json_file: Path):
        """Return total scanned files from RTP stats JSON in either legacy or current schema."""
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

    def _count_rtp_scans(self, json_file: Path):
        """Return total scanned files from RTP stats JSON."""
        total = self._rtp_total_files(json_file)
        if total is None:
            return "N/A"
        return str(total)

    def _count_rtp_scan_delta(self, before_file: Path, after_file: Path):
        """Return scanned-file delta across a phase using before/after RTP snapshots."""
        before_total = self._rtp_total_files(before_file)
        after_total = self._rtp_total_files(after_file)
        if before_total is None or after_total is None:
            return "N/A"
        return str(max(0, after_total - before_total))

    def _start_hot_event_collection(self, cwd: Optional[Path] = None):
        """Start hot-event collection to run concurrently with an active build."""
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return None, set()
        try:
            # Always write hot-event JSON files to the results dir, not the source tree.
            output_dir = self.orchestrator.results_dir
            output_dir.mkdir(parents=True, exist_ok=True)
            existing = {str(p.resolve()) for p in output_dir.glob("hot_event_source_*.json")}
            proc = subprocess.Popen(
                [
                    "sudo",
                    "mdatp",
                    "diagnostic",
                    "hot-event-sources",
                    f"--time={self.hot_event_duration}",
                ],
                cwd=output_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return proc, existing
        except Exception:
            return None, set()

    def _finalize_hot_event_collection(self, proc, existing_paths, out_file: Path, cwd: Optional[Path] = None):
        """Stop hot-event capture and persist the newest produced artifact."""
        if proc is None:
            return False
        try:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=2)
            except Exception:
                pass

        scan_dir = self.orchestrator.results_dir
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

        admin_only, applied = self._get_profile_state()
        if admin_only:
            print_info("Merge policy is admin-only. Profiles must be deployed via MDM.")
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

        self._report_optional_capabilities()
        self._log_line("phase_setup:complete")

        return True

    def run(self, resume_from: Optional[int] = None) -> bool:
        """Execute scenario, optionally resuming from saved baseline checkpoint."""
        selected_resume = resume_from
        if self.enable_resume_checkpoint and selected_resume is None:
            state = self._load_state()
            if state and state.get("baseline_complete"):
                if self._is_state_stale(state):
                    print_info("Ignoring stale resume checkpoint and starting fresh")
                    self._clear_state()
                    state = None

            if state and state.get("baseline_complete"):
                baseline_time = state.get("baseline_duration_seconds", 0)
                self.baseline["time"] = float(baseline_time or 0)
                self.baseline["cpu"] = state.get("baseline_cpu_avg", "N/A")
                self.baseline["scans"] = state.get("baseline_scans", "N/A")
                self.baseline["client_analyzer"] = state.get("baseline_client_analyzer")
                recs = state.get("recommended_profiles")
                if isinstance(recs, list) and recs:
                    self.recommended_profiles = [p for p in recs if p in self.config.profiles]
                    self.recommendation_source = state.get("recommendation_source", "saved")

                print("")
                print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                print("  📋 Previous run detected — baseline already complete.")
                print(f"     Baseline build time: {baseline_time:.1f} seconds")
                if self.recommended_profiles:
                    print(
                        f"     Saved phase-4 recommendations ({self.recommendation_source}): "
                        f"{', '.join(self.recommended_profiles)}"
                    )
                print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                print("")

                choice = input("  Continue to comparison build, or restart from scratch? [C/r] ").strip().lower()
                if choice.startswith("r"):
                    print("  🔄 Restarting from scratch...")
                    self._clear_state()
                else:
                    selected_resume = 3
                    print("  ▶️  Resuming — skipping setup, baseline, and diagnostics...")
                print("")

        success = False
        try:
            success = super().run(resume_from=selected_resume)
            if success and self.enable_resume_checkpoint:
                self._clear_state()
            return success
        finally:
            if self.applied_temp_exclusions:
                self._cleanup_temporary_exclusions()

    def build_baseline(self) -> bool:
        print_section("Baseline Build (No Profiles)")
        print_info(f"Running baseline for {self.config.name}...")
        self._log_line("phase_baseline:start")
        self._log_profile_state_snapshot("baseline.pre_remove")

        # Remove both currently applied profiles and scenario-available profiles
        # to guarantee a globally clean baseline, including cross-scenario residue
        # (for example, xcode while running vscode).
        _, currently_applied = self._get_profile_state()
        removable_profiles = sorted(set(self._get_available_profiles()) | set(currently_applied))
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
                self._log_line(f"baseline.remove_attempt profile={profile}")
            except Exception:
                self._log_line(f"baseline.remove_attempt profile={profile} exception")
                pass

        self._log_profile_state_snapshot("baseline.post_remove")

        _, applied = self._get_profile_state()
        residual = sorted(set(applied))
        self._log_line(f"baseline.guard residual_profiles={residual}")
        if residual:
            print_error("Baseline is not clean: some demo profiles are still applied")
            for profile in residual:
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

        rtp_before = self.orchestrator.results_dir / "phase1_rtp_stats_before.json"
        self._collect_rtp_stats(rtp_before)

        cpu_log = self.orchestrator.results_dir / "phase1_cpu.log"
        hot_before = self.orchestrator.results_dir / "phase2_hot_events.json"
        stop_event, monitor_thread = self._start_cpu_monitor(cpu_log)
        hes_proc, hes_existing = self._start_hot_event_collection(cwd=baseline_cwd)
        start = time.time()

        ok = self._run_build_command(baseline_cwd, "Baseline")
        elapsed = time.time() - start

        stop_event.set()
        monitor_thread.join(timeout=3)
        self._finalize_hot_event_collection(hes_proc, hes_existing, hot_before, cwd=baseline_cwd)

        if not ok:
            return False

        self.baseline["time"] = elapsed
        self.baseline["cpu"] = self._calc_avg_cpu(cpu_log)
        rtp_file = self.orchestrator.results_dir / "phase1_rtp_stats.json"
        self._collect_rtp_stats(rtp_file)
        self.baseline["scans"] = self._count_rtp_scan_delta(rtp_before, rtp_file)
        self._log_line(
            f"phase_baseline:complete time={elapsed:.2f}s cpu={self.baseline['cpu']} scans={self.baseline['scans']}"
        )

        return True

    def apply_profiles(self) -> bool:
        print_section("Applying Profiles")
        self._log_line("phase_apply_profiles:start")

        selected = self.recommended_profiles or list(self.config.profiles)
        print_info(f"Selected profile set ({self.recommendation_source}): {', '.join(selected)}")
        print_warning("SECURITY CAUTION: Applying profiles or exclusions can reduce Defender protection")
        print("   Use least privilege and review all recommendations before applying changes.")

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

        if not self._confirm_profile_change("apply", selected):
            print_info("Profile application cancelled by user")
            self._log_line("phase_apply_profiles:cancelled profile_apply_declined")
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

        self.exclusions_before = self._get_exclusion_snapshot()
        self._log_line(f"temporary_exclusions:before {self.exclusions_before}")
        self._apply_recommended_exclusions()

        self._log_profile_state_snapshot("apply_profiles.post_apply")
        self._log_line("phase_apply_profiles:complete")
        return True

    def build_optimized(self) -> bool:
        print_section("Optimized Build (With Profiles)")
        print_info(f"Running optimized build for {self.config.name}...")
        self._log_line("phase_optimized:start")

        optimized_cwd = self.optimized_repo_path
        if self.clone_in_timed_phases:
            print_info(f"Fresh clone for optimized run: {optimized_cwd}")
            if not self._fresh_clone(optimized_cwd):
                return False

        self._prepare_build_environment("optimized", optimized_cwd)

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

        rtp_before = self.orchestrator.results_dir / "phase5_rtp_stats_before.json"
        self._collect_rtp_stats(rtp_before)

        cpu_log = self.orchestrator.results_dir / "phase5_cpu.log"
        hot_after = self.orchestrator.results_dir / "phase5_hot_events.json"
        stop_event, monitor_thread = self._start_cpu_monitor(cpu_log)
        hes_proc, hes_existing = self._start_hot_event_collection(cwd=optimized_cwd)
        start = time.time()

        ok = self._run_build_command(optimized_cwd, "Optimized")
        elapsed = time.time() - start

        stop_event.set()
        monitor_thread.join(timeout=3)
        self._finalize_hot_event_collection(hes_proc, hes_existing, hot_after, cwd=optimized_cwd)

        if not ok:
            return False

        self.optimized["time"] = elapsed
        self.optimized["cpu"] = self._calc_avg_cpu(cpu_log)
        rtp_file = self.orchestrator.results_dir / "phase5_rtp_stats.json"
        self._collect_rtp_stats(rtp_file)
        self.optimized["scans"] = self._count_rtp_scan_delta(rtp_before, rtp_file)
        self._log_line(
            f"phase_optimized:complete time={elapsed:.2f}s cpu={self.optimized['cpu']} scans={self.optimized['scans']}"
        )

        scan_target = optimized_cwd if optimized_cwd.exists() else self.config.repo_path
        if self.applied_temp_exclusions:
            print_info("Final step: start compensating custom scan (--ignore-exclusions)")
            self._run_compensating_scan(scan_target)
        else:
            self.compensating_scan_target = str(scan_target)
            self.compensating_scan_status = "skipped_no_temp_exclusions"
            print_info("Final step: skipping compensating custom scan (no temporary AV exclusions were applied)")
            self._log_line("phase_optimized:compensating_scan skipped reason=no_temp_exclusions")

        return True

    def analyze_results(self) -> bool:
        print_section("Analysis")
        self._log_line("phase_analysis:start")

        if self.enable_client_analyzer:
            print_info("Collecting post-optimized Client Analyzer capture (~10s)")
            optimized_analyzer_zip = self._run_client_analyzer("phase6")
            if optimized_analyzer_zip:
                self.optimized["client_analyzer"] = optimized_analyzer_zip
                print_success(f"Post-optimized Client Analyzer report: {optimized_analyzer_zip}")
            elif self.client_analyzer_last_error:
                print_info(f"Post-optimized Client Analyzer skipped: {self.client_analyzer_last_error}")

        baseline = float(self.baseline.get("time") or 0)
        optimized = float(self.optimized.get("time") or 0)

        print_info("Comparison summary:")
        print(f"   ⏱️  Baseline build time:   {baseline:.1f}s")
        print(f"   ⏱️  Optimized build time:  {optimized:.1f}s")
        print(f"   🖥️  Baseline MDE avg CPU:  {self.baseline.get('cpu', 'N/A')}%")
        print(f"   🖥️  Optimized MDE avg CPU: {self.optimized.get('cpu', 'N/A')}%")
        print(f"   📁 Baseline scans:        {self.baseline.get('scans', 'N/A')}")
        print(f"   📁 Optimized scans:       {self.optimized.get('scans', 'N/A')}")
        saved = baseline - optimized
        speedup = ((saved / baseline) * 100) if baseline > 0 else 0
        print(f"   ⚡ Speedup:               {speedup:.0f}% ({saved:.1f}s saved)")
        print(f"   📦 Artifacts:             {self.orchestrator.results_dir}")
        print(f"   📝 Run log:               {self.run_log_file}")
        if self.baseline.get("client_analyzer"):
            print(f"   📊 Client Analyzer (base): {self.baseline.get('client_analyzer')}")
        if self.optimized.get("client_analyzer"):
            print(f"   📊 Client Analyzer (opt):  {self.optimized.get('client_analyzer')}")
        if self.recommended_exclusions:
            exclusions = ", ".join([f"{c['type']}:{c['value']}" for c in self.recommended_exclusions])
            print(f"   🧩 Exclusion candidates:  {exclusions}")
        if self.applied_temp_exclusions:
            applied = ", ".join([f"{c['type']}:{c['value']}" for c in self.applied_temp_exclusions])
            print(f"   🧪 Temp exclusions used:  {applied}")

        self.exclusions_after_optimized = self._get_exclusion_snapshot()
        before_text = self._format_exclusion_snapshot(self.exclusions_before)
        after_opt_text = self._format_exclusion_snapshot(self.exclusions_after_optimized)
        print_info("AV exclusions snapshot:")
        print(f"   🔹 Before apply:          {before_text}")
        print(f"   🔹 After optimized run:   {after_opt_text}")

        print_info("Profiles applied:")
        print(f"   📌 Requested apply set:  {', '.join(self.recommended_profiles or self.config.profiles)}")
        print(f"   📌 Recommendation source: {self.recommendation_source}")
        print(f"   📌 Selected profiles:     {', '.join(self.recommended_profiles or self.config.profiles)}")
        print(f"   📌 Baseline start state:  {self.baseline.get('profiles_at_start', '(unknown)')}")
        _, active_applied = self._get_profile_state()
        if active_applied:
            active_sorted = sorted([p for p in active_applied if p in self.config.profiles])
            print(f"   ✅ Active on endpoint:    {', '.join(active_sorted)}")
        else:
            print("   ✅ Active on endpoint:    (none detected)")

        selected_profiles = self.recommended_profiles or self.config.profiles
        risk_triggered = bool(selected_profiles or self.exclusions_after_optimized or self.applied_temp_exclusions)
        if risk_triggered:
            print_warning("SECURITY CAUTION: Exclusions or performance profiles reduce Defender protection")
            print("   Use exclusions sparingly and keep profile/exclusion scope as narrow as possible.")
            print("   Mitigation: run compensating scans after build/retest to reduce supply-chain risk.")
            print_info("AI notice: GitHub Copilot recommendations use AI; review all recommendations before applying")

            scan_target = self.optimized_repo_path if self.optimized_repo_path.exists() else self.config.repo_path
            quoted_target = shlex.quote(str(scan_target))
            print_info("Compensating scan recommendation:")
            print("   1) One-time post-build custom scan (ignore exclusions):")
            print(f"      sudo mdatp scan custom --path {quoted_target} --ignore-exclusions")
            print("   2) Optional quick scan immediately after custom scan:")
            print("      sudo mdatp scan quick")
            print("   3) Check scan status and completion:")
            print("      mdatp scan list")
            self._log_line(f"phase_analysis:compensating_scan path={scan_target}")

        if self.compensating_scan_status:
            print_info("Compensating scan status:")
            print(f"   Status:                {self.compensating_scan_status}")
            print(f"   Files scanned:         {self.compensating_scan_files_scanned}")
            print(f"   Threats found:         {self.compensating_scan_threats_found}")

        before_hot = self.orchestrator.results_dir / "phase2_hot_events.json"
        after_hot = self.orchestrator.results_dir / "phase5_hot_events.json"
        before_agg = self._hot_event_aggregate(before_hot)
        after_agg = self._hot_event_aggregate(after_hot)

        print_info("Hot event sources (aggregate):")
        if before_agg:
            print(
                "   Aggregate before: "
                f"auth={before_agg['auth']} notify={before_agg['notify']} total={before_agg['total']}"
            )
        else:
            print("   Aggregate before: unavailable")

        if after_agg:
            print(
                "   Aggregate after:  "
                f"auth={after_agg['auth']} notify={after_agg['notify']} total={after_agg['total']}"
            )
        else:
            print("   Aggregate after:  unavailable")

        if before_agg and after_agg:
            delta_events = after_agg["total"] - before_agg["total"]
            print(f"   Delta (after-before): {delta_events:+d} events")
            self._log_line(
                f"phase_analysis:hot_events before={before_agg['total']} after={after_agg['total']} delta={delta_events:+d}"
            )

        self._post_analysis_hook(before_hot, after_hot)

        self._log_line(
            "phase_analysis:summary "
            f"baseline_time={baseline:.2f}s optimized_time={optimized:.2f}s "
            f"baseline_cpu={self.baseline.get('cpu', 'N/A')} optimized_cpu={self.optimized.get('cpu', 'N/A')} "
            f"selected_profiles={self.recommended_profiles or self.config.profiles} source={self.recommendation_source}"
        )
        self._log_line(
            "phase_analysis:exclusions "
            f"before={self.exclusions_before} after_optimized={self.exclusions_after_optimized}"
        )

        self._cleanup_temporary_exclusions()
        self.exclusions_after_cleanup = self._get_exclusion_snapshot()
        after_cleanup_text = self._format_exclusion_snapshot(self.exclusions_after_cleanup)
        print(f"   🔹 After cleanup:         {after_cleanup_text}")
        self._log_line(f"phase_analysis:exclusions_after_cleanup {self.exclusions_after_cleanup}")

        self._write_final_markdown_report(baseline, optimized)

        print_success("Analysis complete")
        self._log_line("phase_analysis:complete")
        return True
