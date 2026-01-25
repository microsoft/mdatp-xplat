# Versioning Policy

This project uses [Semantic Versioning](https://semver.org/) (SemVer) for all version numbers.

## Version Format

```
MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]
```

| Component | Description | Example |
|-----------|-------------|---------|
| MAJOR | Breaking changes | `2.0.0` |
| MINOR | New features (backward compatible) | `1.1.0` |
| PATCH | Bug fixes (backward compatible) | `1.0.1` |
| PRERELEASE | Pre-release identifier | `1.0.0-beta.1` |
| BUILD | Build metadata | `1.0.0+build.123` |

## When to Bump Versions

### MAJOR Version (Breaking Changes)

Increment when making incompatible changes:

- Removing or renaming command-line options
- Changing default behavior in breaking ways
- Removing support for operating systems or versions
- Changing exit codes for existing error conditions
- Breaking changes to configuration file formats

**Example:** Removing `--legacy` flag that users depend on.

### MINOR Version (New Features)

Increment when adding functionality in a backward-compatible manner:

- Adding new command-line options
- Adding support for new operating systems or versions
- Adding new scripts or tools
- Enhancing existing functionality without breaking changes
- Adding new optional configuration options

**Example:** Adding `--verbose` flag for detailed output.

### PATCH Version (Bug Fixes)

Increment for backward-compatible bug fixes:

- Fixing bugs in existing functionality
- Security fixes that don't change API
- Documentation corrections
- Performance improvements
- Fixing typos in output messages

**Example:** Fixing distro detection for Ubuntu 24.04.

## Version Bump Requirements

### Mandatory for Code Changes

Any change to the following files **MUST** include a version bump:

- `linux/**/*.sh` - Shell scripts
- `linux/**/*.py` - Python scripts
- `macos/**/*.py` - Python scripts
- `macos/**/*.sh` - Shell scripts
- `macos/mobileconfig/**` - Configuration profiles
- `macos/schema/**` - Schema files

### Not Required

Version bumps are not required for:

- Documentation-only changes (README, docs/)
- CI/CD configuration changes (.github/)
- Development tooling changes (pyproject.toml, .pre-commit-config.yaml)
- Test-only changes (tests/)

### Changelog Entry

Every version bump **SHOULD** include a corresponding entry in `CHANGELOG.md`:

```markdown
## [1.0.1] - 2026-01-24

### Fixed
- Fixed distro detection for Ubuntu 24.04 LTS
- Fixed quoting issues in mde_installer.sh
```

## How to Bump Version

### 1. Edit VERSION File

```bash
# Current version
cat VERSION
# 1.0.0

# Update to new version
echo "1.0.1" > VERSION
```

### 2. Update CHANGELOG.md

Add a new section at the top (after `## [Unreleased]` if present):

```markdown
## [1.0.1] - 2026-01-24

### Fixed
- Description of bug fix

### Added
- Description of new feature

### Changed
- Description of change

### Security
- Description of security fix
```

### 3. Commit Both Files

```bash
git add VERSION CHANGELOG.md
git commit -m "chore: bump version to 1.0.1"
```

## CI/CD Enforcement

### Pull Request Checks

The CI pipeline automatically:

1. Detects if versioned files were modified
2. Verifies VERSION file was updated
3. Validates version format follows SemVer
4. Warns if CHANGELOG.md wasn't updated

### Automated Releases

When VERSION changes on the `main` branch:

1. CI extracts the new version number
2. Creates a Git tag `v{VERSION}`
3. Generates a GitHub Release with changelog

## Individual Script Versions

Some scripts have internal version variables:

```bash
# mde_installer.sh
SCRIPT_VERSION="0.8.4"
```

These should be updated to read from the central VERSION file:

```bash
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ -f "${REPO_ROOT}/VERSION" ]]; then
    SCRIPT_VERSION=$(cat "${REPO_ROOT}/VERSION")
else
    SCRIPT_VERSION="0.8.4"  # Fallback
fi
```

## Version History

| Version | Date | Description |
|---------|------|-------------|
| 1.0.0 | 2026-01-24 | Initial versioned release with CI/CD |
| 0.8.4 | Pre-versioning | Legacy mde_installer.sh version |
| 0.0.2 | Pre-versioning | Legacy xplat_offline_updates version |

## FAQ

### Q: Do I need to bump version for a typo fix?

**A:** If it's in code (error messages, log output): Yes, PATCH bump.
If it's in documentation only: No.

### Q: What if my PR has multiple changes?

**A:** One version bump covers all changes in the PR. Choose the highest applicable bump level (MAJOR > MINOR > PATCH).

### Q: Can I skip the changelog?

**A:** You'll get a warning, but it's not blocking. However, it's strongly recommended to document changes.

### Q: What version do I use for a new feature that also fixes bugs?

**A:** Use MINOR for new features. Document both the feature and bug fixes in the changelog.
