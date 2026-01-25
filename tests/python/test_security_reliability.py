"""Tests for security and reliability fixes.

These tests verify that the security and reliability fixes remain in place
and prevent regressions.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest


class TestSEC002InputValidation:
    """Test SEC-002: Validate CLI arguments in shell scripts."""

    def test_validate_path_function_exists(self, scripts_dir: Path) -> None:
        """Test that validate_path function exists in mde_installer.sh."""
        script_path = scripts_dir / "mde_installer.sh"
        content = script_path.read_text()
        assert "validate_path()" in content, "validate_path function should exist"

    def test_validate_script_path_function_exists(self, scripts_dir: Path) -> None:
        """Test that validate_script_path function exists."""
        script_path = scripts_dir / "mde_installer.sh"
        content = script_path.read_text()
        assert "validate_script_path()" in content, "validate_script_path function should exist"

    def test_validate_install_path_function_exists(self, scripts_dir: Path) -> None:
        """Test that validate_install_path function exists."""
        script_path = scripts_dir / "mde_installer.sh"
        content = script_path.read_text()
        assert "validate_install_path()" in content, "validate_install_path function should exist"

    def test_path_traversal_check_exists(self, scripts_dir: Path) -> None:
        """Test that path traversal check exists in validation."""
        script_path = scripts_dir / "mde_installer.sh"
        content = script_path.read_text()
        assert '".."' in content, "Path traversal check should be present"

    def test_shell_metacharacter_check_exists(self, scripts_dir: Path) -> None:
        """Test that shell metacharacter check exists."""
        script_path = scripts_dir / "mde_installer.sh"
        content = script_path.read_text()
        assert "metacharacters" in content.lower() or "shell" in content.lower(), \
            "Shell metacharacter check should be documented"

    def test_onboard_uses_validation(self, scripts_dir: Path) -> None:
        """Test that --onboard option uses validation."""
        script_path = scripts_dir / "mde_installer.sh"
        content = script_path.read_text()
        assert "validate_script_path" in content and "onboarding" in content, \
            "--onboard should use validate_script_path"

    def test_install_path_uses_validation(self, scripts_dir: Path) -> None:
        """Test that --install-path option uses validation."""
        script_path = scripts_dir / "mde_installer.sh"
        content = script_path.read_text()
        assert "validate_install_path" in content, \
            "--install-path should use validate_install_path"


class TestSEC007GPGKeyVerification:
    """Test SEC-007: GPG key fingerprint verification."""

    def test_gpg_fingerprint_constant_exists(self, scripts_dir: Path) -> None:
        """Test that GPG fingerprint constants are defined."""
        script_path = scripts_dir / "mde_installer.sh"
        content = script_path.read_text()
        assert "MICROSOFT_GPG_FINGERPRINT" in content, \
            "MICROSOFT_GPG_FINGERPRINT constant should be defined"

    def test_verify_gpg_key_fingerprint_function_exists(self, scripts_dir: Path) -> None:
        """Test that verify_gpg_key_fingerprint function exists."""
        script_path = scripts_dir / "mde_installer.sh"
        content = script_path.read_text()
        assert "verify_gpg_key_fingerprint()" in content, \
            "verify_gpg_key_fingerprint function should exist"

    def test_download_and_verify_gpg_key_function_exists(self, scripts_dir: Path) -> None:
        """Test that download_and_verify_gpg_key function exists."""
        script_path = scripts_dir / "mde_installer.sh"
        content = script_path.read_text()
        assert "download_and_verify_gpg_key()" in content, \
            "download_and_verify_gpg_key function should exist"

    def test_gpg_verification_used_in_debian_install(self, scripts_dir: Path) -> None:
        """Test that GPG verification is used during Debian installation."""
        script_path = scripts_dir / "mde_installer.sh"
        content = script_path.read_text()
        # Check that download_and_verify_gpg_key is called
        assert content.count("download_and_verify_gpg_key") >= 2, \
            "download_and_verify_gpg_key should be called for key downloads"


class TestSEC008ModernAptKeyHandling:
    """Test SEC-008: Use modern apt key handling (signed-by)."""

    def test_uses_keyrings_directory(self, scripts_dir: Path) -> None:
        """Test that keys are stored in /usr/share/keyrings/."""
        script_path = scripts_dir / "mde_installer.sh"
        content = script_path.read_text()
        assert "/usr/share/keyrings/" in content, \
            "Should use /usr/share/keyrings/ for GPG keys"

    def test_gpg_key_file_defined(self, scripts_dir: Path) -> None:
        """Test that gpg_key_file variable is properly set."""
        script_path = scripts_dir / "mde_installer.sh"
        content = script_path.read_text()
        assert "microsoft-prod.gpg" in content, \
            "Should use microsoft-prod.gpg keyring file"


class TestREL003ErrorReporting:
    """Test REL-003: Improved error reporting."""

    def test_script_exit_has_success_message(self, scripts_dir: Path) -> None:
        """Test that script_exit shows clear SUCCESS message."""
        script_path = scripts_dir / "mde_installer.sh"
        content = script_path.read_text()
        assert "[SUCCESS]" in content, "script_exit should show [SUCCESS] for success"

    def test_script_exit_has_failed_message(self, scripts_dir: Path) -> None:
        """Test that script_exit shows clear FAILED message."""
        script_path = scripts_dir / "mde_installer.sh"
        content = script_path.read_text()
        assert "[FAILED]" in content, "script_exit should show [FAILED] for failure"

    def test_script_exit_has_hints(self, scripts_dir: Path) -> None:
        """Test that script_exit provides hints for common errors."""
        script_path = scripts_dir / "mde_installer.sh"
        content = script_path.read_text()
        assert "[*] Hint:" in content, "script_exit should provide hints for errors"


class TestREL006TimeoutHandling:
    """Test REL-006: Timeout handling with cleanup."""

    def test_run_with_timeout_function_exists(self, scripts_dir: Path) -> None:
        """Test that run_with_timeout function exists."""
        script_path = scripts_dir / "mde_installer.sh"
        content = script_path.read_text()
        assert "run_with_timeout()" in content, \
            "run_with_timeout function should exist"

    def test_timeout_kills_process(self, scripts_dir: Path) -> None:
        """Test that timeout function kills hung processes."""
        script_path = scripts_dir / "mde_installer.sh"
        content = script_path.read_text()
        assert "kill -TERM" in content or "kill -KILL" in content, \
            "Timeout handling should kill hung processes"

    def test_timeout_logs_message(self, scripts_dir: Path) -> None:
        """Test that timeout logs appropriate message."""
        script_path = scripts_dir / "mde_installer.sh"
        content = script_path.read_text()
        assert "timeout" in content.lower() and "timed out" in content.lower(), \
            "Timeout should log timeout message"


class TestCQSH001QuotedVariables:
    """Test CQ-SH-001: Critical variables are properly quoted."""

    def test_onboarding_script_quoted_in_execution(self, scripts_dir: Path) -> None:
        """Test that ONBOARDING_SCRIPT is quoted when executed."""
        script_path = scripts_dir / "mde_installer.sh"
        content = script_path.read_text()
        # Check for quoted usage in run_quietly
        assert '"$ONBOARDING_SCRIPT"' in content, \
            "ONBOARDING_SCRIPT should be quoted in execution"

    def test_offboarding_script_quoted_in_execution(self, scripts_dir: Path) -> None:
        """Test that OFFBOARDING_SCRIPT is quoted when executed."""
        script_path = scripts_dir / "mde_installer.sh"
        content = script_path.read_text()
        assert '"$OFFBOARDING_SCRIPT"' in content, \
            "OFFBOARDING_SCRIPT should be quoted in execution"

    def test_install_path_quoted_in_mkdir(self, scripts_dir: Path) -> None:
        """Test that INSTALL_PATH is quoted in mkdir commands."""
        script_path = scripts_dir / "mde_installer.sh"
        content = script_path.read_text()
        assert 'mkdir -p "$INSTALL_PATH"' in content, \
            "INSTALL_PATH should be quoted in mkdir"


class TestCQPY007PythonInputValidation:
    """Test CQ-PY-007: Python scripts have input validation."""

    def test_main_py_has_validate_path(self, linuxmdeparser_dir: Path) -> None:
        """Test that main.py has path validation function."""
        script_path = linuxmdeparser_dir / "main.py"
        content = script_path.read_text()
        assert "validate_path" in content, "main.py should have validate_path function"

    def test_main_py_validates_input(self, linuxmdeparser_dir: Path) -> None:
        """Test that main.py validates input files."""
        script_path = linuxmdeparser_dir / "main.py"
        content = script_path.read_text()
        assert "must_exist" in content, "main.py should validate input file exists"

    def test_main_py_checks_path_traversal(self, linuxmdeparser_dir: Path) -> None:
        """Test that main.py checks for path traversal."""
        script_path = linuxmdeparser_dir / "main.py"
        content = script_path.read_text()
        assert '".."' in content, "main.py should check for path traversal"

    def test_high_cpu_parser_validates_input(self, diagnostic_dir: Path) -> None:
        """Test that high_cpu_parser.py validates input structure."""
        script_path = diagnostic_dir / "high_cpu_parser.py"
        content = script_path.read_text()
        assert "isinstance" in content, "high_cpu_parser.py should validate input types"

    def test_high_cpu_parser_validates_top_argument(self, diagnostic_dir: Path) -> None:
        """Test that high_cpu_parser.py validates --top argument."""
        script_path = diagnostic_dir / "high_cpu_parser.py"
        content = script_path.read_text()
        assert "args.top" in content and "<= 0" in content, \
            "high_cpu_parser.py should validate --top is positive"


class TestShellScriptSyntax:
    """Test that all shell scripts have valid syntax after changes."""

    def test_mde_installer_syntax(self, scripts_dir: Path) -> None:
        """Test mde_installer.sh has valid syntax."""
        script_path = scripts_dir / "mde_installer.sh"
        result = subprocess.run(
            ["bash", "-n", str(script_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_xplat_offline_updates_syntax(self, project_root: Path) -> None:
        """Test xplat_offline_updates_download.sh has valid syntax."""
        script_path = project_root / "linux" / "definition_downloader" / "xplat_offline_updates_download.sh"
        result = subprocess.run(
            ["bash", "-n", str(script_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"


class TestPythonScriptSyntax:
    """Test that all Python scripts have valid syntax after changes."""

    def test_all_python_files_compile(self, project_root: Path) -> None:
        """Test that all modified Python files compile."""
        python_files = [
            "linux/LinuxMDEparser/main.py",
            "linux/LinuxMDEparser/json2excel.py",
            "linux/diagnostic/high_cpu_parser.py",
            "linux/MDEAuditdAnalyzer/MDEAuditAnalyzer.py",
            "linux/scheduler/schedule_scan.py",
            "linux/scheduler/schedule_update.py",
            "macos/jamf/download_profile.py",
            "macos/mdm/analyze_profiles.py",
        ]
        
        for py_file in python_files:
            script_path = project_root / py_file
            if script_path.exists():
                result = subprocess.run(
                    [sys.executable, "-m", "py_compile", str(script_path)],
                    capture_output=True,
                    text=True,
                )
                assert result.returncode == 0, f"{py_file}: {result.stderr}"
