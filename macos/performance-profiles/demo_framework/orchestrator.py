"""
Demo orchestration framework for MDE performance profiles.

This module provides the core infrastructure for running demo scenarios,
managing phases, capturing output, and handling user interactions.
"""

import subprocess
import sys
import time
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class PhaseStatus(Enum):
    """Status of a demo phase."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PhaseResult:
    """Result of running a phase."""
    name: str
    status: PhaseStatus
    duration_seconds: float
    output: str
    error: Optional[str] = None


class DemoOrchestrator:
    """Manages the execution of demo phases."""

    def __init__(self, name: str, repo_dir: Optional[Path] = None):
        self.name = name
        self.repo_dir = repo_dir or Path.home() / "demo"
        self.results_dir = Path.home() / "demo" / "results"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.phases: List[Tuple[str, callable]] = []
        self.results: List[PhaseResult] = []
        self._sudo_cached = False

    def add_phase(self, name: str, handler: callable) -> None:
        """Register a phase to run."""
        self.phases.append((name, handler))

    def cache_sudo(self) -> bool:
        """Pre-cache sudo credentials so commands don't hang waiting for password."""
        try:
            print("🔐 Caching sudo credentials (you may be prompted once)...")
            result = subprocess.run(
                ["sudo", "-v"],
                capture_output=True,
                timeout=30,
                text=True
            )
            self._sudo_cached = result.returncode == 0
            return self._sudo_cached
        except subprocess.TimeoutExpired:
            print("⚠️  Sudo prompt timed out")
            return False
        except Exception as e:
            print(f"⚠️  Could not cache sudo: {e}")
            return False

    def run(self, resume_from: Optional[int] = None) -> bool:
        """Execute all phases. Returns True if all succeeded."""
        start_time = time.time()
        
        print(f"\n╔{'═' * 65}╗")
        print(f"║ {self.name:<63} ║")
        print(f"╚{'═' * 65}╝\n")

        for idx, (phase_name, handler) in enumerate(self.phases):
            if resume_from is not None and idx < resume_from:
                print(f"⏭️  Skipping phase {idx + 1}: {phase_name}")
                continue

            phase_start = time.time()
            print(f"\n{'─' * 70}")
            print(f"PHASE {idx + 1}: {phase_name}")
            print(f"{'─' * 70}\n")

            try:
                output = handler()
                duration = time.time() - phase_start
                result = PhaseResult(
                    name=phase_name,
                    status=PhaseStatus.COMPLETED,
                    duration_seconds=duration,
                    output=output or ""
                )
                print(f"✅ Phase {idx + 1} completed in {duration:.1f}s\n")
            except KeyboardInterrupt:
                print("\n⚠️  Interrupted by user")
                return False
            except Exception as e:
                duration = time.time() - phase_start
                result = PhaseResult(
                    name=phase_name,
                    status=PhaseStatus.FAILED,
                    duration_seconds=duration,
                    output="",
                    error=str(e)
                )
                print(f"\n❌ Phase {idx + 1} failed: {e}\n")
                return False

            self.results.append(result)

        total_duration = time.time() - start_time
        print(f"\n{'═' * 70}")
        print(f"✅ All phases completed in {total_duration:.1f}s")
        print(f"{'═' * 70}\n")
        return True

    def summary(self) -> Dict:
        """Generate execution summary."""
        return {
            "name": self.name,
            "total_phases": len(self.results),
            "completed": sum(1 for r in self.results if r.status == PhaseStatus.COMPLETED),
            "failed": sum(1 for r in self.results if r.status == PhaseStatus.FAILED),
            "total_duration": sum(r.duration_seconds for r in self.results),
            "results": self.results
        }


class CommandRunner:
    """Execute shell commands with output capture and error handling."""

    @staticmethod
    def run(
        command: List[str],
        cwd: Optional[Path] = None,
        capture: bool = False,
        timeout: Optional[int] = None
    ) -> Tuple[int, str, str]:
        """Run a shell command and return exit code, stdout, stderr."""
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                capture_output=capture,
                text=True,
                timeout=timeout
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return 124, "", "Command timed out"
        except Exception as e:
            return 1, "", str(e)

    @staticmethod
    def run_with_output(
        command: List[str],
        cwd: Optional[Path] = None,
        timeout: Optional[int] = None
    ) -> int:
        """Run command and stream output to console."""
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                timeout=timeout
            )
            return result.returncode
        except subprocess.TimeoutExpired:
            return 124
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
