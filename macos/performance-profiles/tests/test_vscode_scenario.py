"""Tests for VS Code scenario build mode behavior."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from demo_framework.scenarios.vscode import VSCodeScenario


class TestVSCodeScenarioBuildModes:
    """Validate compile-only vs install+compile behavior."""

    def test_setup_installs_dependencies_by_default(self, tmp_path: Path):
        repo = tmp_path / "vscode"
        repo.mkdir()

        scenario = VSCodeScenario(repo_path=repo, include_install_in_build=False)

        with patch("demo_framework.scenarios.vscode.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            ok = scenario.setup()

        assert ok is True
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert ["npm", "install"] in calls

    def test_setup_skips_dependency_install_when_included_in_build(self, tmp_path: Path):
        repo = tmp_path / "vscode"
        repo.mkdir()

        scenario = VSCodeScenario(repo_path=repo, include_install_in_build=True)

        with patch("demo_framework.scenarios.vscode.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            ok = scenario.setup()

        assert ok is True
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert ["npm", "install"] not in calls

    def test_baseline_runs_install_then_compile_when_enabled(self, tmp_path: Path):
        repo = tmp_path / "vscode"
        repo.mkdir()

        scenario = VSCodeScenario(repo_path=repo, include_install_in_build=True)

        with patch("demo_framework.scenarios.vscode.subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),  # remove profile
                MagicMock(returncode=0),  # npm install
                MagicMock(returncode=0),  # npm run compile
            ]
            ok = scenario.build_baseline()

        assert ok is True
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert calls[1] == ["npm", "install"]
        assert calls[2] == ["npm", "run", "compile"]

    def test_baseline_runs_compile_only_when_install_not_included(self, tmp_path: Path):
        repo = tmp_path / "vscode"
        repo.mkdir()

        scenario = VSCodeScenario(repo_path=repo, include_install_in_build=False)

        with patch("demo_framework.scenarios.vscode.subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),  # remove profile
                MagicMock(returncode=0),  # npm run compile
            ]
            ok = scenario.build_baseline()

        assert ok is True
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert ["npm", "install"] not in calls
        assert ["npm", "run", "compile"] in calls
