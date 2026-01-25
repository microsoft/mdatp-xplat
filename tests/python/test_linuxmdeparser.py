"""Tests for LinuxMDEparser module."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


class TestJson2Excel:
    """Test cases for json2excel.py functionality."""

    def test_script_exists(self, linuxmdeparser_dir: Path) -> None:
        """Test that the json2excel.py script exists."""
        script_path = linuxmdeparser_dir / "json2excel.py"
        assert script_path.exists(), f"Script not found: {script_path}"

    def test_script_has_python3_shebang(self, linuxmdeparser_dir: Path) -> None:
        """Test that the script has a Python 3 shebang."""
        script_path = linuxmdeparser_dir / "json2excel.py"
        with open(script_path) as f:
            first_line = f.readline().strip()
        assert first_line.startswith("#!"), "Script should have a shebang"
        assert "python3" in first_line, "Shebang should reference python3"

    def test_script_syntax(self, linuxmdeparser_dir: Path) -> None:
        """Test that the script has valid Python syntax."""
        script_path = linuxmdeparser_dir / "json2excel.py"
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(script_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_no_os_system_calls(self, linuxmdeparser_dir: Path) -> None:
        """Test that the script does not use os.system()."""
        script_path = linuxmdeparser_dir / "json2excel.py"
        content = script_path.read_text()
        assert "os.system(" not in content, "Script should not use os.system()"

    def test_no_bare_except(self, linuxmdeparser_dir: Path) -> None:
        """Test that the script does not have bare except clauses."""
        script_path = linuxmdeparser_dir / "json2excel.py"
        content = script_path.read_text()
        # Check for bare except: (with colon and possible whitespace)
        import re
        bare_except = re.search(r'\bexcept\s*:', content)
        assert bare_except is None, "Script should not have bare except: clauses"

    def test_uses_logging_module(self, linuxmdeparser_dir: Path) -> None:
        """Test that the script uses the logging module."""
        script_path = linuxmdeparser_dir / "json2excel.py"
        content = script_path.read_text()
        assert "import logging" in content, "Script should use logging module"

    def test_has_type_hints(self, linuxmdeparser_dir: Path) -> None:
        """Test that the script has type hints."""
        script_path = linuxmdeparser_dir / "json2excel.py"
        content = script_path.read_text()
        # Check for common type hint patterns
        assert "-> " in content or ": str" in content or ": Path" in content, \
            "Script should have type hints"


class TestMain:
    """Test cases for main.py functionality."""

    def test_script_exists(self, linuxmdeparser_dir: Path) -> None:
        """Test that the main.py script exists."""
        script_path = linuxmdeparser_dir / "main.py"
        assert script_path.exists(), f"Script not found: {script_path}"

    def test_script_has_python3_shebang(self, linuxmdeparser_dir: Path) -> None:
        """Test that the script has a Python 3 shebang."""
        script_path = linuxmdeparser_dir / "main.py"
        with open(script_path) as f:
            first_line = f.readline().strip()
        assert first_line.startswith("#!"), "Script should have a shebang"
        assert "python3" in first_line, "Shebang should reference python3"

    def test_script_syntax(self, linuxmdeparser_dir: Path) -> None:
        """Test that the script has valid Python syntax."""
        script_path = linuxmdeparser_dir / "main.py"
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(script_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_no_os_system_calls(self, linuxmdeparser_dir: Path) -> None:
        """Test that the script does not use os.system()."""
        script_path = linuxmdeparser_dir / "main.py"
        content = script_path.read_text()
        assert "os.system(" not in content, "Script should not use os.system()"

    def test_no_bare_except(self, linuxmdeparser_dir: Path) -> None:
        """Test that the script does not have bare except clauses."""
        script_path = linuxmdeparser_dir / "main.py"
        content = script_path.read_text()
        import re
        bare_except = re.search(r'\bexcept\s*:', content)
        assert bare_except is None, "Script should not have bare except: clauses"

    def test_uses_argparse(self, linuxmdeparser_dir: Path) -> None:
        """Test that the script uses argparse for argument parsing."""
        script_path = linuxmdeparser_dir / "main.py"
        content = script_path.read_text()
        assert "import argparse" in content or "from argparse" in content, \
            "Script should use argparse module"

    def test_help_option(self, linuxmdeparser_dir: Path) -> None:
        """Test that the script supports --help option."""
        script_path = linuxmdeparser_dir / "main.py"
        result = subprocess.run(
            [sys.executable, str(script_path), "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Help option failed: {result.stderr}"
        assert "usage" in result.stdout.lower() or "help" in result.stdout.lower()
