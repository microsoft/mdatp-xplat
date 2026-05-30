from pathlib import Path
from unittest.mock import MagicMock, patch

from demo_framework.scenarios.profiled_build import ProfiledBuildScenario
from demo_framework.scenarios.vscode import VSCodeScenario


class TestVSCodeScenarioConfig:
    def test_vscode_scenario_uses_profiled_build_base(self, tmp_path: Path):
        scenario = VSCodeScenario(repo_path=tmp_path / "vscode")
        assert isinstance(scenario, ProfiledBuildScenario)

    def test_vscode_scenario_wires_expected_common_options(self, tmp_path: Path):
        scenario = VSCodeScenario(repo_path=tmp_path / "vscode")
        assert scenario.clone_args == ["--depth", "1", "--branch", "1.122.1"]
        assert scenario.install_command == ["npm", "install"]
        assert scenario.enable_resume_checkpoint is True
        assert scenario.enable_client_analyzer is True

    def test_setup_installs_dependencies_by_default(self, tmp_path: Path):
        repo = tmp_path / "vscode"
        repo.mkdir()

        scenario = VSCodeScenario(repo_path=repo, include_install_in_build=False)

        with patch.object(scenario, "_get_profile_state", return_value=(False, set())):
            with patch("demo_framework.scenarios.profiled_build.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                ok = scenario.setup()

        assert ok is True
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert ["npm", "install"] in calls

    def test_setup_skips_dependency_install_when_included_in_build(self, tmp_path: Path):
        repo = tmp_path / "vscode"
        repo.mkdir()

        scenario = VSCodeScenario(repo_path=repo, include_install_in_build=True)

        with patch.object(scenario, "_get_profile_state", return_value=(False, set())):
            with patch("demo_framework.scenarios.profiled_build.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                ok = scenario.setup()

        assert ok is True
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert ["npm", "install"] not in calls

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

    def test_run_ignores_stale_resume_state_and_starts_fresh(self, tmp_path: Path):
        repo = tmp_path / "vscode"
        repo.mkdir()

        scenario = VSCodeScenario(repo_path=repo)
        scenario.state_file = tmp_path / ".vscode-demo-state.json"
        scenario.state_file.write_text(
            '{"baseline_complete": true, "baseline_duration_seconds": 42.0, "created_at_epoch": 1}'
        )

        with patch("builtins.input") as mock_input:
            with patch.object(scenario.orchestrator, "cache_sudo", return_value=True):
                with patch.object(scenario.orchestrator, "run", return_value=False) as mock_run:
                    ok = scenario.run()

        assert ok is False
        assert not scenario.state_file.exists()
        mock_input.assert_not_called()
        mock_run.assert_called_once_with(resume_from=None)

    def test_run_ignores_zero_duration_resume_state_and_starts_fresh(self, tmp_path: Path):
        repo = tmp_path / "vscode"
        repo.mkdir()

        scenario = VSCodeScenario(repo_path=repo)
        scenario.state_file = tmp_path / ".vscode-demo-state.json"
        scenario.state_file.write_text(
            '{"baseline_complete": true, "baseline_duration_seconds": 0.0, "created_at_epoch": 1780164049.0}'
        )

        with patch("builtins.input") as mock_input:
            with patch.object(scenario.orchestrator, "cache_sudo", return_value=True):
                with patch.object(scenario.orchestrator, "run", return_value=False) as mock_run:
                    ok = scenario.run()

        assert ok is False
        assert not scenario.state_file.exists()
        mock_input.assert_not_called()
        mock_run.assert_called_once_with(resume_from=None)

    def test_ghcp_recommendations_declined_each_call(self, tmp_path: Path):
        scenario = VSCodeScenario(repo_path=tmp_path / "vscode")
        hot = tmp_path / "hot.json"
        hot.write_text(
            '{"eventSource": ['
            '{"path":"/usr/local/bin/node","authCount":10,"notifyCount":5}'
            ']}'
        )

        with patch.object(scenario, "_has_ghcp_cli", return_value=True):
            with patch("builtins.input", return_value="n"):
                with patch("demo_framework.scenarios.profiled_build.subprocess.run") as mock_run:
                    recs = scenario._ghcp_profile_recommendations(hot, ["node", "git"])

        assert recs == []
        mock_run.assert_not_called()

    def test_ghcp_recommendations_include_analysis_and_profiles(self, tmp_path: Path):
        scenario = VSCodeScenario(repo_path=tmp_path / "vscode")
        hot = tmp_path / "hot.json"
        hot.write_text(
            '{"eventSource": ['
            '{"path":"/usr/local/bin/node","authCount":10,"notifyCount":5}'
            ']}'
        )

        with patch.object(scenario, "_has_ghcp_cli", return_value=True):
            with patch("builtins.input", return_value="y"):
                with patch("demo_framework.scenarios.profiled_build.subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(
                        returncode=0,
                        stdout='{"type":"assistant.message","data":{"content":"ANALYSIS: Node process dominates telemetry.\\nRECOMMENDED_PROFILES: node"}}\n',
                    )
                    recs = scenario._ghcp_profile_recommendations(hot, ["node", "git"])

        assert recs == ["node"]
        args = mock_run.call_args.args[0]
        assert args[0] == "copilot"
        assert "-p" in args
        assert "--no-ask-user" in args
        assert "json" in args

    def test_select_profiles_choice_union(self, tmp_path: Path):
        scenario = VSCodeScenario(repo_path=tmp_path / "vscode")
        hot = tmp_path / "hot.json"
        hot.write_text('{"eventSource": [{"path":"/usr/local/bin/node","authCount":10,"notifyCount":5}]}')

        with patch.object(scenario, "_get_available_profiles", return_value=["node", "git", "vscode"]):
            with patch.object(scenario, "_ghcp_profile_recommendations", return_value=["node"]):
                with patch.object(scenario, "_python_profile_recommendations", return_value=["vscode"]):
                    with patch("builtins.input", return_value="3"):
                        scenario._select_profiles_for_phase4(hot)

        assert scenario.recommended_profiles == ["node", "vscode"]
        assert scenario.recommendation_source == "union"

    def test_select_profiles_choice_intersection(self, tmp_path: Path):
        scenario = VSCodeScenario(repo_path=tmp_path / "vscode")
        hot = tmp_path / "hot.json"
        hot.write_text('{"eventSource": [{"path":"/usr/local/bin/node","authCount":10,"notifyCount":5}]}')

        with patch.object(scenario, "_get_available_profiles", return_value=["node", "git", "vscode"]):
            with patch.object(scenario, "_ghcp_profile_recommendations", return_value=["node", "vscode"]):
                with patch.object(scenario, "_python_profile_recommendations", return_value=["vscode"]):
                    with patch("builtins.input", return_value="2"):
                        scenario._select_profiles_for_phase4(hot)

        assert scenario.recommended_profiles == ["vscode"]
        assert scenario.recommendation_source == "python+intersection"
