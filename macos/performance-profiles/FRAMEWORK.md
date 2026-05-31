# Python Demo Framework

The new Python-based demo framework replaces the bash script with a more extensible, testable, and maintainable architecture.

## Quick Start

### Recommended: Bootstrap Script

```bash
./perf-profile-demo.sh
```

The bootstrap script will:
- create and activate `venv` if needed
- install/update dependencies from `requirements.txt`
- prompt for scenario selection (`vscode`, `xcode`, or `android-studio`)
- launch the Python framework

### Install Dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Run VS Code Demo

```bash
python3 demo.py
```

### Run Tests

```bash
pytest
```

## Architecture

### Core Modules

#### `demo_framework/orchestrator.py`
- **`DemoOrchestrator`** — Manages phases, execution flow, and result tracking
- **`CommandRunner`** — Execute shell commands with output capture
- **`PhaseStatus`/`PhaseResult`** — Track phase execution state

#### `demo_framework/scenarios/profiled_build.py`
- **`ProfiledBuildScenario`** — Shared, data-driven scenario foundation for:
    - setup/tool checks
    - baseline profile removal and cleanliness guard
    - baseline telemetry analysis phase (standardized phase 3)
    - profile apply flow (including admin-only handling)
    - optimized build execution
    - standardized analysis summary/reporting
    - hot-event artifact capture to `~/demo/results` (prevents generated JSON files from being written into source repos)

Standard phase template (used as the model for scenarios):
1. Setup and Preflight
2. Baseline Build (No Profiles)
3. Analyze Baseline Telemetry
4. Apply Performance Profiles
5. Optimized Build (With Profiles)
6. Analyze Impact

#### `demo_framework/preflight.py`
- **`Preflight`** — Check prerequisites (MDE, Node.js, Xcode CLT, build tools)
- Interactive installation prompts (matching UX of bash version)
- Version validation and enforcement

#### `demo_framework/ui.py`
- **`Spinner`** — Animated progress for long operations
- Helper functions for formatted output (success, error, warning, info)
- Context manager pattern for clean resource management

### Scenarios

Scenarios are extensible demo templates. Each scenario:
- Inherits from `DemoScenario` base class
- Implements setup, build phases, and analysis
- Registers phases with orchestrator
- Can be easily extended or reused

#### Available Scenarios

- **`VSCodeScenario`** — Build microsoft/vscode, showing profile impact
    - Migrated to the shared `ProfiledBuildScenario` foundation while keeping VS Code-specific telemetry/recommendation logic in framework hooks
- **`XcodeScenario`** — Build microsoft/fluentui-apple with Swift toolchain
    - Uses `swift build -c release` (compatible with current repo layout)
    - Includes a fresh `git clone` in baseline and optimized phases so `git` profile impact is measurable
- **`AndroidStudioScenario`** — Build/test/install/launch local Android app on emulator
    - Uses local app at `apps/hello-defender-android`
    - Baseline/optimized flow: `clean` -> `connectedDebugAndroidTest` -> `assembleDebug` -> `adb install` -> `adb shell am start`
    - Auto-detects Android SDK tools from PATH, `ANDROID_SDK_ROOT`, `ANDROID_HOME`, and default `~/Library/Android/sdk`
    - Requires Android Studio installed and at least one configured AVD in Device Manager

### Example: Create New Scenario

```python
from demo_framework.scenarios import DemoScenario, ScenarioConfig

class MyProjectScenario(DemoScenario):
    def __init__(self):
        config = ScenarioConfig(
            name="My Project Demo",
            repo_url="https://github.com/user/project.git",
            profiles=["node", "git"]
        )
        super().__init__(config)
        self._register_phases()

    def _register_phases(self):
        self.orchestrator.add_phase("Setup", self.setup)
        self.orchestrator.add_phase("Baseline", self.build_baseline)
        # ... more phases

    def setup(self) -> bool:
        # Your setup logic
        return True

    # Implement other abstract methods...
```

## Testing

Tests are organized by module:

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_orchestrator.py

# Run with coverage
pytest --cov=demo_framework tests/
```

### Writing Tests

```python
import pytest
from demo_framework.orchestrator import DemoOrchestrator

def test_orchestrator_adds_phases():
    orch = DemoOrchestrator("test")
    orch.add_phase("Phase 1", lambda: "output")
    assert len(orch.phases) == 1
