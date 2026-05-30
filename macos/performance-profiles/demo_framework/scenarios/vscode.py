"""
VS Code build demo scenario.

Shows the impact of MDE performance profiles on the Microsoft VS Code build process.
"""

from pathlib import Path
from typing import Optional
import json
import os
import shutil
import subprocess
import threading
import time

from .base import DemoScenario, ScenarioConfig
from ..ui import print_section, print_success, print_error, print_info


class VSCodeScenario(DemoScenario):
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
        super().__init__(config)
        self.include_install_in_build = include_install_in_build
        self.hot_events_analysis_mode = hot_events_analysis_mode
        self.admin_only = False
        self.hot_event_duration = 60
        self.analyzer_dir = Path.home() / "demo" / "analyzer" / "XMDEClientAnalyzerBinary"
        self.state_file = self.orchestrator.results_dir / ".vscode-demo-state.json"
        self.baseline = {"time": 0.0, "cpu": "N/A", "scans": "N/A", "client_analyzer": None}
        self.optimized = {"time": 0.0, "cpu": "N/A", "scans": "N/A"}
        self._register_phases()

    def _to_int(self, value):
        """Best-effort int conversion for mixed numeric JSON fields."""
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
                print("")
                print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                print("  📋 Previous run detected — baseline already complete.")
                print(f"     Baseline build time: {baseline_time:.1f} seconds")
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

        cpu_log = self.orchestrator.results_dir / "phase1_cpu.log"
        stop_event, monitor_thread = self._start_cpu_monitor(cpu_log)
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
                return False

            stop_event.set()
            monitor_thread.join(timeout=3)

            elapsed = time.time() - start
            self.baseline["time"] = elapsed
            self.baseline["cpu"] = self._calc_avg_cpu(cpu_log)
            rtp_file = self.orchestrator.results_dir / "phase1_rtp_stats.json"
            self._collect_rtp_stats(rtp_file)
            self.baseline["scans"] = self._count_rtp_scans(rtp_file)

            print_info(f"Baseline time: {elapsed:.1f}s, MDE avg CPU: {self.baseline['cpu']}%")
            print_success("Baseline build completed")
            return True
        except subprocess.TimeoutExpired:
            stop_event.set()
            monitor_thread.join(timeout=3)
            print_error("Build timed out")
            return False

    def apply_profiles(self) -> bool:
        """Apply performance profiles."""
        print_section("Applying Profiles")

        admin_only, applied = self._get_profile_state()
        required = set(self.config.profiles)

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
        
        for profile in self.config.profiles:
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
        stop_event, monitor_thread = self._start_cpu_monitor(cpu_log)
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
                return False

            stop_event.set()
            monitor_thread.join(timeout=3)

            elapsed = time.time() - start
            self.optimized["time"] = elapsed
            self.optimized["cpu"] = self._calc_avg_cpu(cpu_log)
            rtp_file = self.orchestrator.results_dir / "phase5_rtp_stats.json"
            self._collect_rtp_stats(rtp_file)
            self.optimized["scans"] = self._count_rtp_scans(rtp_file)

            hot_after = self.orchestrator.results_dir / "phase5_hot_events.json"
            self._collect_hot_event_sources(hot_after)

            print_info(f"Optimized time: {elapsed:.1f}s, MDE avg CPU: {self.optimized['cpu']}%")
            print_success("Optimized build completed")
            return True
        except subprocess.TimeoutExpired:
            stop_event.set()
            monitor_thread.join(timeout=3)
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

        before_hot = self.orchestrator.results_dir / "phase2_hot_events.json"
        after_hot = self.orchestrator.results_dir / "phase5_hot_events.json"

        mode = self.hot_events_analysis_mode
        if mode == "prompt":
            has_ghcp = self._has_ghcp_cli()
            print_info("Hot event analysis mode:")
            print("   1) Python (local parsing)")
            if has_ghcp:
                print("   2) GHCP CLI")
                print("   3) Both")
                choice = input("   Select [1/2/3] (default: 1): ").strip()
                if choice == "2":
                    mode = "ghcp"
                elif choice == "3":
                    mode = "both"
                else:
                    mode = "python"
            else:
                mode = "python"

        if mode in ("python", "both"):
            self._hot_event_python_summary(before_hot, after_hot)
        if mode in ("ghcp", "both"):
            self._hot_event_ghcp_analysis(before_hot, after_hot)

        print_success("Analysis complete")
        return True

    def _collect_diagnostics(self) -> bool:
        """Collect diagnostic data during baseline."""
        print_section("Diagnostics")
        print_info("Collecting MDE performance data...")
        print_info("Step 1/3: Hot event sources capture (this may take 1-5 minutes)")

        hot_before = self.orchestrator.results_dir / "phase2_hot_events.json"
        if self._collect_hot_event_sources(hot_before):
            print_success(f"Hot event sources saved: {hot_before}")
        else:
            print_info("Hot event sources were not captured")

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
                }
            )
            print_info("Could not collect full diagnostics (this is optional)")
            return True
