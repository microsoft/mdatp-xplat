from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from demo_framework.scenarios.vscode import VSCodeScenario
from demo_framework.scenarios.xcode import XcodeScenario


# ──────────────────────────────────────────────────────────────────
# Phase structure
# ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "scenario_factory",
    [
        lambda p: VSCodeScenario(repo_path=p / "vscode"),
        lambda p: XcodeScenario(repo_path=p / "fluentui-apple"),
    ],
)
def test_scenario_uses_six_phase_template(tmp_path: Path, scenario_factory):
    scenario = scenario_factory(tmp_path)
    phase_names = [name for name, _ in scenario.orchestrator.phases]
    assert phase_names == [
        "Setup and Preflight",
        "Baseline Build",
        "AV Exclusions Build",
        "Compensating Scan",
        "Profiles Build",
        "Compare Results",
    ]


# ──────────────────────────────────────────────────────────────────
# Default exclusion configuration
# ──────────────────────────────────────────────────────────────────

def test_vscode_has_expected_default_exclusions(tmp_path: Path):
    scenario = VSCodeScenario(repo_path=tmp_path / "vscode")
    rel_paths = [e["rel"] for e in scenario.default_exclusions]
    assert "node_modules" in rel_paths
    assert "out" in rel_paths
    assert ".build" in rel_paths


def test_xcode_has_expected_default_exclusions(tmp_path: Path):
    scenario = XcodeScenario(repo_path=tmp_path / "fluentui-apple")
    rel_paths = [e["rel"] for e in scenario.default_exclusions]
    assert "DerivedData" in rel_paths
    assert ".build" in rel_paths


def test_vscode_eicar_subdir_is_out(tmp_path: Path):
    scenario = VSCodeScenario(repo_path=tmp_path / "vscode")
    assert scenario.eicar_subdir == "out"


def test_xcode_eicar_subdir_is_build(tmp_path: Path):
    scenario = XcodeScenario(repo_path=tmp_path / "fluentui-apple")
    assert scenario.eicar_subdir == ".build"


# ──────────────────────────────────────────────────────────────────
# EICAR helpers
# ──────────────────────────────────────────────────────────────────

def test_place_eicar_writes_file(tmp_path: Path):
    scenario = XcodeScenario(repo_path=tmp_path / "fluentui-apple")
    target = tmp_path / "test_dir"
    target.mkdir(parents=True, exist_ok=True)

    # Patch write_text to avoid MDE intercepting the actual EICAR string in tests.
    with patch.object(Path, "write_text") as mock_write:
        path, placed_at = scenario._place_eicar(target)

    assert path is not None
    assert path.name.startswith("eicar_") and path.name.endswith(".txt")
    assert placed_at > 0
    mock_write.assert_called_once()
    written_content = mock_write.call_args.args[0]
    assert "EICAR" in written_content


def test_place_eicar_creates_directory(tmp_path: Path):
    scenario = XcodeScenario(repo_path=tmp_path / "fluentui-apple")
    target = tmp_path / "nonexistent" / "subdir"

    with patch.object(Path, "write_text"):
        path, placed_at = scenario._place_eicar(target)

    assert path is not None
    assert placed_at > 0
    assert target.exists()


def test_place_eicar_returns_blocked_sentinel_on_eperm(tmp_path: Path):
    """When MDE blocks the write (EPERM), return _EICAR_BLOCKED sentinel."""
    import errno as _errno
    from demo_framework.scenarios.profiled_build import _EICAR_BLOCKED

    scenario = XcodeScenario(repo_path=tmp_path / "fluentui-apple")
    target = tmp_path / "blocked_dir"
    target.mkdir(parents=True, exist_ok=True)

    eperm = OSError(_errno.EPERM, "Operation not permitted")
    with patch.object(Path, "write_text", side_effect=eperm):
        path, placed_at = scenario._place_eicar(target)

    assert path is _EICAR_BLOCKED
    assert placed_at == 0


def test_place_eicar_returns_none_on_other_error(tmp_path: Path):
    """Non-EPERM errors return (None, 0)."""
    import errno as _errno

    scenario = XcodeScenario(repo_path=tmp_path / "fluentui-apple")
    target = tmp_path / "err_dir"
    target.mkdir(parents=True, exist_ok=True)

    eacces = OSError(_errno.EACCES, "Permission denied")
    with patch.object(Path, "write_text", side_effect=eacces):
        path, placed_at = scenario._place_eicar(target)

    assert path is None
    assert placed_at == 0


