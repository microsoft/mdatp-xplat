# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.5.1] - 2026-01-29

### Fixed

- **E2E Test Suite**: Fixed Fedora 40 and 41 VM startup failures
  - Root cause: Official `fedora/40-cloud-base` and `fedora/41-cloud-base` Vagrant boxes
    return 404 errors when attempting to download from Vagrant Cloud
  - Solution: Switched Fedora 40/41 to use locally converted cloud images (`local/fedora40`,
    `local/fedora41`) matching the pattern used for Debian boxes and Fedora 43
  - Added Fedora 40 and 41 cloud image URLs to `convert_cloud_image.sh`
  - Updated `distro_parser.py` to reference local boxes for Fedora 40/41

### Added

- **E2E Test Suite**: Automatic local box building during test runs
  - New `BoxBuilder` class in `runner.py` detects missing `local/*` Vagrant boxes
  - Automatically runs `convert_cloud_image.sh` to build required boxes before tests
  - Filters out distros if their box build fails, allowing remaining tests to continue
  - Eliminates need to manually run `./scripts/convert_cloud_image.sh` before first test run

## [1.5.0] - 2026-01-27

### Added

- **E2E Test Suite**: Extended distro coverage with 4 new Linux distributions
  - Amazon Linux 2 (using `crystax/amazon2` Vagrant box with libvirt provider)
  - Amazon Linux 2023 (using `crystax/amazon2023` Vagrant box with libvirt provider)
  - Fedora 42 (using `alvistack/fedora-42` Vagrant box with libvirt provider)
  - Fedora 43 (using locally converted cloud image as `local/fedora43`)
- **convert_cloud_image.sh**: Added Fedora support for cloud image to Vagrant box conversion
  - Added `create_fedora_customize_script()` function for Fedora-specific VM customization
  - Added `get_distro_family()` and `get_guest_type()` helper functions
  - Added Fedora 43 cloud image URL to CLOUD_IMAGES array
  - Supports dnf package manager, sshd service, and wheel group for Fedora
- **distro_parser.py**: Added Fedora 42, Fedora 43, Amazon Linux 2, and Amazon Linux 2023 entries

## [1.4.1] - 2026-01-26

### Fixed

- **mde_installer.sh**: Fixed null byte validation that incorrectly rejected all paths
  - The pattern `*$'\0'*` expands to `**` in bash since bash strings cannot contain null bytes
  - Removed the broken check as bash naturally strips null bytes from input
- **mde_installer.sh**: Fixed multiple `set -u` (unbound variable) compatibility issues:
  - Added initialization of `log_path`, `SKIP_PMC_SETUP`, `INSTALL_PATH` variables at script startup
  - Fixed `http_proxy` and `ftp_proxy` access using `${var:-}` syntax in `get_rpm_proxy_params()`
  - Fixed `tags` associative array access check to avoid unbound error when empty
- **mde_installer.sh**: Fixed `set -eo pipefail` compatibility issues causing silent script exits:
  - Fixed `find_service()` to use `|| true` when checking non-existent services
  - Fixed `verify_conflicting_applications()` fanotify detection pipeline to use `|| true`
  - Fixed yum repolist check in `install_on_fedora()` to use if-statement instead of exit-code capture
- **mde_installer.sh**: Updated fallback version constant from 1.2.0 to 1.4.1

## [1.4.0] - 2026-01-26

### Added

- **E2E Test Suite**: Comprehensive end-to-end testing infrastructure for MDE Linux installer
  - Vagrant-based test automation with libvirt KVM provider support
  - Automatic distro discovery from `mde_installer.sh` (13+ distros: Ubuntu, Debian, RHEL family, SLES, Azure Linux)
  - Full installation and onboarding workflow testing on isolated VMs
  - Device health validation using `mdatp health --output json`
  - Parallel test execution with configurable CPU/memory budgeting
  - Failure log collection and markdown summary reporting
  - Secret management for sensitive onboarding/managed config/offboarding JSON files
  - Per-distro provisioning scripts handling OS-specific setup
  - Flexible test filtering (--all, --distro, --family, --distros)
  - Dry-run capability and custom resource allocation options
  - Comprehensive documentation in `tests/e2e/README.md`

