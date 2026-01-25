"""Pytest configuration and fixtures for mdatp-xplat tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def project_root() -> Path:
    """Return the project root directory."""
    return Path(__file__).parent.parent.parent


@pytest.fixture
def linux_dir(project_root: Path) -> Path:
    """Return the linux directory."""
    return project_root / "linux"


@pytest.fixture
def macos_dir(project_root: Path) -> Path:
    """Return the macos directory."""
    return project_root / "macos"


@pytest.fixture
def scripts_dir(linux_dir: Path) -> Path:
    """Return the linux installation directory."""
    return linux_dir / "installation"


@pytest.fixture
def scheduler_dir(linux_dir: Path) -> Path:
    """Return the linux scheduler directory."""
    return linux_dir / "scheduler"


@pytest.fixture
def diagnostic_dir(linux_dir: Path) -> Path:
    """Return the linux diagnostic directory."""
    return linux_dir / "diagnostic"


@pytest.fixture
def linuxmdeparser_dir(linux_dir: Path) -> Path:
    """Return the LinuxMDEparser directory."""
    return linux_dir / "LinuxMDEparser"


@pytest.fixture
def mdeauditanalyzer_dir(linux_dir: Path) -> Path:
    """Return the MDEAuditdAnalyzer directory."""
    return linux_dir / "MDEAuditdAnalyzer"


@pytest.fixture
def jamf_dir(macos_dir: Path) -> Path:
    """Return the macOS jamf directory."""
    return macos_dir / "jamf"


@pytest.fixture
def mdm_dir(macos_dir: Path) -> Path:
    """Return the macOS mdm directory."""
    return macos_dir / "mdm"


@pytest.fixture
def mobileconfig_dir(macos_dir: Path) -> Path:
    """Return the macOS mobileconfig directory."""
    return macos_dir / "mobileconfig"


@pytest.fixture
def schema_dir(macos_dir: Path) -> Path:
    """Return the macOS schema directory."""
    return macos_dir / "schema"
