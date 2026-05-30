from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from demo_framework.scenarios.vscode import VSCodeScenario
from demo_framework.scenarios.xcode import XcodeScenario


@pytest.mark.parametrize(
    "scenario_factory,expected_build_cmd,expected_profile",
    [
        (lambda p: VSCodeScenario(repo_path=p / "vscode"), ["npm", "run", "compile"], "node"),
        (lambda p: XcodeScenario(repo_path=p / "fluentui-apple"), ["swift", "build", "-c", "release"], "git"),
    ],
)
def test_scenario_uses_six_phase_template(tmp_path: Path, scenario_factory, expected_build_cmd, expected_profile):
    scenario = scenario_factory(tmp_path)
    phase_names = [name for name, _ in scenario.orchestrator.phases]
    assert phase_names == [
        "Setup and Preflight",
        "Baseline Build (No Profiles)",
        "Analyze Baseline Telemetry",
        "Apply Performance Profiles",
        "Optimized Build (With Profiles)",
        "Analyze Impact",
    ]


@pytest.mark.parametrize(
    "scenario_factory,expected_build_cmd,expected_profile",
    [
        (lambda p: VSCodeScenario(repo_path=p / "vscode"), ["npm", "run", "compile"], "node"),
        (lambda p: XcodeScenario(repo_path=p / "fluentui-apple"), ["swift", "build", "-c", "release"], "git"),
    ],
)
def test_apply_profiles_uses_apply_command(tmp_path: Path, scenario_factory, expected_build_cmd, expected_profile):
    scenario = scenario_factory(tmp_path)

    with patch.object(scenario, "_get_profile_state", return_value=(False, set())):
        with patch("demo_framework.scenarios.profiled_build.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            ok = scenario.apply_profiles()

    assert ok is True
    calls = [c.args[0] for c in mock_run.call_args_list]
    assert ["sudo", "mdatp", "performance-profiles", "apply", "--name", expected_profile] in calls


@pytest.mark.parametrize(
    "scenario_factory,expected_build_cmd",
    [
        (lambda p: VSCodeScenario(repo_path=p / "vscode"), ["npm", "run", "compile"]),
        (lambda p: XcodeScenario(repo_path=p / "fluentui-apple"), ["swift", "build", "-c", "release"]),
    ],
)
def test_build_baseline_runs_build_command_when_clean(tmp_path: Path, scenario_factory, expected_build_cmd):
    scenario = scenario_factory(tmp_path)
    scenario.config.repo_path.mkdir(parents=True, exist_ok=True)

    with patch.object(scenario, "_fresh_clone", return_value=True):
        with patch.object(scenario, "_get_profile_state", return_value=(False, set())):
            with patch("demo_framework.scenarios.profiled_build.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                ok = scenario.build_baseline()

    assert ok is True
    calls = [c.args[0] for c in mock_run.call_args_list]
    assert expected_build_cmd in calls


@pytest.mark.parametrize(
    "scenario_factory,expected_build_cmd",
    [
        (lambda p: VSCodeScenario(repo_path=p / "vscode"), ["npm", "run", "compile"]),
        (lambda p: XcodeScenario(repo_path=p / "fluentui-apple"), ["swift", "build", "-c", "release"]),
    ],
)
def test_build_baseline_fails_when_profiles_still_applied(tmp_path: Path, scenario_factory, expected_build_cmd):
    scenario = scenario_factory(tmp_path)
    scenario.config.repo_path.mkdir(parents=True, exist_ok=True)

    with patch.object(scenario, "_get_profile_state", return_value=(False, {scenario.config.profiles[0]})):
        with patch("demo_framework.scenarios.profiled_build.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            ok = scenario.build_baseline()

    assert ok is False
    calls = [c.args[0] for c in mock_run.call_args_list]
    assert expected_build_cmd not in calls


def test_vscode_baseline_fails_when_foreign_profile_remains_applied(tmp_path: Path):
    scenario = VSCodeScenario(repo_path=tmp_path / "vscode")
    scenario.config.repo_path.mkdir(parents=True, exist_ok=True)

    with patch.object(scenario, "_get_available_profiles", return_value=["node", "git", "vscode", "vscode-tree", "xcode"]):
        with patch.object(scenario, "_get_profile_state", return_value=(False, {"xcode"})):
            with patch("demo_framework.scenarios.profiled_build.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                ok = scenario.build_baseline()

    assert ok is False
    calls = [c.args[0] for c in mock_run.call_args_list]
    assert ["npm", "run", "compile"] not in calls


@pytest.mark.parametrize(
    "scenario_factory,expected_build_cmd",
    [
        (lambda p: VSCodeScenario(repo_path=p / "vscode"), ["npm", "run", "compile"]),
        (lambda p: XcodeScenario(repo_path=p / "fluentui-apple"), ["swift", "build", "-c", "release"]),
    ],
)
def test_build_optimized_runs_build_command(tmp_path: Path, scenario_factory, expected_build_cmd):
    scenario = scenario_factory(tmp_path)
    scenario.config.repo_path.mkdir(parents=True, exist_ok=True)

    with patch.object(scenario, "_fresh_clone", return_value=True):
        with patch("demo_framework.scenarios.profiled_build.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            ok = scenario.build_optimized()

    assert ok is True
    calls = [c.args[0] for c in mock_run.call_args_list]
    assert expected_build_cmd in calls


@pytest.mark.parametrize(
    "scenario_factory",
    [
        lambda p: VSCodeScenario(repo_path=p / "vscode"),
        lambda p: XcodeScenario(repo_path=p / "fluentui-apple"),
    ],
)
def test_analyze_baseline_telemetry_returns_true(tmp_path: Path, scenario_factory):
    scenario = scenario_factory(tmp_path)
    with patch.object(scenario, "_select_profiles_for_phase4"):
        assert scenario.analyze_baseline_telemetry() is True


@pytest.mark.parametrize(
    "scenario_factory,available_profiles,ghcp_recs,python_recs,expected_profiles",
    [
        (
            lambda p: VSCodeScenario(repo_path=p / "vscode"),
            ["node", "git", "vscode"],
            ["node"],
            ["vscode"],
            ["node", "vscode"],
        ),
        (
            lambda p: XcodeScenario(repo_path=p / "fluentui-apple"),
            ["xcode", "git", "xcode-ide-tree"],
            ["git"],
            ["xcode"],
            ["xcode", "git"],
        ),
    ],
)
def test_select_profiles_choice_union_in_common_runner(
    tmp_path: Path,
    scenario_factory,
    available_profiles,
    ghcp_recs,
    python_recs,
    expected_profiles,
):
    scenario = scenario_factory(tmp_path)
    hot = tmp_path / "hot.json"
    hot.write_text('{"eventSource": [{"path":"/tmp/workload","authCount":10,"notifyCount":5}]}')

    with patch.object(scenario, "_get_available_profiles", return_value=available_profiles):
        with patch.object(scenario, "_ghcp_profile_recommendations", return_value=ghcp_recs):
            with patch.object(scenario, "_python_profile_recommendations", return_value=python_recs):
                with patch("builtins.input", return_value="3"):
                    scenario._select_profiles_for_phase4(hot)

    assert scenario.recommended_profiles == expected_profiles
    assert scenario.recommendation_source == "union"


@pytest.mark.parametrize(
    "scenario_factory,available_profiles,ghcp_recs,python_recs,expected_profiles",
    [
        (
            lambda p: VSCodeScenario(repo_path=p / "vscode"),
            ["node", "git", "vscode"],
            ["node", "vscode"],
            ["vscode"],
            ["vscode"],
        ),
        (
            lambda p: XcodeScenario(repo_path=p / "fluentui-apple"),
            ["xcode", "git", "xcode-ide-tree"],
            ["git", "xcode"],
            ["xcode"],
            ["xcode"],
        ),
    ],
)
def test_select_profiles_choice_intersection_in_common_runner(
    tmp_path: Path,
    scenario_factory,
    available_profiles,
    ghcp_recs,
    python_recs,
    expected_profiles,
):
    scenario = scenario_factory(tmp_path)
    hot = tmp_path / "hot.json"
    hot.write_text('{"eventSource": [{"path":"/tmp/workload","authCount":10,"notifyCount":5}]}')

    with patch.object(scenario, "_get_available_profiles", return_value=available_profiles):
        with patch.object(scenario, "_ghcp_profile_recommendations", return_value=ghcp_recs):
            with patch.object(scenario, "_python_profile_recommendations", return_value=python_recs):
                with patch("builtins.input", return_value="2"):
                    scenario._select_profiles_for_phase4(hot)

    assert scenario.recommended_profiles == expected_profiles
    assert scenario.recommendation_source == "python+intersection"


@pytest.mark.parametrize(
    "scenario_factory,available_profiles,ghcp_recs,python_recs,expected_profiles",
    [
        (
            lambda p: VSCodeScenario(repo_path=p / "vscode"),
            ["node", "git", "vscode", "vscode-tree"],
            ["node"],
            ["vscode"],
            ["node", "git", "vscode", "vscode-tree"],
        ),
        (
            lambda p: XcodeScenario(repo_path=p / "fluentui-apple"),
            ["xcode", "git", "xcode-ide-tree"],
            ["git"],
            ["xcode"],
            ["xcode", "git", "xcode-ide-tree"],
        ),
    ],
)
def test_select_profiles_choice_scenario_default_in_common_runner(
    tmp_path: Path,
    scenario_factory,
    available_profiles,
    ghcp_recs,
    python_recs,
    expected_profiles,
):
    scenario = scenario_factory(tmp_path)
    hot = tmp_path / "hot.json"
    hot.write_text('{"eventSource": [{"path":"/tmp/workload","authCount":10,"notifyCount":5}]}')

    with patch.object(scenario, "_get_available_profiles", return_value=available_profiles):
        with patch.object(scenario, "_ghcp_profile_recommendations", return_value=ghcp_recs):
            with patch.object(scenario, "_python_profile_recommendations", return_value=python_recs):
                with patch("builtins.input", return_value="4"):
                    scenario._select_profiles_for_phase4(hot)

    assert scenario.recommended_profiles == expected_profiles
    assert scenario.recommendation_source == "scenario-default"


@pytest.mark.parametrize(
    "scenario_factory,available_profiles,same_recs",
    [
        (
            lambda p: VSCodeScenario(repo_path=p / "vscode"),
            ["node", "vscode"],
            ["node", "vscode"],
        ),
        (
            lambda p: XcodeScenario(repo_path=p / "fluentui-apple"),
            ["xcode", "git"],
            ["xcode", "git"],
        ),
    ],
)
def test_select_profiles_consolidates_duplicate_sets_without_prompt(
    tmp_path: Path,
    scenario_factory,
    available_profiles,
    same_recs,
):
    scenario = scenario_factory(tmp_path)
    hot = tmp_path / "hot.json"
    hot.write_text('{"eventSource": [{"path":"/tmp/workload","authCount":10,"notifyCount":5}]}')

    with patch.object(scenario, "_get_available_profiles", return_value=available_profiles):
        with patch.object(scenario, "_ghcp_profile_recommendations", return_value=same_recs):
            with patch.object(scenario, "_python_profile_recommendations", return_value=same_recs):
                with patch("builtins.input") as mock_input:
                    scenario._select_profiles_for_phase4(hot)

    assert scenario.recommended_profiles == same_recs
    assert scenario.recommendation_source == "ghcp+python+intersection+union+scenario-default"
    mock_input.assert_not_called()
