# AGENTS.md - AI Agent Instructions for mdatp-xplat Repository

## Overview

This document provides instructions for AI coding agents working on the `mdatp-xplat` repository. Following these guidelines ensures consistent, high-quality contributions that align with the project's goals and coding standards.

## Repository Purpose

The `mdatp-xplat` repository contains auxiliary tools and samples for **Microsoft Defender for Endpoint** on Linux and macOS platforms. These tools are used in enterprise-scale deployments and must meet high standards for:

- **Security** - No command injection, proper input validation, secure file handling
- **Reliability** - Proper error handling, no race conditions, comprehensive testing
- **Maintainability** - Consistent coding standards, documentation, version tracking
- **Compatibility** - Support for multiple distros, Python versions, and package managers

---

## Critical Rules for AI Agents

### 1. Always Maintain a TODO List

Before starting ANY work:

1. Create a comprehensive TODO list with all major tasks
2. Break complex tasks into sub-tasks (max 5-7 items per task)
3. Update the TODO list as you progress, marking items complete
4. Never skip updating the TODO list between major actions

### 2. Version Management is Mandatory

**Every code change MUST include:**

1. Update to the `VERSION` file (semantic versioning: MAJOR.MINOR.PATCH)
2. Update to `CHANGELOG.md` with description of changes
3. Individual script version variables should read from central `VERSION` file

Version bump rules:
- **PATCH**: Bug fixes, documentation updates
- **MINOR**: New features, enhancements (backward compatible)
- **MAJOR**: Breaking changes

### 3. Testing Requirements

Before submitting any code change:

1. Run ShellCheck on all modified shell scripts
2. Run Python linters (ruff, black, mypy) on all modified Python files
3. Run existing tests and add new tests for new functionality
4. Verify no regressions introduced

### 4. Security-First Development

When modifying code:

1. **NEVER use naked `eval`** - Use `bash -c` with proper escaping or refactor
2. **Always quote variables** - `"$var"` not `$var`
3. **Use `mktemp`** for temporary files
4. **Validate all inputs** before using in commands or file operations
5. **Set proper file permissions** - onboarding files should be `root:mdatp` with `0660`

---

## Coding Standards

### Shell Scripts (Bash)

```bash
#!/bin/bash
set -euo pipefail

# Required at the top of every script
```

| Pattern | ❌ Avoid | ✅ Use Instead |
|---------|---------|----------------|
| Variable expansion | `$var` | `"$var"` |
| Test construct | `[ condition ]` | `[[ condition ]]` |
| Command check | `which cmd` | `command -v cmd` |
| Command substitution | `` `cmd` `` | `$(cmd)` |
| Empty check | `[ -z $var ]` | `[[ -z "$var" ]]` |
| Non-empty check | `[ ! -z "$var" ]` | `[[ -n "$var" ]]` |
| Temp files | `tempFile="temp.txt"` | `tmpfile=$(mktemp)` |
| Dynamic commands | `eval $cmd` | `bash -c "$cmd"` or refactor |

### Python Scripts

```python
#!/usr/bin/env python3
"""Module docstring."""

from __future__ import annotations

import logging
import subprocess
from typing import ...

# Configure logging (not print statements)
logger = logging.getLogger(__name__)
```

| Pattern | ❌ Avoid | ✅ Use Instead |
|---------|---------|----------------|
| System calls | `os.system(cmd)` | `subprocess.run([...], check=True)` |
| Exception handling | `except:` | `except SpecificError as e:` |
| Type hints | None | Add to all functions |
| Shebang | `#!/usr/bin/python` | `#!/usr/bin/env python3` |
| Temp files | `open('/tmp/file.txt')` | `tempfile.NamedTemporaryFile()` |

### YAML Files

- Use 2-space indentation
- Maximum line length: 120 characters
- No duplicate keys
- Quote strings containing special characters

---

## File Structure

```
mdatp-xplat/
├── .github/
│   ├── workflows/           # CI/CD pipelines
│   │   ├── ci.yml          # Main CI pipeline
│   │   ├── lint.yml        # Linting workflow
│   │   ├── test.yml        # Testing workflow
│   │   ├── release.yml     # Release automation
│   │   └── version-check.yml
│   ├── CODEOWNERS
│   └── pull_request_template.md
├── docs/
│   ├── CONTRIBUTING.md
│   ├── VERSIONING.md
│   └── DEVELOPMENT.md
├── tests/
│   ├── shellcheck/
│   ├── python/
│   ├── bats/
│   └── integration/
├── linux/                   # Linux-specific tools
├── macos/                   # macOS-specific tools
├── VERSION                  # Central version file
├── CHANGELOG.md
├── AGENTS.md               # This file
├── pyproject.toml
├── .shellcheckrc
├── .yamllint.yml
└── .pre-commit-config.yaml
```

