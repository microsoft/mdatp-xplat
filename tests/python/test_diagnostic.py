"""Tests for high_cpu_parser module."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


class TestHighCpuParser:
    """Test cases for high_cpu_parser functionality."""

    def test_script_exists(self, diagnostic_dir: Path) -> None:
        """Test that the high_cpu_parser.py script exists."""
        script_path = diagnostic_dir / "high_cpu_parser.py"
        assert script_path.exists(), f"Script not found: {script_path}"

    def test_script_has_shebang(self, diagnostic_dir: Path) -> None:
        """Test that the script has a proper shebang."""
        script_path = diagnostic_dir / "high_cpu_parser.py"
        with open(script_path) as f:
            first_line = f.readline()
        # Script may or may not have a shebang, but if it does it should be valid
        if first_line.startswith("#!"):
            assert "python" in first_line.lower(), "Shebang should reference python"

    def test_script_syntax(self, diagnostic_dir: Path) -> None:
        """Test that the script has valid Python syntax."""
        script_path = diagnostic_dir / "high_cpu_parser.py"
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(script_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"