def test_remove_eicar_deletes_file(tmp_path: Path):
    scenario = XcodeScenario(repo_path=tmp_path / "fluentui-apple")
    eicar_file = tmp_path / "eicar_test.txt"
    eicar_file.write_text("test")

    scenario._remove_eicar(eicar_file)
    assert not eicar_file.exists()


def test_remove_eicar_is_noop_for_none(tmp_path: Path):
    scenario = XcodeScenario(repo_path=tmp_path / "fluentui-apple")
    # Should not raise
    scenario._remove_eicar(None)


def test_remove_eicar_tolerates_already_deleted_file(tmp_path: Path):
    scenario = XcodeScenario(repo_path=tmp_path / "fluentui-apple")
    missing = tmp_path / "already_gone.txt"
    # Should not raise even though file does not exist
    scenario._remove_eicar(missing)


def test_check_eicar_detected_returns_true_when_file_gone(tmp_path: Path):
    scenario = XcodeScenario(repo_path=tmp_path / "fluentui-apple")
    missing_path = tmp_path / "gone.txt"

    with patch("demo_framework.scenarios.profiled_build.time.sleep"):
        detected = scenario._check_eicar_detected(missing_path, max_wait=2)

    assert detected is True


def test_check_eicar_detected_returns_false_when_file_present_and_no_threat_list(tmp_path: Path):
    scenario = XcodeScenario(repo_path=tmp_path / "fluentui-apple")
    eicar_file = tmp_path / "eicar_test.txt"
    eicar_file.write_text("test")

    with patch("demo_framework.scenarios.profiled_build.time.sleep"), \
         patch("demo_framework.scenarios.profiled_build.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        detected = scenario._check_eicar_detected(eicar_file, max_wait=2)

    assert detected is False


def test_check_eicar_detected_returns_true_via_threat_list(tmp_path: Path):
    scenario = XcodeScenario(repo_path=tmp_path / "fluentui-apple")
    eicar_file = tmp_path / "eicar_test.txt"
    eicar_file.write_text("test")

    # Use the actual MDE structure: {"threats": {"scans": [{"threats": [{...}]}]}}
    placed_at = 1000.0  # 1000s epoch → 1_000_000ms
    threat_json = (
        '{"threats": {"scans": [{"threats": [{'
        '"threat": {"name": "Virus:DOS/EICAR_Test_File", "type": "virus"},'
        '"detection_time": 1000001'  # 1ms after placed_at
        '}]}]}}'
    )
    with patch("demo_framework.scenarios.profiled_build.time.sleep"), \
         patch("demo_framework.scenarios.profiled_build.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=threat_json)
        detected = scenario._check_eicar_detected(eicar_file, placed_at=placed_at, max_wait=2)

    assert detected is True


# ──────────────────────────────────────────────────────────────────
# _eicar_in_threat_list parsing
# ──────────────────────────────────────────────────────────────────

def _make_scenario(tmp_path: Path):
    return XcodeScenario(repo_path=tmp_path / "fluentui-apple")


def test_eicar_in_threat_list_detects_real_mde_structure(tmp_path: Path):
    """Actual MDE structure: {"threats": {"scans": [{"threats": [{...}]}]}}."""
    scenario = _make_scenario(tmp_path)
    placed_at = 1000.0  # → 1_000_000 ms
    data = {
        "threats": {
            "scans": [{
                "threats": [{
                    "threat": {"name": "Virus:DOS/EICAR_Test_File", "type": "virus"},
                    "detection_time": 1_000_001,  # 1ms after
                }]
            }]
        }
    }
    assert scenario._eicar_in_threat_list(data, placed_at) is True


def test_eicar_in_threat_list_ignores_old_detections(tmp_path: Path):
    """Detections before placement timestamp must not match."""
    scenario = _make_scenario(tmp_path)
    placed_at = 2000.0  # → 2_000_000 ms
    data = {
        "threats": {
            "scans": [{
                "threats": [{
                    "threat": {"name": "Virus:DOS/EICAR_Test_File"},
                    "detection_time": 1_000_000,  # before placed_at
                }]
            }]
        }
    }
    assert scenario._eicar_in_threat_list(data, placed_at) is False


def test_eicar_in_threat_list_ignores_non_eicar_threats(tmp_path: Path):
    """Non-EICAR threats at the right time must not match."""
    scenario = _make_scenario(tmp_path)
    placed_at = 1000.0
    data = {
        "threats": {
            "scans": [{
                "threats": [{
                    "threat": {"name": "Trojan:Win32/Something"},
                    "detection_time": 1_000_001,
                }]
            }]
        }
    }
    assert scenario._eicar_in_threat_list(data, placed_at) is False


def test_eicar_in_threat_list_handles_empty_scans(tmp_path: Path):
    scenario = _make_scenario(tmp_path)
    assert scenario._eicar_in_threat_list({"threats": {"scans": []}}, 0.0) is False


def test_eicar_in_threat_list_handles_non_dict_input(tmp_path: Path):
    scenario = _make_scenario(tmp_path)
    assert scenario._eicar_in_threat_list([], 0.0) is False
    assert scenario._eicar_in_threat_list(None, 0.0) is False
    assert scenario._eicar_in_threat_list("bad", 0.0) is False


def test_eicar_in_threat_list_handles_flat_list_structure(tmp_path: Path):
    """Fallback: if 'threats' is a flat list (old format), still works."""
    scenario = _make_scenario(tmp_path)
    placed_at = 1000.0
    data = {
        "threats": [
            {"threat": {"name": "Virus:DOS/EICAR_Test_File"}, "detection_time": 1_000_001}
        ]
    }
    assert scenario._eicar_in_threat_list(data, placed_at) is True


# ──────────────────────────────────────────────────────────────────
# AV exclusion management
# ──────────────────────────────────────────────────────────────────

def test_setup_fails_when_scenario_exclusions_already_active(tmp_path: Path):
    repo = tmp_path / "vscode"
    repo.mkdir()
    scenario = VSCodeScenario(repo_path=repo)

    # Simulate mdatp returning the 'out' exclusion path as already active
    out_path = str(repo / "out")
    exclusion_json = f'[{{"type": "folder", "value": "{out_path}"}}]'

    with patch.object(scenario, "_get_profile_state", return_value=(False, set())), \
         patch("demo_framework.scenarios.profiled_build.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=exclusion_json)
        ok = scenario.setup()

    assert ok is False


def test_setup_succeeds_when_unrelated_exclusions_are_active(tmp_path: Path):
    repo = tmp_path / "vscode"
    repo.mkdir()
    scenario = VSCodeScenario(repo_path=repo)

    # Exclusion for a path NOT in this scenario's default exclusions
    unrelated_json = '[{"type": "folder", "value": "/Users/other/project/node_modules"}]'

    with patch.object(scenario, "_get_profile_state", return_value=(False, set())), \
         patch("demo_framework.scenarios.profiled_build.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=unrelated_json)
        ok = scenario.setup()

    assert ok is True


def test_apply_default_exclusions_calls_mdatp_for_each_exclusion(tmp_path: Path):
    scenario = VSCodeScenario(repo_path=tmp_path / "vscode")

    with patch("demo_framework.scenarios.profiled_build.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        applied = scenario._apply_default_exclusions()

    assert len(applied) == len(scenario.default_exclusions)
    calls = [c.args[0] for c in mock_run.call_args_list]
    assert all("mdatp" in " ".join(cmd) for cmd in calls)
    assert all("exclusion" in " ".join(cmd) and "add" in " ".join(cmd) for cmd in calls)


def test_apply_default_exclusions_populates_applied_exclusions(tmp_path: Path):
    scenario = VSCodeScenario(repo_path=tmp_path / "vscode")

    with patch("demo_framework.scenarios.profiled_build.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        scenario._apply_default_exclusions()

    assert len(scenario.applied_exclusions) == len(scenario.default_exclusions)
    for entry in scenario.applied_exclusions:
        assert entry["type"] == "folder"
        assert str(tmp_path / "vscode") in entry["value"]


def test_remove_default_exclusions_calls_mdatp_remove(tmp_path: Path):
    scenario = VSCodeScenario(repo_path=tmp_path / "vscode")
    scenario.applied_exclusions = [
        {"type": "folder", "value": "/tmp/test/node_modules"},
        {"type": "folder", "value": "/tmp/test/out"},
    ]

    with patch("demo_framework.scenarios.profiled_build.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        scenario._remove_default_exclusions()

    assert scenario.applied_exclusions == []
    calls = [c.args[0] for c in mock_run.call_args_list]
    assert all("remove" in cmd for cmd in calls)


def test_remove_default_exclusions_is_noop_when_nothing_applied(tmp_path: Path):
    scenario = VSCodeScenario(repo_path=tmp_path / "vscode")
    scenario.applied_exclusions = []

    with patch("demo_framework.scenarios.profiled_build.subprocess.run") as mock_run:
        scenario._remove_default_exclusions()

    mock_run.assert_not_called()


# ──────────────────────────────────────────────────────────────────
# Profile management
# ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "scenario_factory,expected_profile",
    [
        (lambda p: VSCodeScenario(repo_path=p / "vscode"), "node"),
        (lambda p: XcodeScenario(repo_path=p / "fluentui-apple"), "git"),
    ],
)
def test_apply_profiles_uses_apply_command(tmp_path: Path, scenario_factory, expected_profile):
    scenario = scenario_factory(tmp_path)

    with patch.object(scenario, "_get_profile_state", return_value=(False, set())):
        with patch("demo_framework.scenarios.profiled_build.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            ok = scenario.apply_profiles()

    assert ok is True
    calls = [c.args[0] for c in mock_run.call_args_list]
    assert ["sudo", "mdatp", "performance-profiles", "apply", "--name", expected_profile] in calls


def test_reset_profiles_at_start_removes_preexisting_profiles(tmp_path: Path):
    scenario = XcodeScenario(repo_path=tmp_path / "fluentui-apple")

    with patch.object(scenario, "_get_available_profiles", return_value=["xcode", "xcode-ide-tree", "git"]), \
        patch.object(scenario, "_get_profile_state", side_effect=[(False, {"xcode"}), (False, set())]), \
        patch("demo_framework.scenarios.profiled_build.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        ok = scenario._reset_profiles_at_start()

    assert ok is True
    removed = [
        c.args[0][-1]
        for c in mock_run.call_args_list
        if c.args[0][:4] == ["sudo", "mdatp", "performance-profiles", "remove"]
    ]
    assert sorted(removed) == ["git", "xcode", "xcode-ide-tree"]


def test_reset_profiles_at_start_fails_when_profiles_remain(tmp_path: Path):
    scenario = XcodeScenario(repo_path=tmp_path / "fluentui-apple")

    with patch.object(scenario, "_get_available_profiles", return_value=["xcode"]), \
        patch.object(scenario, "_get_profile_state", side_effect=[(False, {"xcode"}), (False, {"xcode"})]), \
        patch("demo_framework.scenarios.profiled_build.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        ok = scenario._reset_profiles_at_start()

    assert ok is False


def test_reset_profiles_at_start_noop_for_admin_only(tmp_path: Path):
    scenario = XcodeScenario(repo_path=tmp_path / "fluentui-apple")

    with patch.object(scenario, "_get_profile_state", return_value=(True, set())), \
        patch("demo_framework.scenarios.profiled_build.subprocess.run") as mock_run:
        ok = scenario._reset_profiles_at_start()

    assert ok is True
    assert mock_run.call_count == 0


# ──────────────────────────────────────────────────────────────────
# Baseline build
# ──────────────────────────────────────────────────────────────────

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


# ──────────────────────────────────────────────────────────────────
# RTP scan counting
# ──────────────────────────────────────────────────────────────────

def test_rtp_scan_count_supports_counters_schema_and_delta(tmp_path: Path):
    scenario = XcodeScenario(repo_path=tmp_path / "fluentui-apple")

    before = tmp_path / "rtp_before.json"
    after = tmp_path / "rtp_after.json"
    before.write_text('{"counters": [{"totalFilesScanned": "100"}, {"totalFilesScanned": "30"}]}')
    after.write_text('{"counters": [{"totalFilesScanned": "145"}, {"totalFilesScanned": "55"}]}')

    assert scenario._rtp_total_files(before) == 130
    assert scenario._rtp_total_files(after) == 200
    assert scenario._count_rtp_scan_delta(before, after) == "70"
