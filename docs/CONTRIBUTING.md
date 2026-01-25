# Contributing to mdatp-xplat

Thank you for your interest in contributing to the Microsoft Defender for Endpoint cross-platform tools repository!

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Submitting Changes](#submitting-changes)
- [Version Management](#version-management)

## Code of Conduct

This project follows the [Microsoft Open Source Code of Conduct](../CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## Getting Started

1. Fork the repository
2. Clone your fork locally
3. Set up your development environment (see below)
4. Create a feature branch from `main`
5. Make your changes
6. Submit a pull request

## Development Setup

### Prerequisites

- **Git**: For version control
- **Bash 4.0+**: For shell scripts
- **Python 3.8+**: For Python scripts and linting tools
- **ShellCheck**: For shell script linting
- **Pre-commit**: For automated checks

### Setup Steps

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/mdatp-xplat.git
cd mdatp-xplat

# Install Python development dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Verify setup
pre-commit run --all-files
```

### Installing ShellCheck

**Ubuntu/Debian:**
```bash
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

## Making Changes

### Branch Naming

Use descriptive branch names:
- `feature/add-rocky-linux-support`
- `fix/distro-detection-ubuntu-24`
- `docs/update-installation-guide`

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Formatting, no code change
- `refactor`: Code restructuring
- `test`: Adding tests
- `chore`: Maintenance tasks

**Examples:**
```
feat(installer): add support for Rocky Linux 9

fix(distro): handle VERSION_CODENAME missing on older systems

docs(readme): add troubleshooting section
```

## Coding Standards

### Shell Scripts

```bash
#!/bin/bash
set -euo pipefail

# Required at the top of every script
```

| Rule | Incorrect | Correct |
|------|-----------|---------|
| Quote variables | `$var` | `"$var"` |
| Test construct | `[ -z $var ]` | `[[ -z "$var" ]]` |
| Command check | `which cmd` | `command -v cmd` |
| Temp files | `tempFile="/tmp/file"` | `tmpfile=$(mktemp)` |

Run ShellCheck before committing:
```bash
shellcheck linux/**/*.sh macos/**/*.sh
```

### Python Scripts

```python
#!/usr/bin/env python3
"""Module docstring."""

from __future__ import annotations

import logging
from typing import ...

logger = logging.getLogger(__name__)
```

| Rule | Incorrect | Correct |
|------|-----------|---------|
| System calls | `os.system(cmd)` | `subprocess.run([...])` |
| Exceptions | `except:` | `except SpecificError:` |
| Type hints | None | Add to all functions |

Run Python linters before committing:
```bash
ruff check .
black --check .
mypy linux/ macos/
```

### YAML Files

- 2-space indentation
- No trailing whitespace
- Maximum line length: 120 characters

Run yamllint:
```bash
yamllint -c .yamllint.yml .
```

## Testing

### Running Tests

```bash
# Run all Python tests
pytest tests/python/ -v

# Run BATS tests (shell scripts)
bats tests/bats/

# Run with coverage
pytest tests/python/ -v --cov --cov-report=term-missing
```

### Writing Tests

**Python Tests:**
```python
# tests/python/test_example.py
import pytest

class TestExample:
    def test_something(self):
        assert True

    def test_something_else(self):
        with pytest.raises(ValueError):
            raise ValueError("expected")
```

**BATS Tests:**
```bash
# tests/bats/test_example.bats
#!/usr/bin/env bats

@test "script has valid syntax" {
    bash -n path/to/script.sh
}

@test "help option works" {
    run bash path/to/script.sh --help
    [ "$status" -eq 0 ]
    [[ "$output" =~ "usage" ]]
}
```

## Submitting Changes

### Before Submitting

1. **Run all linters:**
   ```bash
   pre-commit run --all-files
   ```

2. **Run tests:**
   ```bash
   pytest tests/python/ -v
   bats tests/bats/
   ```

3. **Update VERSION file** (for code changes):
   ```bash
   # Bump the version appropriately
   echo "1.0.1" > VERSION
   ```

4. **Update CHANGELOG.md**:
   ```markdown
   ## [1.0.1] - YYYY-MM-DD

   ### Fixed
   - Description of your fix
   ```

### Pull Request Process

1. Push your branch to your fork
2. Create a pull request to `main`
3. Fill out the PR template completely
4. Wait for CI checks to pass
5. Address any reviewer feedback
6. Once approved, your PR will be merged

### PR Checklist

- [ ] VERSION file updated
- [ ] CHANGELOG.md updated
- [ ] All tests pass
- [ ] ShellCheck passes for shell changes
- [ ] Python linters pass for Python changes
- [ ] Documentation updated if needed

## Version Management

See [VERSIONING.md](VERSIONING.md) for complete version policy.

### Quick Reference

- **PATCH** (1.0.x): Bug fixes, minor changes
- **MINOR** (1.x.0): New features, backward compatible
- **MAJOR** (x.0.0): Breaking changes

**Every code change requires a version bump and changelog entry.**

## Getting Help

- Open an issue for bugs or feature requests
- Tag issues with appropriate labels
- Join discussions in existing issues before creating duplicates

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
