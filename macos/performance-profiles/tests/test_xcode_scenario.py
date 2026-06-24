from pathlib import Path

from demo_framework.scenarios.profiled_build import ProfiledBuildScenario
from demo_framework.scenarios.xcode import XcodeScenario


class TestXcodeScenarioConfig:
    def test_xcode_scenario_uses_profiled_build_base(self, tmp_path: Path):
        scenario = XcodeScenario(repo_path=tmp_path / "fluentui-apple")
        assert isinstance(scenario, ProfiledBuildScenario)

    def test_xcode_scenario_uses_data_driven_clone_phase_paths(self, tmp_path: Path):
        scenario = XcodeScenario(repo_path=tmp_path / "fluentui-apple")
        assert str(scenario.baseline_repo_path).endswith("fluentui-apple-baseline")
        assert str(scenario.optimized_repo_path).endswith("fluentui-apple-optimized")

    def test_xcode_scenario_wires_expected_common_options(self, tmp_path: Path):
        scenario = XcodeScenario(repo_path=tmp_path / "fluentui-apple")
        assert scenario.clone_in_timed_phases is True
        assert scenario.install_command == []
        assert scenario.tool_checks == [["git", "--version"], ["swift", "--version"]]
