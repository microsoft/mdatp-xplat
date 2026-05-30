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

    def test_setup_fails_for_admin_only_when_profiles_already_applied(self, tmp_path: Path):
        repo = tmp_path / "vscode"
        repo.mkdir()

        scenario = VSCodeScenario(repo_path=repo)

        with patch.object(
            scenario,
            "_get_profile_state",
            side_effect=[(True, {"node", "vscode"}), (True, {"node", "vscode"})],
        ):
            ok = scenario.setup()

        assert ok is False

    def test_run_resumes_from_phase_4_when_state_exists_and_user_continues(self, tmp_path: Path):
        repo = tmp_path / "vscode"
        repo.mkdir()

        scenario = VSCodeScenario(repo_path=repo)
        scenario.state_file = tmp_path / ".vscode-demo-state.json"
        scenario.state_file.write_text('{"baseline_complete": true, "baseline_duration_seconds": 42.0}')

        with patch("builtins.input", return_value="c"):
            with patch.object(scenario.orchestrator, "cache_sudo", return_value=True):
                with patch.object(scenario.orchestrator, "run", return_value=False) as mock_run:
                    ok = scenario.run()

        assert ok is False
        mock_run.assert_called_once_with(resume_from=3)

    def test_run_restarts_when_state_exists_and_user_chooses_restart(self, tmp_path: Path):
        repo = tmp_path / "vscode"
        repo.mkdir()

        scenario = VSCodeScenario(repo_path=repo)
        scenario.state_file = tmp_path / ".vscode-demo-state.json"
        scenario.state_file.write_text('{"baseline_complete": true, "baseline_duration_seconds": 42.0}')

        with patch("builtins.input", return_value="r"):
            with patch.object(scenario.orchestrator, "cache_sudo", return_value=True):
                with patch.object(scenario.orchestrator, "run", return_value=False) as mock_run:
                    ok = scenario.run()

        assert ok is False
        mock_run.assert_called_once_with(resume_from=None)
        assert not scenario.state_file.exists()

    def test_collect_diagnostics_saves_baseline_checkpoint(self, tmp_path: Path):
        repo = tmp_path / "vscode"
        repo.mkdir()

        scenario = VSCodeScenario(repo_path=repo)
        scenario.state_file = tmp_path / ".vscode-demo-state.json"

        scenario.orchestrator.results = [
            MagicMock(name="Setup and Preflight", duration_seconds=1.0),
            MagicMock(name="Baseline Build (No Profiles)", duration_seconds=123.4),
        ]
        scenario.orchestrator.results[0].name = "Setup and Preflight"
        scenario.orchestrator.results[1].name = "Baseline Build (No Profiles)"

        with patch("demo_framework.scenarios.vscode.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            ok = scenario._collect_diagnostics()

        assert ok is True
        assert scenario.state_file.exists()
        state = scenario.state_file.read_text()
        assert "baseline_complete" in state