```

## File Structure

```
macos/performance-profiles/
├── demo.py                          # Main entry point
├── perf-profile-demo.sh             # Shell bootstrap launcher (recommended)
├── requirements.txt                 # Python dependencies
├── pytest.ini                       # Pytest configuration
├── README.md                        # Documentation
│
├── demo_framework/                  # Core framework
│   ├── __init__.py
│   ├── orchestrator.py             # Phase management
│   ├── preflight.py                # Prerequisites checking
│   ├── ui.py                       # UI/spinners/output
│   │
│   └── scenarios/                  # Demo scenario templates
│       ├── __init__.py
│       ├── base.py                 # Base scenario class
│       ├── android_studio.py       # Android Studio emulator scenario
│       ├── vscode.py               # VS Code scenario
│       └── xcode.py                # Xcode scenario
│
├── apps/                           # Local app fixtures for scenarios
│   ├── hello-defender-android/
│   └── hello-defender-ios/
│
├── tests/                          # Test suite
│   ├── __init__.py
│   ├── test_android_studio_scenario.py
│   ├── test_orchestrator.py
│   ├── test_preflight.py
│   └── test_scenarios.py           # (Optional extension)
│
└── README.md                       # (Legacy) Original docs
```

## Migration from Bash

The Python framework has feature parity with the original bash scripts:

| Feature | Bash | Python |
|---------|------|--------|
| Preflight checks | ✅ | ✅ |
| Node.js version validation | ✅ | ✅ |
| Interactive tool installation | ✅ | ✅ |
| Phase execution tracking | ✅ | ✅ |
| Real-time output | ✅ | ✅ |
| State resumption | ✅ | ✅ (via `--resume-from`) |
| Testing | ❌ | ✅ |
| Extensible scenarios | ❌ | ✅ |

## Future Enhancements

- [ ] Add macOS-native build scenario  
- [ ] Rich progress bars with `rich` library
- [ ] Save/restore state across runs
- [ ] Parallel phase execution
- [ ] Performance metrics dashboard
- [ ] Integration with GitHub Actions/CI
- [ ] Web UI for interactive demos

## Command Reference

```bash
# Prompt and choose scenario interactively
python3 demo.py

# Run VS Code demo directly
python3 demo.py vscode

# Run VS Code demo with full developer build timing (install + compile)
python3 demo.py vscode --include-install

# Require Client Analyzer in preflight (auto-prompt install if missing)
python3 demo.py vscode --require-client-analyzer

# Override Client Analyzer install/detection directory
python3 demo.py vscode --require-client-analyzer --client-analyzer-dir ~/demo/analyzer/custom

# Client Analyzer preference across scenarios (user/environment driven)
python3 demo.py xcode --client-analyzer-mode on
python3 demo.py android-studio --client-analyzer-mode off
export MDE_DEMO_CLIENT_ANALYZER=on   # auto|on|off

# Temporary AV exclusion workflow preference (parallel to profile workflow)
python3 demo.py xcode --av-exclusions-mode auto
python3 demo.py xcode --av-exclusions-mode on
export MDE_DEMO_AV_EXCLUSIONS=auto   # auto|on|off

# NOTE: The current XMDE Client Analyzer package is Python-based
# (mde_support_tool.sh + mde_tools/) and no longer provides SupportToolMacOSBinary.zip.
# This integration is validated with the latest package from
# https://aka.ms/XMDEClientAnalyzerBinary; older package layouts may not
# be detected or may behave differently.
# If you run analyzer manually, use:
#   ./mde_support_tool.sh -h
#   sudo ./mde_support_tool.sh performance --length 30

# Choose hot-event analysis mode directly
python3 demo.py vscode --hot-events-analysis python
python3 demo.py vscode --hot-events-analysis ghcp
python3 demo.py vscode --hot-events-analysis both

# Phase 6 is non-interactive and always prints a clean summary report,
# including hot-event aggregates (before/after/delta) and profiles applied.
# Use ghcp or both only if you also want optional GHCP narrative output.

# During phase 3, the flow is intentionally two user-facing steps:
# 1) Collect baseline logs
#    - hot-event telemetry (always expected)
#    - optional Client Analyzer output
# 2) Analyze telemetry and choose profiles
#    - recommendations are generated from hot events and available profiles
#      discovered from mdatp CLI
#
# MDE diagnostic bundle export is treated as a fallback artifact collection step
# (not a separate decision/analysis step). It can overlap with Client Analyzer
# content, so when Client Analyzer output is present the framework may skip the
# mdatp diagnostic bundle export.
# Default behavior is GHCP-first recommendation; if GHCP is unavailable or
# returns no profile matches, it falls back to Python heuristics.
# GHCP is asked to emit a machine-readable line:
# RECOMMENDED_PROFILES: profile1, profile2
# so phase 4 can directly apply the parsed profile list.
# Phase 4 then applies the selected recommendation set.
#
# When the temporary exclusion workflow is enabled and Client Analyzer output
# exists, GHCP may also emit EXCLUSION_CANDIDATES. These can be applied as
# temporary exclusions for the optimized retest and are removed automatically
# during analysis cleanup.

# Run Xcode demo directly
python3 demo.py xcode

# Run Android Studio demo directly
python3 demo.py android-studio

# Run Android Studio demo from bootstrap script
./perf-profile-demo.sh android-studio

# Bootstrap prewarms sudo credentials once by default to reduce repeated prompts.
# Opt out if needed:
./perf-profile-demo.sh --no-sudo-prep xcode

# Run with custom repo path
python3 demo.py vscode --repo ~/my-vscode

# Resume from phase 3
python3 demo.py vscode --resume-from 3

# Show help
python3 demo.py --help

# Run tests
pytest

# Run tests with coverage
pytest --cov=demo_framework

# Run specific test
pytest tests/test_preflight.py::TestPreflight::test_check_node_version_valid
```
