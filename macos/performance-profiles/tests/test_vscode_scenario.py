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

        with patch.object(scenario, "_get_profile_state", return_value=(False, set())):
            with patch("demo_framework.scenarios.vscode.subprocess.run") as mock_run:
                mock_run.side_effect = [
                    MagicMock(returncode=0),  # remove profile node
                    MagicMock(returncode=0),  # remove profile git
                    MagicMock(returncode=0),  # remove profile vscode
                    MagicMock(returncode=0),  # remove profile vscode-tree
                    MagicMock(returncode=0),  # npm install
                    MagicMock(returncode=0),  # npm run compile
                ]
                ok = scenario.build_baseline()

        assert ok is True
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert ["npm", "install"] in calls
        assert ["npm", "run", "compile"] in calls
        assert calls.index(["npm", "install"]) < calls.index(["npm", "run", "compile"])

    def test_baseline_runs_compile_only_when_install_not_included(self, tmp_path: Path):
        repo = tmp_path / "vscode"
        repo.mkdir()

        scenario = VSCodeScenario(repo_path=repo, include_install_in_build=False)

        with patch.object(scenario, "_get_profile_state", return_value=(False, set())):
            with patch("demo_framework.scenarios.vscode.subprocess.run") as mock_run:
                mock_run.side_effect = [
                    MagicMock(returncode=0),  # remove profile node
                    MagicMock(returncode=0),  # remove profile git
                    MagicMock(returncode=0),  # remove profile vscode
                    MagicMock(returncode=0),  # remove profile vscode-tree
                    MagicMock(returncode=0),  # npm run compile
                ]
                ok = scenario.build_baseline()

        assert ok is True
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert ["npm", "install"] not in calls
        assert ["npm", "run", "compile"] in calls

    def test_apply_profiles_returns_false_in_admin_only_when_profiles_missing(self, tmp_path: Path):
        repo = tmp_path / "vscode"
        repo.mkdir()

        scenario = VSCodeScenario(repo_path=repo)

        with patch.object(
            scenario,
            "_get_profile_state",
            return_value=(True, {"node"}),
        ):
            ok = scenario.apply_profiles()

        assert ok is False

    def test_apply_profiles_uses_apply_command_when_not_admin_only(self, tmp_path: Path):
        repo = tmp_path / "vscode"
        repo.mkdir()

        scenario = VSCodeScenario(repo_path=repo)

        with patch.object(
            scenario,
            "_get_profile_state",
            return_value=(False, set()),
        ):
            with patch("demo_framework.scenarios.vscode.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                ok = scenario.apply_profiles()

        assert ok is True
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert ["sudo", "mdatp", "performance-profiles", "apply", "--name", "node"] in calls
