"""Tests for preflight checks."""

import pytest
from unittest.mock import patch, MagicMock
from demo_framework.preflight import Preflight


class TestPreflight:
    """Test preflight checks."""

    def test_check_command_exists(self):
        """Test checking if command exists."""
        # These commands should always exist
        assert Preflight.check_command_exists("echo") is True
        assert Preflight.check_command_exists("nonexistent_command_xyz") is False

    def test_get_version(self):
        """Test getting version of a command."""
        version = Preflight.get_version("echo")
        assert version is not None

    def test_check_node_version_valid(self):
        """Test checking valid Node.js version."""
        # Mock the subprocess to return a valid version
        with patch("demo_framework.preflight.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "v24.16.0\n"
            mock_run.return_value = mock_result
            
            result = Preflight.check_node_version(required_major=24)
            assert result == "v24.16.0"

    def test_check_node_version_invalid(self):
        """Test checking invalid Node.js version."""
        # Mock to return v23
        with patch("demo_framework.preflight.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "v23.11.0\n"
            mock_run.return_value = mock_result
            
            result = Preflight.check_node_version(required_major=24)
            assert result is None

    def test_check_node_version_missing(self):
        """Test checking when Node.js is not installed."""
        with patch("demo_framework.preflight.subprocess.run") as mock_run:
            mock_run.side_effect = Exception("Command not found")
            
            result = Preflight.check_node_version()
            assert result is None

    def test_install_missing_tools_user_declines(self):
        """Test user declining tool installation."""
        with patch("builtins.input", return_value="n"):
            result = Preflight.install_missing_tools(["git"])
            assert result is False

    def test_install_missing_tools_user_accepts(self):
        """Test user accepting tool installation."""
        with patch("builtins.input", return_value="y"):
            with patch("demo_framework.preflight.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                result = Preflight.install_missing_tools(["git"])
                assert result is True

    def test_check_mdatp_profiles_parses_list_available_output(self):
        """Test profile count parser for actual list-available output format."""
        output = """=====================================
adobe
---
android-studio
---
git
---
"""
        with patch("demo_framework.preflight.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = output
            mock_run.return_value = mock_result

            count = Preflight.check_mdatp_profiles()

            assert count == 3
            mock_run.assert_called_once_with(
                ["mdatp", "performance-profiles", "list-available"],
                capture_output=True,
                text=True,
                timeout=5,
            )

    def test_check_mdatp_profiles_returns_zero_on_command_error(self):
        """Test profile check returns zero when command fails."""
        with patch("demo_framework.preflight.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stdout = ""
            mock_run.return_value = mock_result

            count = Preflight.check_mdatp_profiles()

            assert count == 0

    def test_run_all_succeeds_when_client_analyzer_found(self):
        """Require analyzer should pass if binary is found."""
        with patch.object(Preflight, "check_mdatp", return_value=True), \
             patch.object(Preflight, "check_mdatp_rtp", return_value=True), \
             patch.object(Preflight, "check_mdatp_profiles", return_value=10), \
             patch.object(Preflight, "check_xcode_clt", return_value=True), \
             patch.object(Preflight, "check_command_exists", return_value=True), \
             patch.object(Preflight, "find_client_analyzer_binary", return_value="/tmp/MDESupportTool"):
            ok = Preflight().run_all(require_node=False, require_client_analyzer=True)
            assert ok is True

    def test_run_all_fails_when_client_analyzer_required_and_declined(self):
        """Require analyzer should fail when user declines installation."""
        with patch.object(Preflight, "check_mdatp", return_value=True), \
             patch.object(Preflight, "check_mdatp_rtp", return_value=True), \
             patch.object(Preflight, "check_mdatp_profiles", return_value=10), \
             patch.object(Preflight, "check_xcode_clt", return_value=True), \
             patch.object(Preflight, "check_command_exists", return_value=True), \
             patch.object(Preflight, "find_client_analyzer_binary", return_value=None), \
             patch("builtins.input", return_value="n"):
            ok = Preflight().run_all(require_node=False, require_client_analyzer=True)
            assert ok is False

    def test_run_all_installs_client_analyzer_when_required(self):
        """Require analyzer should install and pass when user accepts."""
        with patch.object(Preflight, "check_mdatp", return_value=True), \
             patch.object(Preflight, "check_mdatp_rtp", return_value=True), \
             patch.object(Preflight, "check_mdatp_profiles", return_value=10), \
             patch.object(Preflight, "check_xcode_clt", return_value=True), \
             patch.object(Preflight, "check_command_exists", return_value=True), \
             patch.object(Preflight, "find_client_analyzer_binary", side_effect=[None, "/tmp/MDESupportTool"]), \
             patch.object(Preflight, "install_client_analyzer", return_value=True), \
             patch("builtins.input", return_value="y"):
            ok = Preflight().run_all(require_node=False, require_client_analyzer=True)
            assert ok is True
