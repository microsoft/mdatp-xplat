"""Tests for schedule_scan module."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


class TestScheduleScan:
    """Test cases for schedule_scan functionality."""

    def test_script_exists(self, scheduler_dir: Path) -> None:
        """Test that the schedule_scan.py script exists."""
        script_path = scheduler_dir / "schedule_scan.py"
        assert script_path.exists(), f"Script not found: {script_path}"

    def test_script_has_shebang(self, scheduler_dir: Path) -> None:
        """Test that the script has a proper shebang."""
        script_path = scheduler_dir / "schedule_scan.py"
        with open(script_path) as f:
            first_line = f.readline()
        assert first_line.startswith("#!"), "Script should have a shebang"
        assert "python" in first_line.lower(), "Shebang should reference python"

    def test_script_syntax(self, scheduler_dir: Path) -> None:
        """Test that the script has valid Python syntax."""
        script_path = scheduler_dir / "schedule_scan.py"
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(script_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_script_imports(self, scheduler_dir: Path) -> None:
        """Test that the script can be imported without errors."""
        import importlib.util

        script_path = scheduler_dir / "schedule_scan.py"
        spec = importlib.util.spec_from_file_location("schedule_scan", script_path)
        assert spec is not None, "Could not create module spec"
        assert spec.loader is not None, "Module spec has no loader"


class TestScheduleUpdate:
    """Test cases for schedule_update functionality."""

    def test_script_exists(self, scheduler_dir: Path) -> None:
        """Test that the schedule_update.py script exists."""
        script_path = scheduler_dir / "schedule_update.py"
        assert script_path.exists(), f"Script not found: {script_path}"

    def test_script_syntax(self, scheduler_dir: Path) -> None:
        """Test that the script has valid Python syntax."""
        script_path = scheduler_dir / "schedule_update.py"
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(script_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"
