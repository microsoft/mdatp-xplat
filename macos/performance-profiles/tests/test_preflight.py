"""Tests for preflight checks."""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
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
             patch.object(Preflight, "check_ghcp_cli", return_value=False), \
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
             patch.object(Preflight, "check_ghcp_cli", return_value=True), \
             patch.object(Preflight, "check_ghcp_access", return_value=(True, "ok", "octocat")), \
             patch.object(Preflight, "find_client_analyzer_binary", side_effect=[None, "/tmp/MDESupportTool"]), \
             patch.object(Preflight, "install_client_analyzer", return_value=True), \
             patch("builtins.input", return_value="y"):
            ok = Preflight().run_all(require_node=False, require_client_analyzer=True)
            assert ok is True

    def test_run_all_uses_custom_client_analyzer_dir(self):
        """Custom analyzer dir should be used for detection and installation."""
        custom_dir = Path("/tmp/custom-analyzer")
        with patch.object(Preflight, "check_mdatp", return_value=True), \
             patch.object(Preflight, "check_mdatp_rtp", return_value=True), \
             patch.object(Preflight, "check_mdatp_profiles", return_value=10), \
             patch.object(Preflight, "check_xcode_clt", return_value=True), \
             patch.object(Preflight, "check_command_exists", return_value=True), \
             patch.object(Preflight, "check_ghcp_cli", return_value=True), \
             patch.object(Preflight, "check_ghcp_access", return_value=(True, "ok", "octocat")), \
             patch.object(Preflight, "find_client_analyzer_binary", side_effect=[None, "/tmp/custom-analyzer/mde_support_tool.sh"]) as mock_find, \
             patch.object(Preflight, "install_client_analyzer", return_value=True) as mock_install, \
             patch("builtins.input", return_value="y"):
            ok = Preflight().run_all(
                require_node=False,
                require_client_analyzer=True,
                client_analyzer_dir=custom_dir,
            )
            assert ok is True
            mock_find.assert_any_call(custom_dir)
            mock_install.assert_called_once_with(custom_dir)

    def test_run_all_allows_missing_ghcp_when_optional(self):
        """Missing GHCP should not fail preflight when not required."""
        with patch.object(Preflight, "check_mdatp", return_value=True), \
             patch.object(Preflight, "check_mdatp_rtp", return_value=True), \
             patch.object(Preflight, "check_mdatp_profiles", return_value=10), \
             patch.object(Preflight, "check_xcode_clt", return_value=True), \
             patch.object(Preflight, "check_command_exists", return_value=True), \
             patch.object(Preflight, "find_client_analyzer_binary", return_value=None), \
             patch.object(Preflight, "check_ghcp_cli", return_value=False):
            ok = Preflight().run_all(require_node=False)
            assert ok is True

    def test_run_all_fails_when_ghcp_required_and_declined(self):
        """Require GHCP should fail when user declines installation."""
        with patch.object(Preflight, "check_mdatp", return_value=True), \
             patch.object(Preflight, "check_mdatp_rtp", return_value=True), \
             patch.object(Preflight, "check_mdatp_profiles", return_value=10), \
             patch.object(Preflight, "check_xcode_clt", return_value=True), \
             patch.object(Preflight, "check_command_exists", return_value=True), \
             patch.object(Preflight, "find_client_analyzer_binary", return_value=None), \
             patch.object(Preflight, "check_ghcp_cli", return_value=False), \
             patch("builtins.input", return_value="n"):
            ok = Preflight().run_all(require_node=False, require_ghcp_cli=True)
            assert ok is False

    def test_run_all_installs_ghcp_when_required(self):
        """Require GHCP should install and pass when user accepts."""
        with patch.object(Preflight, "check_mdatp", return_value=True), \
             patch.object(Preflight, "check_mdatp_rtp", return_value=True), \
             patch.object(Preflight, "check_mdatp_profiles", return_value=10), \
             patch.object(Preflight, "check_xcode_clt", return_value=True), \
             patch.object(Preflight, "check_command_exists", return_value=True), \
             patch.object(Preflight, "find_client_analyzer_binary", return_value=None), \
             patch.object(Preflight, "check_ghcp_cli", side_effect=[False, True]), \
             patch.object(Preflight, "check_ghcp_access", return_value=(True, "ok", "octocat")), \
             patch.object(Preflight, "install_ghcp_cli", return_value=True), \
             patch("builtins.input", return_value="y"):
            ok = Preflight().run_all(require_node=False, require_ghcp_cli=True)
            assert ok is True

    def test_check_ghcp_access_detects_policy_denial(self):
        """A policy-blocked account must be detected even though the CLI exits 0."""
        denial_output = (
            "Error: Access denied by policy settings (Request ID: EE84:1234)\n"
            "Your Copilot CLI policy setting may be preventing access."
        )
        with patch.object(Preflight, "check_command_exists", return_value=True), \
             patch("demo_framework.preflight.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=denial_output, stderr="")
            ok, detail, user = Preflight.check_ghcp_access()
            assert ok is False
            assert "policy" in detail.lower()
            assert user is None

    def test_check_ghcp_access_succeeds_on_ok_response(self):
        """A normal OK response should be treated as authorized."""
        with patch.object(Preflight, "check_command_exists", return_value=True), \
             patch("demo_framework.preflight.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="OK\n", stderr="")
            ok, _, _ = Preflight.check_ghcp_access()
            assert ok is True

    def test_check_ghcp_access_reports_authenticated_user(self):
        """The probe should parse the authenticated GitHub login from the response."""
        with patch.object(Preflight, "check_command_exists", return_value=True), \
             patch("demo_framework.preflight.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="USER:octocat\n", stderr="")
            ok, _, user = Preflight.check_ghcp_access()
            assert ok is True
            assert user == "octocat"

    def test_check_ghcp_access_user_unknown_is_none(self):
        """A USER:unknown reply should resolve to no identified user but still pass."""
        with patch.object(Preflight, "check_command_exists", return_value=True), \
             patch("demo_framework.preflight.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="USER:unknown\n", stderr="")
            ok, _, user = Preflight.check_ghcp_access()
            assert ok is True
            assert user is None

    def test_run_all_warns_but_passes_when_ghcp_blocked_and_optional(self):
        """GHCP installed but policy-blocked should warn yet not fail an optional run."""
        with patch.object(Preflight, "check_mdatp", return_value=True), \
             patch.object(Preflight, "check_mdatp_rtp", return_value=True), \
             patch.object(Preflight, "check_mdatp_profiles", return_value=10), \
             patch.object(Preflight, "check_xcode_clt", return_value=True), \
             patch.object(Preflight, "check_command_exists", return_value=True), \
             patch.object(Preflight, "find_client_analyzer_binary", return_value=None), \
             patch.object(Preflight, "check_ghcp_cli", return_value=True), \
             patch.object(Preflight, "get_active_github_user", return_value="j0shbregman"), \
             patch.object(Preflight, "check_ghcp_access", return_value=(False, "request blocked by Copilot policy/subscription/auth", None)):
            ok = Preflight().run_all(require_node=False)
            assert ok is True

    def test_run_all_fails_when_ghcp_required_but_blocked(self):
        """GHCP installed but policy-blocked must fail a required run."""
        with patch.object(Preflight, "check_mdatp", return_value=True), \
             patch.object(Preflight, "check_mdatp_rtp", return_value=True), \
             patch.object(Preflight, "check_mdatp_profiles", return_value=10), \
             patch.object(Preflight, "check_xcode_clt", return_value=True), \
             patch.object(Preflight, "check_command_exists", return_value=True), \
             patch.object(Preflight, "find_client_analyzer_binary", return_value=None), \
             patch.object(Preflight, "check_ghcp_cli", return_value=True), \
             patch.object(Preflight, "get_active_github_user", return_value="j0shbregman"), \
             patch.object(Preflight, "check_ghcp_access", return_value=(False, "request blocked by Copilot policy/subscription/auth", None)):
            ok = Preflight().run_all(require_node=False, require_ghcp_cli=True)
            assert ok is False

    def test_get_active_github_user_selects_active_account(self):
        """With multiple accounts, the one marked active must be returned."""
        status_output = (
            "github.com\n"
            "  ✓ Logged in to github.com account j0shbregman (keyring)\n"
            "  - Active account: true\n"
            "  - Token scopes: 'repo'\n"
            "\n"
            "  ✓ Logged in to github.com account josh-bregman (keyring)\n"
            "  - Active account: false\n"
            "  - Token scopes: 'repo'\n"
        )
        with patch.object(Preflight, "check_command_exists", return_value=True), \
             patch("demo_framework.preflight.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr=status_output)
            assert Preflight.get_active_github_user() == "j0shbregman"

    def test_get_active_github_user_single_account_fallback(self):
        """A single signed-in account should be returned even without an active marker."""
        status_output = (
            "github.com\n"
            "  ✓ Logged in to github.com account solo-user (keyring)\n"
            "  - Git operations protocol: https\n"
        )
        with patch.object(Preflight, "check_command_exists", return_value=True), \
             patch("demo_framework.preflight.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr=status_output)
            assert Preflight.get_active_github_user() == "solo-user"

    def test_get_active_github_user_returns_none_without_gh(self):
        """No gh binary means no identity can be resolved."""
        with patch.object(Preflight, "check_command_exists", return_value=False):
            assert Preflight.get_active_github_user() is None