## [1.3.0] - 2026-01-25

### Security

- **SEC-002: Input Validation for CLI Arguments**
  - Added `validate_path()` function to check for path traversal, null bytes, and shell metacharacters
  - Added `validate_script_path()` for onboarding/offboarding script validation
  - Added `validate_install_path()` for installation directory validation with allowed prefix restrictions
  - All CLI path arguments now validated before use

- **SEC-007: GPG Key Fingerprint Verification**
  - Added `MICROSOFT_GPG_FINGERPRINT` and `MICROSOFT_2025_GPG_FINGERPRINT` constants
  - Added `verify_gpg_key_fingerprint()` function to verify downloaded keys
  - Added `download_and_verify_gpg_key()` wrapper for secure key download and verification
  - Keys are now verified against known-good fingerprints before installation

- **SEC-008: Modern apt Key Handling**
  - GPG keys now stored in `/usr/share/keyrings/microsoft-prod.gpg`
  - Sources.list entries use `signed-by` attribute on modern systems
  - Legacy fallback maintained for older systems with fingerprint verification

### Fixed
- **REL-003: Improved Error Reporting**
  - Rewrote `script_exit()` function with clear `[SUCCESS]` and `[FAILED]` prefixes
  - Added hints for common error codes to help users troubleshoot
  - Success and failure messages are now clearly distinguished

- **REL-006: Timeout Handling**
  - Added `run_with_timeout()` function for operations that may hang
  - Sends SIGTERM followed by SIGKILL for graceful process termination
  - Logs appropriate timeout messages with exit codes

- **CQ-SH-001: Quoted Variables**
  - Quoted critical variable expansions in file operations
  - Fixed `$ONBOARDING_SCRIPT`, `$OFFBOARDING_SCRIPT`, `$INSTALL_PATH` quoting
  - Prevents word splitting and glob expansion vulnerabilities

- **CQ-PY-007: Python Input Validation**
  - Added `validate_path()` function to `main.py` for path validation
  - Added `--top` argument validation to `high_cpu_parser.py` (must be positive)
  - Added JSON data structure validation in `high_cpu_parser.py`

### Added

- **Regression Test Suite**
  - `tests/python/test_security_reliability.py`: 30 tests covering all security and reliability fixes
  - Tests verify: input validation functions, GPG verification, error reporting, timeout handling
  - Tests ensure Python scripts validate inputs and have proper syntax
  - BATS tests added for shell script security functions

- **CI/CD Security Scanning**
  - Added zizmor-action to GitHub Actions workflows for security scanning of workflow files

## [1.2.0] - 2026-01-24

### Added

- **Comprehensive Test Suite**
  - `tests/python/test_linuxmdeparser.py`: Tests for json2excel.py and main.py
  - `tests/python/test_mdeauditanalyzer.py`: Tests for MDEAuditAnalyzer.py
  - `tests/python/test_macos.py`: Tests for macOS Python scripts (download_profile.py, analyze_profiles.py, build_combined.py, validate-config-profile.py)
  - `tests/python/test_code_quality.py`: Codebase-wide regression tests for banned patterns
  - Tests verify: no os.system() usage, no bare except: clauses, valid Python syntax, proper shebangs, version consistency

### Fixed

- **Python Script Modernization**
  - `linux/diagnostic/high_cpu_parser.py`: Added shebang, type hints, logging, error handling
  - `linux/MDEAuditdAnalyzer/MDEAuditAnalyzer.py`: Complete rewrite with argparse, context managers, regex parsing, type hints
  - `linux/LinuxMDEparser/json2excel.py`: Rewritten with type hints, logging, proper error handling
  - `linux/LinuxMDEparser/main.py`: Rewritten with argparse, logging, proper structure
  - `macos/jamf/download_profile.py`: Updated to Python 3 only, added type hints, proper error handling, logging
  - `macos/mdm/analyze_profiles.py`: Fixed os.system calls, replaced with subprocess.run
  - `macos/mobileconfig/combined/build_combined.py`: Fixed bare except clauses
  - `macos/schema/validator/validate-config-profile.py`: Added shebang, fixed bare except clauses, removed Python 2 fallback
  - All Python scripts now use `subprocess` instead of `os.system()`
  - All Python scripts now use `logging` module instead of `print()` statements
  - Removed all Python 2 compatibility code

