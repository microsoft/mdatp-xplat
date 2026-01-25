"""Code quality tests to prevent regressions.

These tests check for banned patterns across the entire codebase to ensure
code quality standards are maintained.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Iterator

import pytest


def get_python_files(root: Path) -> Iterator[Path]:
    """Yield all Python files in the project, excluding __pycache__."""
    for py_file in root.rglob("*.py"):
        if "__pycache__" not in str(py_file):
            yield py_file


def get_shell_files(root: Path) -> Iterator[Path]:
    """Yield all shell script files in the project."""
    for sh_file in root.rglob("*.sh"):
        yield sh_file


class TestBannedPythonPatterns:
    """Test that banned Python patterns are not used anywhere."""

    def test_no_os_system_anywhere(self, project_root: Path) -> None:
        """Test that os.system() is not used in any Python file."""
        violations = []
        for py_file in get_python_files(project_root):
            content = py_file.read_text()
            if "os.system(" in content:
                # Find line numbers
                for i, line in enumerate(content.splitlines(), 1):
                    if "os.system(" in line:
                        violations.append(f"{py_file}:{i}: {line.strip()}")

        assert not violations, (
            "os.system() calls found. Use subprocess.run() instead:\n"
            + "\n".join(violations)
        )

    def test_no_bare_except_anywhere(self, project_root: Path) -> None:
        """Test that bare except: clauses are not used in any Python file."""
        violations = []
        bare_except_pattern = re.compile(r'\bexcept\s*:')

        for py_file in get_python_files(project_root):
            content = py_file.read_text()
            for i, line in enumerate(content.splitlines(), 1):
                if bare_except_pattern.search(line):
                    violations.append(f"{py_file}:{i}: {line.strip()}")

        assert not violations, (
            "Bare except: clauses found. Use specific exceptions:\n"
            + "\n".join(violations)
        )

    def test_all_python_files_compile(self, project_root: Path) -> None:
        """Test that all Python files have valid syntax."""
        failures = []
        for py_file in get_python_files(project_root):
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", str(py_file)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                failures.append(f"{py_file}: {result.stderr}")

        assert not failures, "Python syntax errors found:\n" + "\n".join(failures)

    def test_no_python2_only_imports(self, project_root: Path) -> None:
        """Test that Python 2-only imports are not used."""
        python2_imports = [
            "import urllib2",
            "from urllib2 import",
            "import ConfigParser",
            "from ConfigParser import",
        ]
        violations = []

        for py_file in get_python_files(project_root):
            content = py_file.read_text()
            for i, line in enumerate(content.splitlines(), 1):
                for py2_import in python2_imports:
                    if py2_import in line:
                        violations.append(f"{py_file}:{i}: {line.strip()}")

        assert not violations, (
            "Python 2-only imports found:\n" + "\n".join(violations)
        )


class TestPythonShebangStandards:
    """Test that Python scripts have proper shebangs."""

    def test_executable_scripts_have_python3_shebang(self, project_root: Path) -> None:
        """Test that all executable Python scripts use python3 in shebang."""
        violations = []
        # List of scripts that should be executable with shebangs
        expected_scripts = [
            "linux/diagnostic/high_cpu_parser.py",
            "linux/MDEAuditdAnalyzer/MDEAuditAnalyzer.py",
            "linux/LinuxMDEparser/json2excel.py",
            "linux/LinuxMDEparser/main.py",
            "linux/scheduler/schedule_scan.py",
            "linux/scheduler/schedule_update.py",
            "macos/jamf/download_profile.py",
            "macos/mdm/analyze_profiles.py",
            "macos/mobileconfig/combined/build_combined.py",
            "macos/schema/validator/validate-config-profile.py",
        ]

        for script_rel in expected_scripts:
            script_path = project_root / script_rel
            if script_path.exists():
                with open(script_path) as f:
                    first_line = f.readline().strip()

                if first_line.startswith("#!"):
                    if "python3" not in first_line:
                        violations.append(
                            f"{script_rel}: shebang '{first_line}' should use python3"
                        )
                else:
                    violations.append(f"{script_rel}: missing shebang")

        assert not violations, (
            "Shebang issues found:\n" + "\n".join(violations)
        )


class TestShellScriptStandards:
    """Test that shell scripts follow best practices."""

    def test_shell_scripts_have_valid_syntax(self, project_root: Path) -> None:
        """Test that all shell scripts have valid bash syntax."""
        failures = []
        for sh_file in get_shell_files(project_root):
            result = subprocess.run(
                ["bash", "-n", str(sh_file)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                failures.append(f"{sh_file}: {result.stderr}")

        assert not failures, "Shell syntax errors found:\n" + "\n".join(failures)

    def test_shell_scripts_have_shebang(self, project_root: Path) -> None:
        """Test that all shell scripts have a shebang."""
        violations = []
        for sh_file in get_shell_files(project_root):
            with open(sh_file) as f:
                first_line = f.readline().strip()

            if not first_line.startswith("#!"):
                violations.append(f"{sh_file}: missing shebang")
            elif "bash" not in first_line and "sh" not in first_line:
                violations.append(
                    f"{sh_file}: shebang '{first_line}' should reference bash or sh"
                )

        assert not violations, "Shebang issues found:\n" + "\n".join(violations)


class TestVersionConsistency:
    """Test that version information is consistent across the project."""

    def test_version_file_exists(self, project_root: Path) -> None:
        """Test that the VERSION file exists."""
        version_file = project_root / "VERSION"
        assert version_file.exists(), "VERSION file not found"

    def test_version_format(self, project_root: Path) -> None:
        """Test that the VERSION file contains a valid semver version."""
        version_file = project_root / "VERSION"
        version = version_file.read_text().strip()
        # Semantic versioning pattern
        semver_pattern = re.compile(r'^\d+\.\d+\.\d+(-[\w.]+)?(\+[\w.]+)?$')
        assert semver_pattern.match(version), (
            f"VERSION '{version}' does not match semver format"
        )

    def test_changelog_exists(self, project_root: Path) -> None:
        """Test that CHANGELOG.md exists."""
        changelog = project_root / "CHANGELOG.md"
        assert changelog.exists(), "CHANGELOG.md not found"

    def test_changelog_references_current_version(self, project_root: Path) -> None:
        """Test that CHANGELOG.md references the current version."""
        version_file = project_root / "VERSION"
        version = version_file.read_text().strip()
        changelog = project_root / "CHANGELOG.md"
        changelog_content = changelog.read_text()
        assert version in changelog_content, (
            f"CHANGELOG.md does not reference version {version}"
        )