---

## Common Tasks for AI Agents

### Task: Add a New Feature

1. Create TODO list with implementation steps
2. Write tests first (TDD approach)
3. Implement the feature
4. Update VERSION (bump MINOR version)
5. Update CHANGELOG.md
6. Run all linters and tests
7. Update documentation if needed

### Task: Fix a Bug

1. Write a failing test that reproduces the bug
2. Fix the bug
3. Verify the test passes
4. Update VERSION (bump PATCH version)
5. Update CHANGELOG.md with bug fix description
6. Run all linters and tests

### Task: Security Fix

1. Document the vulnerability in CHANGELOG.md under "Security"
2. Write tests that verify the vulnerability is fixed
3. Implement the fix
4. Update VERSION (bump PATCH or MINOR depending on scope)
5. Run security-focused tests

### Task: Refactoring

1. Ensure comprehensive tests exist before refactoring
2. Run tests before changes (baseline)
3. Refactor in small, incremental changes
4. Run tests after each change
5. Update VERSION (bump PATCH if behavior unchanged)
6. Update CHANGELOG.md

---

## Distro/Platform Support

### Linux Distributions

The installer script must support:

| Distro Family | Distributions |
|---------------|---------------|
| Debian | Ubuntu (16.04-24.04+), Debian (10-13+), Pop!_OS, Elementary, Linux Mint |
| RHEL | RHEL, CentOS, Rocky, AlmaLinux, Oracle Linux, Amazon Linux, Fedora |
| SUSE | SLES, openSUSE Leap, openSUSE Tumbleweed |
| Azure | Azure Linux (Mariner) |

### macOS Versions

Support macOS 10.15 (Catalina) and newer.

### Python Versions

All Python scripts must support Python 3.8 through 3.12+.

---

## Error Handling Guidelines

### Shell Scripts

```bash
# Always check command success
if ! command_that_might_fail; then
    log_error "Command failed: explanation"
    exit "$ERROR_CODE"
fi

# Use trap for cleanup
cleanup() {
    rm -f "$temp_file"
}
trap cleanup EXIT

# Provide meaningful error messages
script_exit "Failed to download GPG key from $url" "$ERR_FAILED_REPO_SETUP"
```

### Python Scripts

```python
try:
    result = subprocess.run(
        ["command", "arg"],
        check=True,
        capture_output=True,
        text=True
    )
except subprocess.CalledProcessError as e:
    logger.error(f"Command failed with exit code {e.returncode}: {e.stderr}")
    raise
except FileNotFoundError as e:
    logger.error(f"Command not found: {e}")
    raise
```

---

## Pre-commit Checklist

Before considering any task complete, verify:

- [ ] All shell scripts pass ShellCheck with no warnings
- [ ] All Python files pass ruff, black, and mypy checks
- [ ] All YAML files pass yamllint
- [ ] VERSION file has been updated appropriately
- [ ] CHANGELOG.md has been updated with changes
- [ ] All existing tests pass
- [ ] New tests added for new functionality
- [ ] No hardcoded paths or credentials
- [ ] Proper error handling in place
- [ ] Documentation updated if needed

---

## Using Subagents

For complex tasks, spawn subagents for:

1. **Research Tasks** - Investigating distro-specific behaviors
2. **Code Review** - Reviewing changes for security issues
3. **Testing** - Running test suites across multiple environments
4. **Documentation** - Generating or updating documentation

Always consolidate subagent findings before proceeding.

---

## References

- [Microsoft Defender for Endpoint Linux Documentation](https://learn.microsoft.com/en-us/defender-endpoint/microsoft-defender-endpoint-linux)
- [ShellCheck Wiki](https://www.shellcheck.net/wiki/)
- [Python Subprocess Documentation](https://docs.python.org/3/library/subprocess.html)
- [Semantic Versioning](https://semver.org/)
- [Keep a Changelog](https://keepachangelog.com/)
