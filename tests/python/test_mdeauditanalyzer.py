"""Tests for MDEAuditdAnalyzer module."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


class TestMDEAuditAnalyzer:
    """Test cases for MDEAuditAnalyzer.py functionality."""

    def test_script_exists(self, mdeauditanalyzer_dir: Path) -> None:
        """Test that the MDEAuditAnalyzer.py script exists."""
        script_path = mdeauditanalyzer_dir / "MDEAuditAnalyzer.py"
        assert script_path.exists(), f"Script not found: {script_path}"

    def test_script_has_python3_shebang(self, mdeauditanalyzer_dir: Path) -> None:
        """Test that the script has a Python 3 shebang."""
        script_path = mdeauditanalyzer_dir / "MDEAuditAnalyzer.py"
        with open(script_path) as f:
            first_line = f.readline().strip()
        assert first_line.startswith("#!"), "Script should have a shebang"
        assert "python3" in first_line, "Shebang should reference python3"

    def test_script_syntax(self, mdeauditanalyzer_dir: Path) -> None:
        """Test that the script has valid Python syntax."""
        script_path = mdeauditanalyzer_dir / "MDEAuditAnalyzer.py"
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(script_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_no_os_system_calls(self, mdeauditanalyzer_dir: Path) -> None:
        """Test that the script does not use os.system()."""
        script_path = mdeauditanalyzer_dir / "MDEAuditAnalyzer.py"
        content = script_path.read_text()
        assert "os.system(" not in content, "Script should not use os.system()"

    def test_no_bare_except(self, mdeauditanalyzer_dir: Path) -> None:
        """Test that the script does not have bare except clauses."""
        script_path = mdeauditanalyzer_dir / "MDEAuditAnalyzer.py"
        content = script_path.read_text()
        import re
        bare_except = re.search(r'\bexcept\s*:', content)
        assert bare_except is None, "Script should not have bare except: clauses"

    def test_uses_logging_module(self, mdeauditanalyzer_dir: Path) -> None:
        """Test that the script uses the logging module."""
        script_path = mdeauditanalyzer_dir / "MDEAuditAnalyzer.py"
        content = script_path.read_text()
        assert "import logging" in content, "Script should use logging module"

    def test_uses_argparse(self, mdeauditanalyzer_dir: Path) -> None:
        """Test that the script uses argparse for argument parsing."""
        script_path = mdeauditanalyzer_dir / "MDEAuditAnalyzer.py"
        content = script_path.read_text()
        assert "import argparse" in content or "from argparse" in content, \
            "Script should use argparse module"

    def test_has_type_hints(self, mdeauditanalyzer_dir: Path) -> None:
        """Test that the script has type hints."""
        script_path = mdeauditanalyzer_dir / "MDEAuditAnalyzer.py"
        content = script_path.read_text()
        # Check for common type hint patterns
        assert "-> " in content, "Script should have type hints on functions"

    def test_help_option(self, mdeauditanalyzer_dir: Path) -> None:
        """Test that the script supports --help option."""
        script_path = mdeauditanalyzer_dir / "MDEAuditAnalyzer.py"
        result = subprocess.run(
            [sys.executable, str(script_path), "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Help option failed: {result.stderr}"
        assert "usage" in result.stdout.lower() or "help" in result.stdout.lower()

    def test_requirements_file_exists(self, mdeauditanalyzer_dir: Path) -> None:
        """Test that requirements.txt exists."""
        requirements_path = mdeauditanalyzer_dir / "requirements.txt"
        assert requirements_path.exists(), f"Requirements file not found: {requirements_path}"
