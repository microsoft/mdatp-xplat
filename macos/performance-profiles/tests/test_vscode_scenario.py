"""Tests for VS Code scenario build mode behavior."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from demo_framework.scenarios.profiled_build import ProfiledBuildScenario
from demo_framework.scenarios.vscode import VSCodeScenario


class TestVSCodeScenarioBuildModes:
    """Validate compile-only vs install+compile behavior."""

    def test_vscode_scenario_uses_profiled_build_base(self, tmp_path: Path):
        scenario = VSCodeScenario(repo_path=tmp_path / "vscode")
        assert isinstance(scenario, ProfiledBuildScenario)

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
            with patch.object(
                scenario,
                "_start_cpu_monitor",
                return_value=(MagicMock(set=lambda: None), MagicMock(join=lambda timeout=None: None)),
            ):
                with patch.object(scenario, "_collect_rtp_stats", return_value=None):
                    with patch.object(scenario, "_count_rtp_scans", return_value="N/A"):
                        with patch("demo_framework.scenarios.vscode.subprocess.run") as mock_run:
                            mock_run.side_effect = [
                                MagicMock(returncode=0),  # enable rtp stats
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
            with patch.object(
                scenario,
                "_start_cpu_monitor",
                return_value=(MagicMock(set=lambda: None), MagicMock(join=lambda timeout=None: None)),
            ):
                with patch.object(scenario, "_collect_rtp_stats", return_value=None):
                    with patch.object(scenario, "_count_rtp_scans", return_value="N/A"):
                        with patch("demo_framework.scenarios.vscode.subprocess.run") as mock_run:
                            mock_run.side_effect = [
                                MagicMock(returncode=0),  # enable rtp stats
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

    def test_baseline_fails_when_profiles_still_applied_after_remove(self, tmp_path: Path):
        repo = tmp_path / "vscode"
        repo.mkdir()

        scenario = VSCodeScenario(repo_path=repo, include_install_in_build=False)

        with patch.object(
            scenario,
            "_get_profile_state",
            return_value=(False, {"node"}),
        ):
            with patch.object(
                scenario,
                "_start_cpu_monitor",
                return_value=(MagicMock(set=lambda: None), MagicMock(join=lambda timeout=None: None)),
            ):
                with patch.object(scenario, "_start_hot_event_collection", return_value=(None, set())):
                    with patch("demo_framework.scenarios.vscode.subprocess.run") as mock_run:
                        mock_run.side_effect = [
                            MagicMock(returncode=0),
                            MagicMock(returncode=0),
                            MagicMock(returncode=0),
                            MagicMock(returncode=0),
                            MagicMock(returncode=0),
                        ]
                        ok = scenario.build_baseline()

        assert ok is False
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert ["npm", "run", "compile"] not in calls

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

    def test_apply_profiles_uses_recommended_profile_subset(self, tmp_path: Path):
        repo = tmp_path / "vscode"
        repo.mkdir()

        scenario = VSCodeScenario(repo_path=repo)
        scenario.recommended_profiles = ["node", "git"]
        scenario.recommendation_source = "python"

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
        assert ["sudo", "mdatp", "performance-profiles", "apply", "--name", "git"] in calls
        assert ["sudo", "mdatp", "performance-profiles", "apply", "--name", "vscode"] not in calls

    def test_select_profiles_for_phase4_uses_default_when_no_recommendations(self, tmp_path: Path):
        repo = tmp_path / "vscode"
        repo.mkdir()
        scenario = VSCodeScenario(repo_path=repo)

        hot = tmp_path / "hot.json"
        hot.write_text('{"eventSource": []}')

        with patch.object(scenario, "_has_ghcp_cli", return_value=False):
            with patch.object(scenario, "_get_available_profiles", return_value=scenario.config.profiles):
                scenario._select_profiles_for_phase4(hot)

        assert scenario.recommended_profiles == scenario.config.profiles
        assert scenario.recommendation_source == "default"

    def test_select_profiles_for_phase4_prefers_ghcp_by_default(self, tmp_path: Path):
        repo = tmp_path / "vscode"
        repo.mkdir()
        scenario = VSCodeScenario(repo_path=repo)

        hot = tmp_path / "hot.json"
        hot.write_text(
            '{"eventSource": ['
            '{"path":"/usr/local/bin/node","authCount":10,"notifyCount":5}'
            ']}'
        )

        with patch.object(scenario, "_ghcp_profile_recommendations", return_value=["git", "node"]):
            scenario._select_profiles_for_phase4(hot)

        assert scenario.recommended_profiles == ["git", "node"]
        assert scenario.recommendation_source == "ghcp"

    def test_select_profiles_for_phase4_falls_back_to_python_when_ghcp_empty(self, tmp_path: Path):
        repo = tmp_path / "vscode"
        repo.mkdir()
        scenario = VSCodeScenario(repo_path=repo)

        hot = tmp_path / "hot.json"
        hot.write_text(
            '{"eventSource": ['
            '{"path":"/usr/local/bin/node","authCount":10,"notifyCount":5}'
            ']}'
        )

        with patch.object(scenario, "_ghcp_profile_recommendations", return_value=[]):
            with patch.object(scenario, "_python_profile_recommendations", return_value=["node"]):
                scenario._select_profiles_for_phase4(hot)

        assert scenario.recommended_profiles == ["node"]
        assert scenario.recommendation_source == "python"

    def test_parse_ghcp_recommended_profiles_machine_readable_line(self, tmp_path: Path):
        repo = tmp_path / "vscode"
        repo.mkdir()
        scenario = VSCodeScenario(repo_path=repo)

        out = "Reasoning...\nRECOMMENDED_PROFILES: git, node\n"
        parsed = scenario._parse_ghcp_recommended_profiles(out, ["node", "git", "vscode"])

        assert parsed == ["git", "node"]

    def test_ghcp_profile_recommendations_reads_machine_format(self, tmp_path: Path):
        repo = tmp_path / "vscode"
        repo.mkdir()
        scenario = VSCodeScenario(repo_path=repo)

        hot = tmp_path / "hot.json"
        hot.write_text(
            '{"eventSource": ['
            '{"path":"/usr/local/bin/node","authCount":10,"notifyCount":5}'
            ']}'
        )

        with patch.object(scenario, "_has_ghcp_cli", return_value=True):
            with patch("demo_framework.scenarios.vscode.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout="RECOMMENDED_PROFILES: vscode, node\n",
                )
                recs = scenario._ghcp_profile_recommendations(hot, ["node", "vscode", "git"])

        assert recs == ["vscode", "node"]

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

        with patch.object(scenario, "_collect_hot_event_sources", return_value=False):
            with patch.object(
                scenario,
                "_run_client_analyzer",
                return_value="/tmp/MDESupportTool_test.zip",
            ):
                with patch("demo_framework.scenarios.vscode.subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0)
                    ok = scenario._collect_diagnostics()

        assert ok is True
        assert scenario.state_file.exists()
        state = scenario.state_file.read_text()
        assert "baseline_complete" in state
        assert "baseline_client_analyzer" in state

    def test_load_hot_event_entries_normalizes_counts(self, tmp_path: Path):
        repo = tmp_path / "vscode"
        repo.mkdir()
        scenario = VSCodeScenario(repo_path=repo)

        hot = tmp_path / "hot.json"
        hot.write_text(
            '{"eventSource": ['
            '{"path":"/bin/node","authCount":"10","notifyCount":"5"},'
            '{"path":"/bin/git","authCount":2,"notifyCount":3}'
            ']}'
        )

        entries = scenario._load_hot_event_entries(hot)
        assert len(entries) == 2
        assert entries[0]["total"] >= entries[1]["total"]
        assert entries[0]["auth"] + entries[0]["notify"] == entries[0]["total"]

    def test_has_ghcp_cli_true_when_gh_copilot_help_works(self, tmp_path: Path):
        repo = tmp_path / "vscode"
        repo.mkdir()
        scenario = VSCodeScenario(repo_path=repo)

        with patch("demo_framework.scenarios.vscode.shutil.which", return_value="/usr/bin/gh"):
            with patch("demo_framework.scenarios.vscode.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                assert scenario._has_ghcp_cli() is True

    def test_get_available_profiles_parses_cli_output(self, tmp_path: Path):
        repo = tmp_path / "vscode"
        repo.mkdir()
        scenario = VSCodeScenario(repo_path=repo)

        stdout = """Available profiles:
