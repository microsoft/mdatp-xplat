from pathlib import Path
from unittest.mock import patch

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

    def test_select_profiles_choice_union(self, tmp_path: Path):
        scenario = XcodeScenario(repo_path=tmp_path / "fluentui-apple")
        hot = tmp_path / "hot.json"
        hot.write_text('{"eventSource": [{"path":"/Applications/Xcode.app","authCount":10,"notifyCount":5}]}')

        with patch.object(scenario, "_get_available_profiles", return_value=["xcode", "git", "xcode-ide-tree"]):
            with patch.object(scenario, "_ghcp_profile_recommendations", return_value=["git"]):
                with patch.object(scenario, "_python_profile_recommendations", return_value=["xcode"]):
                    with patch("builtins.input", return_value="3"):
                        scenario._select_profiles_for_phase4(hot)

        assert scenario.recommended_profiles == ["xcode", "git"]
        assert scenario.recommendation_source == "union"

    def test_select_profiles_choice_intersection(self, tmp_path: Path):
        scenario = XcodeScenario(repo_path=tmp_path / "fluentui-apple")
        hot = tmp_path / "hot.json"
        hot.write_text('{"eventSource": [{"path":"/Applications/Xcode.app","authCount":10,"notifyCount":5}]}')

        with patch.object(scenario, "_get_available_profiles", return_value=["xcode", "git", "xcode-ide-tree"]):
            with patch.object(scenario, "_ghcp_profile_recommendations", return_value=["git", "xcode"]):
                with patch.object(scenario, "_python_profile_recommendations", return_value=["xcode"]):
                    with patch("builtins.input", return_value="2"):
                        scenario._select_profiles_for_phase4(hot)

        assert scenario.recommended_profiles == ["xcode"]
        assert scenario.recommendation_source == "python+intersection"