### Changed

- **Documentation Updates**
  - Marked all security, reliability, and code quality issues as complete

### Security

- Removed bare `except:` clauses from all Python scripts
- Added proper exception handling with specific exception types
- Credentials in `download_profile.py` now handled more securely with proper error handling

## [1.1.0] - 2026-01-24

### Added

- **New Distribution Support**
  - Oracle Linux 10
  - Ubuntu 25.04 (Plucky Puffin)
  - Ubuntu 25.10
  - Rocky Linux 10
  - RHEL 10
- **Version Check Pipeline Improvements**
  - Added embedded version consistency checking
  - Validates fallback versions in scripts match central VERSION file
  - Checks Python `__version__` variables for consistency

### Changed

- **Debian/Ubuntu Repository File Naming**
  - Changed from `microsoft-$CHANNEL.list` to `microsoft-$DISTRO-$CODENAME-$CHANNEL.list`
  - Aligns with Microsoft Intune documentation standards
  - Cleanup now handles both old and new naming conventions
- **GPG Key Handling**
  - Extended new GPG key format support to Ubuntu 25.04 and 25.10
- **Comprehensive .gitignore**
  - Added Python cache and virtual environment patterns
  - Added IDE/editor patterns (VS Code, JetBrains, Vim, Emacs)
  - Added OS-specific patterns (macOS, Windows, Linux)
  - Added test output and log file patterns

## [1.0.0] - 2026-01-24

### Added

- CI/CD pipeline with GitHub Actions
  - ShellCheck linting for all shell scripts
  - Python linting with ruff, black, isort, and mypy
  - YAML linting with yamllint
  - Automated testing with pytest and BATS
  - Version bump enforcement on PRs
  - Automated release creation
- Comprehensive test suite
  - BATS tests for shell scripts
  - pytest tests for Python modules
  - Test fixtures and helpers
- Pre-commit hooks for code quality
  - Trailing whitespace removal
  - End of file fixer
  - YAML/JSON validation
  - Private key detection
  - ShellCheck integration
- Centralized version management
  - Single `VERSION` file for all components
  - Semantic versioning enforcement
  - Automated changelog tracking
- Documentation
  - `AGENTS.md` for AI coding agents
  - `CONTRIBUTING.md` with contribution guidelines
  - `VERSIONING.md` with version policy
  - `DEVELOPMENT.md` with developer setup guide

### Fixed

- **mde_installer.sh**
  - Added `set -euo pipefail` for strict error handling
  - Replaced naked `eval` statements with safer alternatives
  - Fixed distro detection for Ubuntu derivatives (Pop!_OS, Elementary, Linux Mint)
  - Fixed distro detection for Debian derivatives (Kali, Parrot)
  - Added proper file permissions for onboarding files (`root:mdatp`, `0660`)
  - Fixed TOCTOU bugs with atomic file operations
  - Fixed quoting issues throughout the script
  - Improved GPG key handling for newer distros
  - Added support for dnf on modern Fedora systems
- **Python scripts**
  - Replaced `os.system()` calls with `subprocess.run()`
  - Added proper exception handling
  - Added type hints
  - Replaced print statements with logging
  - Fixed shebang consistency (`#!/usr/bin/env python3`)
- **xplat_offline_updates_download.sh**
  - Fixed predictable temporary file names
  - Added proper error propagation

### Changed

- Updated README.md with development and testing information
- Standardized error messages and exit codes
- Improved logging throughout all scripts

### Security

- Removed command injection vulnerabilities from `eval` statements
- Added input validation for command-line arguments
- Secure temporary file handling with `mktemp`
- Proper credential handling in Python scripts
