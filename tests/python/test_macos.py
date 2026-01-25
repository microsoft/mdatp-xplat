"""Tests for macOS Python scripts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


class TestDownloadProfile:
    """Test cases for download_profile.py functionality."""

    def test_script_exists(self, jamf_dir: Path) -> None:
        """Test that the download_profile.py script exists."""
        script_path = jamf_dir / "download_profile.py"
        assert script_path.exists(), f"Script not found: {script_path}"

    def test_script_has_python3_shebang(self, jamf_dir: Path) -> None:
        """Test that the script has a Python 3 shebang."""
        script_path = jamf_dir / "download_profile.py"
        with open(script_path) as f:
            first_line = f.readline().strip()
        assert first_line.startswith("#!"), "Script should have a shebang"
        assert "python3" in first_line, "Shebang should reference python3"

    def test_script_syntax(self, jamf_dir: Path) -> None:
        """Test that the script has valid Python syntax."""
        script_path = jamf_dir / "download_profile.py"
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(script_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_no_os_system_calls(self, jamf_dir: Path) -> None:
        """Test that the script does not use os.system()."""
        script_path = jamf_dir / "download_profile.py"
        content = script_path.read_text()
        assert "os.system(" not in content, "Script should not use os.system()"

    def test_no_bare_except(self, jamf_dir: Path) -> None:
        """Test that the script does not have bare except clauses."""
        script_path = jamf_dir / "download_profile.py"
        content = script_path.read_text()
        import re
        bare_except = re.search(r'\bexcept\s*:', content)
        assert bare_except is None, "Script should not have bare except: clauses"

    def test_uses_logging_module(self, jamf_dir: Path) -> None:
        """Test that the script uses the logging module."""
        script_path = jamf_dir / "download_profile.py"
        content = script_path.read_text()
        assert "import logging" in content, "Script should use logging module"


class TestAnalyzeProfiles:
    """Test cases for analyze_profiles.py functionality."""

    def test_script_exists(self, mdm_dir: Path) -> None:
        """Test that the analyze_profiles.py script exists."""
        script_path = mdm_dir / "analyze_profiles.py"
        assert script_path.exists(), f"Script not found: {script_path}"

    def test_script_has_python3_shebang(self, mdm_dir: Path) -> None:
        """Test that the script has a Python 3 shebang."""
        script_path = mdm_dir / "analyze_profiles.py"
        with open(script_path) as f:
            first_line = f.readline().strip()
        assert first_line.startswith("#!"), "Script should have a shebang"
        assert "python3" in first_line, "Shebang should reference python3"

    def test_script_syntax(self, mdm_dir: Path) -> None:
        """Test that the script has valid Python syntax."""
        script_path = mdm_dir / "analyze_profiles.py"
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(script_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_no_os_system_calls(self, mdm_dir: Path) -> None:
        """Test that the script does not use os.system()."""
        script_path = mdm_dir / "analyze_profiles.py"
        content = script_path.read_text()
        assert "os.system(" not in content, "Script should not use os.system()"

    def test_no_bare_except(self, mdm_dir: Path) -> None:
        """Test that the script does not have bare except clauses."""
        script_path = mdm_dir / "analyze_profiles.py"
        content = script_path.read_text()
        import re
        bare_except = re.search(r'\bexcept\s*:', content)
        assert bare_except is None, "Script should not have bare except: clauses"


class TestBuildCombined:
    """Test cases for build_combined.py functionality."""

    def test_script_exists(self, mobileconfig_dir: Path) -> None:
        """Test that the build_combined.py script exists."""
        script_path = mobileconfig_dir / "combined" / "build_combined.py"
        assert script_path.exists(), f"Script not found: {script_path}"

    def test_script_has_python3_shebang(self, mobileconfig_dir: Path) -> None:
        """Test that the script has a Python 3 shebang."""
        script_path = mobileconfig_dir / "combined" / "build_combined.py"
        with open(script_path) as f:
            first_line = f.readline().strip()
        assert first_line.startswith("#!"), "Script should have a shebang"
        assert "python3" in first_line, "Shebang should reference python3"

    def test_script_syntax(self, mobileconfig_dir: Path) -> None:
        """Test that the script has valid Python syntax."""
        script_path = mobileconfig_dir / "combined" / "build_combined.py"
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(script_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_no_os_system_calls(self, mobileconfig_dir: Path) -> None:
        """Test that the script does not use os.system()."""
        script_path = mobileconfig_dir / "combined" / "build_combined.py"
        content = script_path.read_text()
        assert "os.system(" not in content, "Script should not use os.system()"

    def test_no_bare_except(self, mobileconfig_dir: Path) -> None:
        """Test that the script does not have bare except clauses."""
        script_path = mobileconfig_dir / "combined" / "build_combined.py"
        content = script_path.read_text()
        import re
        bare_except = re.search(r'\bexcept\s*:', content)
        assert bare_except is None, "Script should not have bare except: clauses"


class TestValidateConfigProfile:
    """Test cases for validate-config-profile.py functionality."""

    def test_script_exists(self, schema_dir: Path) -> None:
        """Test that the validate-config-profile.py script exists."""
        script_path = schema_dir / "validator" / "validate-config-profile.py"
        assert script_path.exists(), f"Script not found: {script_path}"

    def test_script_has_python3_shebang(self, schema_dir: Path) -> None:
        """Test that the script has a Python 3 shebang."""
        script_path = schema_dir / "validator" / "validate-config-profile.py"
        with open(script_path) as f:
            first_line = f.readline().strip()
        assert first_line.startswith("#!"), "Script should have a shebang"
        assert "python3" in first_line, "Shebang should reference python3"

    def test_script_syntax(self, schema_dir: Path) -> None:
        """Test that the script has valid Python syntax."""
        script_path = schema_dir / "validator" / "validate-config-profile.py"
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(script_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_no_os_system_calls(self, schema_dir: Path) -> None:
        """Test that the script does not use os.system()."""
        script_path = schema_dir / "validator" / "validate-config-profile.py"
        content = script_path.read_text()
        assert "os.system(" not in content, "Script should not use os.system()"

    def test_no_bare_except(self, schema_dir: Path) -> None:
        """Test that the script does not have bare except clauses."""
        script_path = schema_dir / "validator" / "validate-config-profile.py"
        content = script_path.read_text()
        import re
        bare_except = re.search(r'\bexcept\s*:', content)
        assert bare_except is None, "Script should not have bare except: clauses"