node
git
vscode
vscode-tree
"""

        with patch("demo_framework.scenarios.vscode.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=stdout)
            profiles = scenario._get_available_profiles()

        assert profiles == ["node", "git", "vscode", "vscode-tree"]

    def test_analyze_results_does_not_prompt_in_prompt_mode(self, tmp_path: Path):
        repo = tmp_path / "vscode"
        repo.mkdir()
        scenario = VSCodeScenario(repo_path=repo, hot_events_analysis_mode="prompt")

        scenario.baseline = {"time": 120.0, "cpu": "70.0", "scans": "100", "client_analyzer": None}
        scenario.optimized = {"time": 90.0, "cpu": "40.0", "scans": "50"}
        scenario.recommended_profiles = ["node", "git"]
        scenario.recommendation_source = "ghcp"

        before = scenario.orchestrator.results_dir / "phase2_hot_events.json"
        after = scenario.orchestrator.results_dir / "phase5_hot_events.json"
        before.write_text('{"eventSource":[{"path":"/bin/node","authCount":10,"notifyCount":5}]}')
        after.write_text('{"eventSource":[{"path":"/bin/node","authCount":7,"notifyCount":3}]}')

        with patch.object(scenario, "_get_profile_state", return_value=(False, {"node", "git"})):
            with patch("builtins.input", side_effect=AssertionError("input() should not be called")):
                ok = scenario.analyze_results()

        assert ok is True
