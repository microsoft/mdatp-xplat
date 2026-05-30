from pathlib import Path
from unittest.mock import MagicMock, patch

from demo_framework.scenarios.xcode import XcodeScenario


class TestXcodeScenario:
    def test_setup_validates_tools_only(self, tmp_path: Path):
        scenario = XcodeScenario(repo_path=tmp_path / "fluentui-apple")

        with patch("demo_framework.scenarios.xcode.subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),  # git --version
                MagicMock(returncode=0),  # swift --version
            ]
            ok = scenario.setup()

        assert ok is True
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert ["git", "--version"] in calls
        assert ["swift", "--version"] in calls

    def test_apply_profiles_uses_apply_command(self, tmp_path: Path):
        scenario = XcodeScenario(repo_path=tmp_path / "fluentui-apple")

        with patch("demo_framework.scenarios.xcode.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            ok = scenario.apply_profiles()

        assert ok is True
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert ["sudo", "mdatp", "performance-profiles", "apply", "--name", "git"] in calls

    def test_build_baseline_clones_and_builds(self, tmp_path: Path):
        scenario = XcodeScenario(repo_path=tmp_path / "fluentui-apple")

        with patch.object(scenario, "_fresh_clone", return_value=True) as mock_clone:
            with patch("demo_framework.scenarios.xcode.subprocess.run") as mock_run:
                mock_run.side_effect = [
                    MagicMock(returncode=0),  # remove xcode
                    MagicMock(returncode=0),  # remove xcode-ide-tree
                    MagicMock(returncode=0),  # remove git
                    MagicMock(returncode=0),  # swift build
                ]
                ok = scenario.build_baseline()

        assert ok is True
        mock_clone.assert_called_once_with(scenario.baseline_repo_path)
        assert mock_run.call_args_list[-1].args[0] == ["swift", "build", "-c", "release"]

    def test_build_optimized_clones_and_builds(self, tmp_path: Path):
        scenario = XcodeScenario(repo_path=tmp_path / "fluentui-apple")

        with patch.object(scenario, "_fresh_clone", return_value=True) as mock_clone:
            with patch("demo_framework.scenarios.xcode.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                ok = scenario.build_optimized()

        assert ok is True
        mock_clone.assert_called_once_with(scenario.optimized_repo_path)
        mock_run.assert_called_once()
