# Python Demo Framework

The new Python-based demo framework replaces the bash script with a more extensible, testable, and maintainable architecture.

## Quick Start

### Install Dependencies

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Run VS Code Demo

```bash
python demo.py vscode
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
- **`XCodeScenario`** — (Planned) Build Xcode/Swift projects

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
│       ├── vscode.py               # VS Code scenario
│       └── xcode.py                # (Planned) Xcode scenario
│
├── tests/                          # Test suite
│   ├── __init__.py
│   ├── test_orchestrator.py
│   ├── test_preflight.py
│   └── test_scenarios.py           # (Planned)
│
├── perf-profile-demo.sh            # (Legacy) Bash version
├── perf-profile-demo-xcode.sh      # (Legacy) Bash Xcode demo
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

- [ ] Add Xcode scenario
- [ ] Add macOS-native build scenario  
- [ ] Rich progress bars with `rich` library
- [ ] Save/restore state across runs
- [ ] Parallel phase execution
- [ ] Performance metrics dashboard
- [ ] Integration with GitHub Actions/CI
- [ ] Web UI for interactive demos

## Command Reference

```bash
# Run VS Code demo
python demo.py vscode

# Run with custom repo path
python demo.py vscode --repo ~/my-vscode

# Resume from phase 3
python demo.py vscode --resume-from 3

# Show help
python demo.py --help

# Run tests
pytest

# Run tests with coverage
pytest --cov=demo_framework

# Run specific test
pytest tests/test_preflight.py::TestPreflight::test_check_node_version_valid
```
