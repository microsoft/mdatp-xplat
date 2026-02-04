# Development Guide

This guide covers setting up a development environment for contributing to the mdatp-xplat repository.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Development Environment](#development-environment)
- [Project Structure](#project-structure)
- [Running Tests](#running-tests)
- [Linting and Formatting](#linting-and-formatting)
- [Debugging](#debugging)
- [Common Tasks](#common-tasks)

## Prerequisites

### Required

| Tool | Version | Purpose |
|------|---------|---------|
| Git | 2.x+ | Version control |
| Bash | 4.0+ | Running shell scripts |
| Python | 3.8+ | Python scripts and tooling |
| pip | Latest | Python package management |

### Optional but Recommended

| Tool | Purpose |
|------|---------|
| ShellCheck | Shell script linting |
| BATS | Bash testing framework |
| Docker | Container-based testing |
| pre-commit | Git hooks |

## Quick Start

```bash
# Clone the repository
git clone https://github.com/microsoft/mdatp-xplat.git
cd mdatp-xplat

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install development dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Verify installation
pre-commit run --all-files
```

## Development Environment

### Virtual Environment Setup

We recommend using a Python virtual environment:

```bash
# Create virtual environment
python3 -m venv .venv

# Activate (Linux/macOS)
source .venv/bin/activate

# Activate (Windows)
.venv\Scripts\activate

# Deactivate when done
deactivate
```

### IDE Setup

#### VS Code

Recommended extensions:

- Python (ms-python.python)
- Pylance (ms-python.vscode-pylance)
- ShellCheck (timonwong.shellcheck)
- YAML (redhat.vscode-yaml)
- Bash IDE (mads-hartmann.bash-ide-vscode)

Settings (`.vscode/settings.json`):

```json
{
    "python.defaultInterpreterPath": ".venv/bin/python",
    "python.formatting.provider": "black",
    "editor.formatOnSave": true,
    "[python]": {
        "editor.codeActionsOnSave": {
            "source.organizeImports": true
        }
    },
    "shellcheck.enable": true,
    "shellcheck.run": "onSave"
}
```

### Installing ShellCheck

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install shellcheck
```

**macOS:**
```bash
brew install shellcheck
```

**Fedora/RHEL:**
```bash
sudo dnf install ShellCheck
```

### Installing BATS

**Ubuntu/Debian:**
```bash
sudo apt-get install bats
```

**macOS:**
```bash
brew install bats-core
```

**From source:**
```bash
git clone https://github.com/bats-core/bats-core.git
cd bats-core
./install.sh /usr/local
```

## Project Structure

```
mdatp-xplat/
├── .github/                    # GitHub configuration
│   ├── workflows/             # CI/CD pipelines
│   ├── CODEOWNERS
│   └── pull_request_template.md
├── docs/                       # Documentation
│   ├── CONTRIBUTING.md
│   ├── DEVELOPMENT.md         # This file
│   └── VERSIONING.md
├── linux/                      # Linux-specific tools
│   ├── installation/          # Installer scripts
│   ├── diagnostic/            # Diagnostic tools
│   ├── scheduler/             # Scheduling utilities
│   └── ...
├── macos/                      # macOS-specific tools
│   ├── jamf/                  # Jamf integration
│   ├── mobileconfig/          # Configuration profiles
│   └── ...
├── tests/                      # Test suites
│   ├── bats/                  # BATS tests for shell
│   ├── python/                # pytest tests
│   └── integration/           # Integration tests
├── VERSION                     # Version file
├── CHANGELOG.md               # Change history
├── pyproject.toml             # Python project config
├── .shellcheckrc              # ShellCheck config
├── .yamllint.yml              # YAML lint config
└── .pre-commit-config.yaml    # Pre-commit hooks
```

## Running Tests

### All Tests

```bash
# Run pre-commit checks (includes linting)
pre-commit run --all-files

# Run Python tests
pytest tests/python/ -v

# Run BATS tests
bats tests/bats/
```

### Python Tests

```bash
# Run all tests
pytest tests/python/

# Run with verbose output
pytest tests/python/ -v

# Run with coverage
pytest tests/python/ --cov --cov-report=term-missing

# Run specific test file
pytest tests/python/test_schedule_scan.py

# Run specific test
pytest tests/python/test_schedule_scan.py::TestScheduleScan::test_import_module

# Run with debugging
pytest tests/python/ -v --pdb
```

### BATS Tests

```bash
# Run all BATS tests
bats tests/bats/

# Run specific test file
bats tests/bats/mde_installer.bats

# Run with timing
bats --timing tests/bats/
```

### Shell Script Syntax Check

```bash
# Check single script
bash -n linux/installation/mde_installer.sh

# Check all scripts
find . -name "*.sh" -exec bash -n {} \;
```

## Linting and Formatting

### Pre-commit (All Checks)

```bash
# Run all checks
pre-commit run --all-files

# Run specific hook
pre-commit run shellcheck --all-files
pre-commit run black --all-files
```

### ShellCheck

```bash
# Check single file
shellcheck linux/installation/mde_installer.sh

# Check with specific severity
shellcheck -S warning linux/installation/mde_installer.sh

# Check all shell files
find . -name "*.sh" -exec shellcheck {} \;
```

### Python Linting

```bash
# Ruff (fast Python linter)
ruff check .
ruff check . --fix  # Auto-fix issues

# Black (formatter)
black .                    # Format all files
black --check .           # Check without modifying
black --diff .            # Show diff

# isort (import sorting)
isort .                   # Sort imports
isort --check-only .      # Check without modifying

# mypy (type checking)
mypy linux/ macos/
```

### YAML Linting

```bash
yamllint -c .yamllint.yml .
```

## Debugging

### Shell Scripts

```bash
# Run with debug output
bash -x linux/installation/mde_installer.sh --help

# Run with verbose tracing
set -x  # Add to script temporarily
```

### Python Scripts

```bash
# Run with debugger
python -m pdb linux/scheduler/schedule_scan.py

# Add breakpoint in code
import pdb; pdb.set_trace()

# Run tests with debugger on failure
pytest --pdb tests/python/
```

## Common Tasks

### Adding a New Shell Script

1. Create the script with proper header:
   ```bash
   #!/bin/bash
   set -euo pipefail

   # Your code here
   ```

2. Make it executable:
   ```bash
   chmod +x path/to/script.sh
   ```

3. Run ShellCheck:
   ```bash
   shellcheck path/to/script.sh
   ```

4. Add BATS tests in `tests/bats/`

5. Update VERSION and CHANGELOG.md

### Adding a New Python Script

1. Create the script with proper header:
   ```python
   #!/usr/bin/env python3
   """Module docstring."""

   from __future__ import annotations
   ```

2. Add type hints to all functions

3. Run linters:
   ```bash
   ruff check path/to/script.py
   black path/to/script.py
   mypy path/to/script.py
   ```

4. Add pytest tests in `tests/python/`

5. Update VERSION and CHANGELOG.md

### Testing on Different Distros

Use Docker for testing on different distributions:

```bash
# Ubuntu
docker run -it -v $(pwd):/workspace ubuntu:24.04 bash
cd /workspace
./linux/installation/mde_installer.sh --help

# Debian
docker run -it -v $(pwd):/workspace debian:12 bash

# Rocky Linux
docker run -it -v $(pwd):/workspace rockylinux:9 bash
```

### Releasing a New Version

1. Update VERSION:
   ```bash
   echo "1.1.0" > VERSION
   ```

2. Update CHANGELOG.md with changes

3. Commit and push:
   ```bash
   git add VERSION CHANGELOG.md
   git commit -m "chore: release version 1.1.0"
   git push origin main
   ```

4. CI will automatically create a release

## Troubleshooting

### Pre-commit fails

```bash
# Update hooks
pre-commit autoupdate

# Clear cache
pre-commit clean

# Reinstall hooks
pre-commit uninstall
pre-commit install
```

### ShellCheck not found

Ensure ShellCheck is installed and in PATH:
```bash
which shellcheck
shellcheck --version
```

### Python tests fail with import errors

Ensure you're in the virtual environment and dependencies are installed:
```bash
source .venv/bin/activate
pip install -e ".[dev]"
```

### BATS not found

Install BATS using your package manager or from source (see above).
