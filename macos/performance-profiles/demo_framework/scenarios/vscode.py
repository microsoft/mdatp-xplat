"""
VS Code build demo scenario.

Shows the impact of MDE performance profiles on the Microsoft VS Code build process.
"""

from pathlib import Path
from typing import Optional, List
import json
import os
import shutil
import subprocess
import time

from .base import ScenarioConfig
from .profiled_build import ProfiledBuildScenario
from ..ui import print_section, print_success, print_error, print_info


class VSCodeScenario(ProfiledBuildScenario):
    """Demo scenario for building Microsoft VS Code."""

    def __init__(
        self,
        repo_path: Optional[Path] = None,
        include_install_in_build: bool = False,
        hot_events_analysis_mode: str = "prompt",
    ):
        config = ScenarioConfig(
            name="Microsoft VS Code Build Demo",
            description="End-to-end demo showing MDE impact on VS Code compilation",
            repo_url="https://github.com/microsoft/vscode.git",
            repo_path=repo_path or (Path.home() / "demo" / "vscode"),
            build_command="npm run compile",
            profiles=["node", "git", "vscode", "vscode-tree"],
            estimated_duration_minutes=60
        )
        super().__init__(
            config=config,
            build_command=["npm", "run", "compile"],
            tool_checks=[],
            repo_validation_file=None,
            clone_in_timed_phases=False,
        )
        self.include_install_in_build = include_install_in_build
        self.hot_events_analysis_mode = hot_events_analysis_mode
        self.admin_only = False
        self.hot_event_duration = 60
        self.analyzer_dir = Path.home() / "demo" / "analyzer" / "XMDEClientAnalyzerBinary"
        self.state_file = self.orchestrator.results_dir / ".vscode-demo-state.json"
        self.baseline = {"time": 0.0, "cpu": "N/A", "scans": "N/A", "client_analyzer": None}
        self.optimized = {"time": 0.0, "cpu": "N/A", "scans": "N/A"}
        self.recommended_profiles = None
        self.recommendation_source = "default"

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
            "Analyze these MDE hot event source summaries from a VS Code build. "
            "Explain likely hotspots and which performance profiles matter most.\n\n"
            f"Before profiles:\n{before_text}\n\nAfter profiles:\n{after_text}\n"
        )

        print_info("Requesting GH Copilot CLI analysis of hot events...")
        try:
            cmd = ["gh", "copilot", "suggest", "-t", "shell", prompt]
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                print("   GHCP analysis:")
                for line in res.stdout.strip().splitlines()[:40]:
                    print(f"   {line}")
            else:
                print_info("GHCP analysis command did not return usable output")
        except Exception as e:
            print_info(f"GHCP analysis failed: {e}")

    def _python_profile_recommendations(self, hot_events: Path, available_profiles: Optional[List[str]] = None) -> List[str]:
        """Derive profile recommendations from hot-event path heuristics."""
        entries = self._load_hot_event_entries(hot_events)
        if not entries:
            return []

        allowed = list(available_profiles or self.config.profiles)

        keyword_map = {
            "node": ["node", "npm", "pnpm", "yarn", "electron"],
            "git": ["/git", "git-core", "git "],
            "vscode": ["code", "vscode", "typescript", "tsserver", "webpack", "esbuild", "ripgrep", "/rg"],
            "vscode-tree": ["fsevent", "chokidar", "watcher", "tree", "explorer", "filewatch"],
        }

        scores = {profile: 0 for profile in allowed}
        for e in entries:
            path_text = str(e.get("path", "")).lower()
            total = self._to_int(e.get("total", 0))
            for profile, words in keyword_map.items():
                if profile in scores and any(word in path_text for word in words):
                    scores[profile] += total

        ranked = [
            profile for profile, score in sorted(scores.items(), key=lambda item: item[1], reverse=True) if score > 0
        ]
        return ranked

    def _clean_build(self):
        """Clean build artifacts to keep before/after runs comparable."""
        cache_dir = self.config.repo_path / "node_modules" / ".cache"
        out_dir = self.config.repo_path / "out"
        build_dir = self.config.repo_path / ".build"
        for d in (cache_dir, out_dir, build_dir):
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)

        for tsinfo in self.config.repo_path.rglob("*.tsbuildinfo"):
            try:
                tsinfo.unlink()
            except Exception:
                pass

    def _collect_hot_event_sources(self, out_file: Path):
        """Collect hot event sources during a build and persist latest report."""
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return False
        try:
            print_info(
                f"Collecting hot event sources (~{self.hot_event_duration}s) while running an additional compile..."
            )
            self._clean_build()

            hes_proc = subprocess.Popen(
                [
                    "sudo",
                    "mdatp",
                    "diagnostic",
                    "hot-event-sources",
                    f"--time={self.hot_event_duration}",
                ],
                cwd=self.config.repo_path,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            build_proc = subprocess.Popen(
                ["npm", "run", "compile"],
                cwd=self.config.repo_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            build_proc.wait(timeout=3600)
            hes_proc.wait(timeout=self.hot_event_duration + 20)

            candidates = sorted(self.config.repo_path.glob("hot_event_source_*.json"), key=lambda p: p.stat().st_mtime)
            if candidates:
                shutil.copy2(candidates[-1], out_file)
                return True
        except Exception:
            pass
        return False

    def _run_client_analyzer(self):
        """Run XMDE Client Analyzer performance capture if available."""
        tool = self.analyzer_dir / "MDESupportTool"
        if not tool.exists() or os.environ.get("PYTEST_CURRENT_TEST"):
            return None

        try:
            subprocess.run(
                ["sudo", str(tool), "performance", "--length", "10"],
                cwd=self.orchestrator.results_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=600,
                check=False,
            )
            zips = sorted(self.orchestrator.results_dir.glob("MDESupportTool_*.zip"), key=lambda p: p.stat().st_mtime)
            if zips:
                return str(zips[-1])
        except Exception:
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

    def run(self, resume_from: Optional[int] = None) -> bool:
        """Execute scenario with checkpoint-aware resume behavior."""
        selected_resume = resume_from
        if selected_resume is None:
            state = self._load_state()
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

        success = super().run(resume_from=selected_resume)
        if success:
            self._clear_state()
        return success

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

        self.admin_only, _ = self._get_profile_state()
        if self.admin_only:
            print_info("Merge policy is admin-only. Profiles must be deployed via MDM.")
            _, applied = self._get_profile_state()
            applied_required = sorted(set(self.config.profiles) & set(applied))
            if applied_required:
                print_error("Admin-only mode has required profiles already applied")
                print_info("This run needs a clean baseline with no demo profiles.")
                print_info("Ask your IT admin to remove these before baseline:")
                for profile in applied_required:
                    print(f"   - {profile}")
                return False

        if self.include_install_in_build:
            print_info("Dependency install is included in timed build phases")
        else:
            print_info("Running npm install (setup phase)...")
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

        self._clean_build()

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
        
        # Remove active demo profiles for clean baseline when allowed.
        if not self.admin_only:
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
        else:
            print_info("Admin-only mode: skipping local profile removal")

        # Hard guard: baseline must run with no demo profiles applied.
        _, applied_before_build = self._get_profile_state()
        residual = sorted(set(self.config.profiles) & set(applied_before_build))
        if residual:
            print_error("Baseline is not clean: some demo profiles are still applied")
            print_info("Remove these profiles and re-run baseline:")
            for profile in residual:
                print(f"   - {profile}")
            return False

        self.baseline["profiles_at_start"] = "(none)"
        print_info("Baseline profile state: no demo profiles applied")

        cpu_log = self.orchestrator.results_dir / "phase1_cpu.log"
        hot_before = self.orchestrator.results_dir / "phase2_hot_events.json"
        stop_event, monitor_thread = self._start_cpu_monitor(cpu_log)
        hes_proc, hes_existing = self._start_hot_event_collection()
        start = time.time()

        # Run build
        try:
            if self.include_install_in_build:
                install_result = subprocess.run(
                    ["npm", "install"],
                    cwd=self.config.repo_path,
                    timeout=900
                )
                if install_result.returncode != 0:
                    print_error("Baseline dependency install failed")
                    self._finalize_hot_event_collection(hes_proc, hes_existing, hot_before)
                    return False

            result = subprocess.run(
                ["npm", "run", "compile"],
                cwd=self.config.repo_path,
                timeout=1800
            )
            if result.returncode != 0:
                print_error("Baseline build failed")
                stop_event.set()
                monitor_thread.join(timeout=3)
                self._finalize_hot_event_collection(hes_proc, hes_existing, hot_before)
                return False

            stop_event.set()
            monitor_thread.join(timeout=3)

            elapsed = time.time() - start
            self.baseline["time"] = elapsed
            self.baseline["cpu"] = self._calc_avg_cpu(cpu_log)
            rtp_file = self.orchestrator.results_dir / "phase1_rtp_stats.json"
            self._collect_rtp_stats(rtp_file)
            self.baseline["scans"] = self._count_rtp_scans(rtp_file)

            if self._finalize_hot_event_collection(hes_proc, hes_existing, hot_before):
                print_success(f"Hot event sources saved: {hot_before}")
            else:
                print_info("Hot event sources were not captured during baseline compile")

            print_info(f"Baseline time: {elapsed:.1f}s, MDE avg CPU: {self.baseline['cpu']}%")
            print_success("Baseline build completed")
            return True
        except subprocess.TimeoutExpired:
            stop_event.set()
            monitor_thread.join(timeout=3)
            self._finalize_hot_event_collection(hes_proc, hes_existing, hot_before)
            print_error("Build timed out")
            return False

    def apply_profiles(self) -> bool:
        """Apply performance profiles."""
        print_section("Applying Profiles")

        selected_profiles = self.recommended_profiles or list(self.config.profiles)
        print_info(f"Selected profile set ({self.recommendation_source}): {', '.join(selected_profiles)}")

        admin_only, applied = self._get_profile_state()
        required = set(selected_profiles)

        if admin_only:
            missing = sorted(required - applied)
            if missing:
                print_error("Admin-only policy detected: profiles cannot be applied locally")
                print_info("Ask your IT admin to deploy these profiles via MDM, then re-run:")
                for profile in missing:
                    print(f"   - {profile}")
                return False

            print_success("Admin-only mode: required profiles are already deployed via MDM")
            return True
        
        for profile in selected_profiles:
            print_info(f"Applying profile: {profile}...")
            try:
                result = subprocess.run(
                    ["sudo", "mdatp", "performance-profiles", "apply", "--name", profile],
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

        self._clean_build()

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

        cpu_log = self.orchestrator.results_dir / "phase5_cpu.log"
        hot_after = self.orchestrator.results_dir / "phase5_hot_events.json"
        stop_event, monitor_thread = self._start_cpu_monitor(cpu_log)
        hes_proc, hes_existing = self._start_hot_event_collection()
        start = time.time()
        
        try:
            if self.include_install_in_build:
                install_result = subprocess.run(
                    ["npm", "install"],
                    cwd=self.config.repo_path,
                    timeout=900
                )
                if install_result.returncode != 0:
                    print_error("Optimized dependency install failed")
                    self._finalize_hot_event_collection(hes_proc, hes_existing, hot_after)
                    return False

            result = subprocess.run(
                ["npm", "run", "compile"],
                cwd=self.config.repo_path,
                timeout=1800
            )
            if result.returncode != 0:
                print_error("Optimized build failed")
                stop_event.set()
                monitor_thread.join(timeout=3)
                self._finalize_hot_event_collection(hes_proc, hes_existing, hot_after)
                return False

            stop_event.set()
            monitor_thread.join(timeout=3)

            elapsed = time.time() - start
            self.optimized["time"] = elapsed
            self.optimized["cpu"] = self._calc_avg_cpu(cpu_log)
            rtp_file = self.orchestrator.results_dir / "phase5_rtp_stats.json"
            self._collect_rtp_stats(rtp_file)
            self.optimized["scans"] = self._count_rtp_scans(rtp_file)
            if self._finalize_hot_event_collection(hes_proc, hes_existing, hot_after):
                print_success(f"Hot event sources saved: {hot_after}")
            else:
                print_info("Hot event sources were not captured during optimized compile")

            print_info(f"Optimized time: {elapsed:.1f}s, MDE avg CPU: {self.optimized['cpu']}%")
            print_success("Optimized build completed")
            return True
        except subprocess.TimeoutExpired:
            stop_event.set()
            monitor_thread.join(timeout=3)
            self._finalize_hot_event_collection(hes_proc, hes_existing, hot_after)
            print_error("Build timed out")
            return False

    def analyze_results(self) -> bool:
        """Analyze impact of profiles."""
        print_section("Analysis")

        baseline_time = float(self.baseline.get("time") or 0)
        optimized_time = float(self.optimized.get("time") or 0)
        speedup = "?"
        saved = 0.0
        if baseline_time > 0 and optimized_time > 0:
            saved = baseline_time - optimized_time
            speedup = f"{((saved / baseline_time) * 100):.0f}"

        print_info("Comparison summary:")
        print(f"   ⏱️  Baseline build time:   {baseline_time:.1f}s")
        print(f"   ⏱️  Optimized build time:  {optimized_time:.1f}s")
        print(f"   🖥️  Baseline MDE avg CPU:  {self.baseline.get('cpu', 'N/A')}%")
        print(f"   🖥️  Optimized MDE avg CPU: {self.optimized.get('cpu', 'N/A')}%")
        print(f"   📁 Baseline scans:        {self.baseline.get('scans', 'N/A')}")
        print(f"   📁 Optimized scans:       {self.optimized.get('scans', 'N/A')}")
        print(f"   ⚡ Speedup:               {speedup}% ({saved:.1f}s saved)")
        print(f"   📦 Artifacts:             {self.orchestrator.results_dir}")
        if self.baseline.get("client_analyzer"):
            print(f"   📊 Client Analyzer:       {self.baseline.get('client_analyzer')}")

        print_info("Profiles applied:")
        selected_profiles = self.recommended_profiles or list(self.config.profiles)
        print(f"   📌 Recommendation source: {self.recommendation_source}")
        print(f"   📌 Selected profiles:     {', '.join(selected_profiles)}")
        print(f"   📌 Baseline start state:  {self.baseline.get('profiles_at_start', '(unknown)')}")
        _, active_applied = self._get_profile_state()
        if active_applied:
            active_sorted = sorted([p for p in active_applied if p in self.config.profiles])
            print(f"   ✅ Active on endpoint:    {', '.join(active_sorted)}")
        else:
            print("   ✅ Active on endpoint:    (none detected)")

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

        mode = self.hot_events_analysis_mode
        if mode in ("ghcp", "both"):
            self._hot_event_ghcp_analysis(before_hot, after_hot)

        print_success("Analysis complete")
        return True

    def analyze_baseline_telemetry(self) -> bool:
        """Common phase 3 implementation: analyze baseline telemetry and persist diagnostics."""
        print_section("Analyze Baseline Telemetry")
        print_info("Collecting MDE performance data...")

        hot_before = self.orchestrator.results_dir / "phase2_hot_events.json"
        print_info("Step 1/3: Analyze baseline hot-event telemetry")
        if hot_before.exists() and hot_before.stat().st_size > 0:
            self._select_profiles_for_phase4(hot_before)
        else:
            print_info("No baseline hot-event telemetry found; using default available profile set")
            self.recommended_profiles = self._get_available_profiles()
            self.recommendation_source = "default"
            print_info(f"Phase 4 will apply ({self.recommendation_source}): {', '.join(self.recommended_profiles)}")

        print_info("Step 2/3: Client Analyzer performance capture (optional)")
        analyzer_zip = self._run_client_analyzer()
        if analyzer_zip:
            self.baseline["client_analyzer"] = analyzer_zip
            print_success(f"Client Analyzer report: {analyzer_zip}")
        else:
            print_info("Client Analyzer not available (skipping)")

        print_info("Step 3/3: MDE diagnostic bundle export")
        
        try:
            result = subprocess.run(
                ["mdatp", "diagnostic", "create", "--folder", str(self.orchestrator.results_dir)],
                timeout=60,
                text=True,
                capture_output=True
            )
            self._save_state(
                {
                    "baseline_complete": True,
                    "baseline_duration_seconds": self.baseline.get("time", 0),
                    "baseline_cpu_avg": self.baseline.get("cpu", "N/A"),
                    "baseline_scans": self.baseline.get("scans", "N/A"),
                    "baseline_client_analyzer": self.baseline.get("client_analyzer"),
                    "recommended_profiles": self.recommended_profiles,
                    "recommendation_source": self.recommendation_source,
                }
            )
            print_success("Diagnostics collected")
            return True
        except:
            self._save_state(
                {
                    "baseline_complete": True,
                    "baseline_duration_seconds": self.baseline.get("time", 0),
                    "baseline_cpu_avg": self.baseline.get("cpu", "N/A"),
                    "baseline_scans": self.baseline.get("scans", "N/A"),
                    "baseline_client_analyzer": self.baseline.get("client_analyzer"),
                    "recommended_profiles": self.recommended_profiles,
                    "recommendation_source": self.recommendation_source,
                }
            )
            print_info("Could not collect full diagnostics (this is optional)")
            return True

    def _collect_diagnostics(self) -> bool:
        """Backward-compatible alias for tests still calling old method name."""
        return self.analyze_baseline_telemetry()
