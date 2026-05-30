from pathlib import Path
from unittest.mock import MagicMock, patch

from demo_framework.scenarios.profiled_build import ProfiledBuildScenario
from demo_framework.scenarios.xcode_simulator import XcodeSimulatorScenario


class TestXcodeSimulatorScenarioConfig:
    def test_xcode_simulator_scenario_uses_profiled_build_base(self, tmp_path: Path):
        scenario = XcodeSimulatorScenario(repo_path=tmp_path / "hello-defender-ios")
        assert isinstance(scenario, ProfiledBuildScenario)

    def test_xcode_simulator_scenario_uses_data_driven_clone_phase_paths(self, tmp_path: Path):
        scenario = XcodeSimulatorScenario(repo_path=tmp_path / "hello-defender-ios")
        assert str(scenario.baseline_repo_path).endswith("hello-defender-ios")
        assert str(scenario.optimized_repo_path).endswith("hello-defender-ios")

    def test_xcode_simulator_scenario_wires_expected_common_options(self, tmp_path: Path):
        scenario = XcodeSimulatorScenario(repo_path=tmp_path / "hello-defender-ios")
        assert scenario.clone_in_timed_phases is False
        assert scenario.install_command == []
        assert scenario.tool_checks == [["xcodebuild", "-version"], ["xcrun", "--version"]]
        assert scenario.config.profiles == ["xcode", "ios-simulator-tree", "iphone-simulator-tree", "git"]
        assert scenario.repo_validation_file is None

    def test_xcode_simulator_runs_tests_by_default(self, tmp_path: Path):
        scenario = XcodeSimulatorScenario(repo_path=tmp_path / "hello-defender-ios")
        derived = tmp_path / ".mde-derived" / "Build" / "Products" / "Debug-iphonesimulator" / "HelloDefender.app"
        derived.mkdir(parents=True)

        with patch.object(
            scenario,
            "_detect_project_and_scheme",
            return_value=(Path("HelloDefender.xcodeproj"), "HelloDefender"),
        ):
            with patch.object(scenario, "_first_bootable_simulator_udid", return_value="SIM-UDID"):
                with patch.object(scenario, "_bundle_identifier", return_value="com.microsoft.mdatp.xplat.hellodefender"):
                    with patch("demo_framework.scenarios.xcode_simulator.subprocess.run") as mock_run:
                        mock_run.return_value = MagicMock(returncode=0, stdout="")
                        ok = scenario._run_build_command(tmp_path, "baseline")

        assert ok is True
        xcodebuild_calls = [
            call.args[0] for call in mock_run.call_args_list if call.args and call.args[0] and call.args[0][0] == "xcodebuild"
        ]
        assert any(call[-1] == "clean" for call in xcodebuild_calls)
        assert any(call[-1] == "test" for call in xcodebuild_calls)
        assert any(call[-1] == "build" for call in xcodebuild_calls)

    def test_xcode_simulator_can_skip_tests_when_disabled(self, tmp_path: Path):
        scenario = XcodeSimulatorScenario(repo_path=tmp_path / "hello-defender-ios", run_tests_by_default=False)
        derived = tmp_path / ".mde-derived" / "Build" / "Products" / "Debug-iphonesimulator" / "HelloDefender.app"
        derived.mkdir(parents=True)

        with patch.object(
            scenario,
            "_detect_project_and_scheme",
            return_value=(Path("HelloDefender.xcodeproj"), "HelloDefender"),
        ):
            with patch.object(scenario, "_first_bootable_simulator_udid", return_value="SIM-UDID"):
                with patch.object(scenario, "_bundle_identifier", return_value="com.microsoft.mdatp.xplat.hellodefender"):
                    with patch("demo_framework.scenarios.xcode_simulator.subprocess.run") as mock_run:
                        mock_run.return_value = MagicMock(returncode=0, stdout="")
                        ok = scenario._run_build_command(tmp_path, "optimized")

        assert ok is True
        xcodebuild_calls = [
            call.args[0] for call in mock_run.call_args_list if call.args and call.args[0] and call.args[0][0] == "xcodebuild"
        ]
        assert any(call[-1] == "clean" for call in xcodebuild_calls)
        assert all(call[-1] != "test" for call in xcodebuild_calls)
        assert any(call[-1] == "build" for call in xcodebuild_calls)
