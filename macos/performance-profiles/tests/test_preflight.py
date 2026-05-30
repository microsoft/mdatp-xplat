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
