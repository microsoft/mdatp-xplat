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


def test_final_report_includes_summary_table_and_ghcp_analysis(tmp_path: Path):
    scenario = XcodeScenario(repo_path=tmp_path / "fluentui-apple")
    results_dir = tmp_path / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    scenario.orchestrator.results_dir = results_dir
    scenario.baseline = {
        "time": 11.8,
        "cpu": 13.5,
        "scans": 0,
        "profiles_at_start": "(none)",
        "client_analyzer": results_dir / "client.zip",
    }
    scenario.optimized = {"time": 10.3, "cpu": 7.2, "scans": 0}
    scenario.recommended_profiles = ["git", "xcode", "xcode-ide-tree"]
    scenario.recommendation_source = "ghcp+union+scenario-default"
    scenario.recommended_exclusions = []
    scenario.applied_temp_exclusions = []
    scenario.exclusions_before = []
    scenario.exclusions_after_optimized = []
    scenario.exclusions_after_cleanup = []
    scenario.compensating_scan_status = "started"
    scenario.compensating_scan_target = "/Users/joshbregman/demo/fluentui-apple-optimized"
    scenario.compensating_scan_files_scanned = "221"
    scenario.compensating_scan_threats_found = "0"
    scenario.phase3_ghcp_analysis = (
        "Hotspots:\n"
        " • swift-frontend dominates with 6,058 events.\n"
        " • auth_readdir is a major directory-read signal."
    )

    (results_dir / "phase2_hot_events.json").write_text(
        '{"eventSource": ['
        '{"path":"/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swift-frontend","authCount":4935,"notifyCount":1123},'
        '{"path":"/usr/bin/git","authCount":500,"notifyCount":100}'
        ']}'
    )
    (results_dir / "phase5_hot_events.json").write_text(
        '{"eventSource": ['
        '{"path":"/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swift-frontend","authCount":1200,"notifyCount":200},'
        '{"path":"/usr/bin/git","authCount":250,"notifyCount":90}'
        ']}'
    )

    with patch.object(scenario, "_get_profile_state", return_value=(False, {"git", "xcode", "xcode-ide-tree"})):
        scenario._write_final_markdown_report(11.8, 10.3)

    report_path = results_dir / f"final_report_{scenario.config.name.lower().replace(' ', '_')}.md"
    report = report_path.read_text()
    assert "## 📋 Analysis" in report
    assert "### ℹ️ Summary" in report
    assert "| Metric | Before | After | Impact |" in report
    assert "### 🧠 Analysis" in report
    assert "AI caveat: GitHub Copilot recommendations use AI" in report
    assert "| 🧩 Profiles applied |" in report
    assert "| 🔹 AV exclusions |" in report
    assert "| ⚡ Hot events (total) |" in report
    assert "| Files scanned | 221 |" in report
    assert "| Threats found | 0 |" in report
    assert "swift-frontend dominates" in report


def test_ghcp_exclusion_parser_accepts_markdown_style_candidates(tmp_path: Path):
    scenario = XcodeScenario(repo_path=tmp_path / "fluentui-apple")
    output = (
        "ANALYSIS: Hotspots look dominated by build outputs.\n"
        "Exclusion candidates:\n"
        "- <repo>/.build/\n"
        "- ~/Library/Developer/Xcode/DerivedData/\n"
        "- process:/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swift-frontend\n"
        "RECOMMENDED_PROFILES: xcode, xcode-ide-tree\n"
    )

    parsed = scenario._parse_ghcp_exclusion_candidates(output)

    assert parsed == [
        {"type": "folder", "value": str(scenario.config.repo_path / ".build/")},
        {"type": "folder", "value": str(Path.home() / "Library/Developer/Xcode/DerivedData")},
        {
            "type": "process",
            "value": "/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swift-frontend",
        },
    ]


def test_ghcp_exclusion_parser_handles_inline_recommended_profiles(tmp_path: Path):
    scenario = XcodeScenario(repo_path=tmp_path / "fluentui-apple")
    output = (
        "EXCLUSION_CANDIDATES: ~/Library/Developer/Xcode/DerivedData, ~/.build, "
        "~/Library/Caches/org.swift.swiftpm, "
        "process:/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swift-frontend "
        "RECOMMENDED_PROFILES: xcode, xcode-ide-tree\n"
    )

    parsed = scenario._parse_ghcp_exclusion_candidates(output)

    assert parsed == [
        {"type": "folder", "value": str(Path.home() / "Library/Developer/Xcode/DerivedData")},
        {"type": "folder", "value": str(Path.home() / ".build")},
        {"type": "folder", "value": str(Path.home() / "Library/Caches/org.swift.swiftpm")},
        {
            "type": "process",
            "value": "/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swift-frontend",
        },
    ]


def test_build_optimized_skips_compensating_scan_when_no_temp_exclusions(tmp_path: Path):
    scenario = XcodeScenario(repo_path=tmp_path / "fluentui-apple")
    scenario.config.repo_path.mkdir(parents=True, exist_ok=True)

    with patch.object(scenario, "_fresh_clone", return_value=True), \
        patch.object(scenario, "_prepare_build_environment"), \
        patch.object(scenario, "_collect_rtp_stats"), \
        patch.object(scenario, "_start_cpu_monitor", return_value=(MagicMock(), MagicMock())), \
        patch.object(scenario, "_start_hot_event_collection", return_value=(None, False)), \
        patch.object(scenario, "_finalize_hot_event_collection"), \
        patch.object(scenario, "_run_build_command", return_value=True), \
        patch.object(scenario, "_calc_avg_cpu", return_value="7.2"), \
        patch.object(scenario, "_count_rtp_scan_delta", return_value="0"), \
        patch.object(scenario, "_run_compensating_scan") as mock_scan, \
        patch("demo_framework.scenarios.profiled_build.subprocess.run"):
        scenario.applied_temp_exclusions = []
        ok = scenario.build_optimized()

    assert ok is True
    assert scenario.compensating_scan_status == "skipped_no_temp_exclusions"
    mock_scan.assert_not_called()


def test_format_exclusion_snapshot_shows_all_entries(tmp_path: Path):
    scenario = VSCodeScenario(repo_path=tmp_path / "vscode")
    entries = [f"folder:/tmp/path-{i}" for i in range(1, 8)]

    rendered = scenario._format_exclusion_snapshot(entries)

    assert rendered == ", ".join(entries)
    assert "+" not in rendered


def test_rtp_scan_count_supports_counters_schema_and_delta(tmp_path: Path):
    scenario = XcodeScenario(repo_path=tmp_path / "fluentui-apple")

    before = tmp_path / "rtp_before.json"
    after = tmp_path / "rtp_after.json"
    before.write_text('{"counters": [{"totalFilesScanned": "100"}, {"totalFilesScanned": "30"}]}')
    after.write_text('{"counters": [{"totalFilesScanned": "145"}, {"totalFilesScanned": "55"}]}')

    assert scenario._count_rtp_scans(before) == "130"
    assert scenario._count_rtp_scans(after) == "200"
    assert scenario._count_rtp_scan_delta(before, after) == "70"


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
