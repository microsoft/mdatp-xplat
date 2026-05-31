from pathlib import Path
from unittest.mock import MagicMock, patch

from demo_framework.scenarios.profiled_build import ProfiledBuildScenario
from demo_framework.scenarios.android_studio import AndroidStudioScenario


class TestAndroidStudioScenarioConfig:
    def test_android_studio_scenario_uses_profiled_build_base(self, tmp_path: Path):
        scenario = AndroidStudioScenario(repo_path=tmp_path / "hello-defender-android")
        assert isinstance(scenario, ProfiledBuildScenario)

    def test_android_studio_scenario_uses_data_driven_clone_phase_paths(self, tmp_path: Path):
        scenario = AndroidStudioScenario(repo_path=tmp_path / "hello-defender-android")
        assert str(scenario.baseline_repo_path).endswith("hello-defender-android")
        assert str(scenario.optimized_repo_path).endswith("hello-defender-android")

    def test_android_studio_scenario_wires_expected_common_options(self, tmp_path: Path):
        scenario = AndroidStudioScenario(repo_path=tmp_path / "hello-defender-android")
        assert scenario.clone_in_timed_phases is False
        assert scenario.install_command == []
        assert scenario.tool_checks == []
        assert scenario.config.profiles == ["android-studio", "android-studio-tree", "java", "git"]
        assert scenario.repo_validation_file is None

    def test_setup_detects_android_sdk_tools_outside_path(self, tmp_path: Path):
        repo = tmp_path / "hello-defender-android"
        manifest = repo / "app" / "src" / "main" / "AndroidManifest.xml"
        manifest.parent.mkdir(parents=True)
        manifest.write_text('<manifest package="com.microsoft.mdatp.xplat.hellodefender"/>')
        gradlew = repo / "gradlew"
        gradlew.write_text("#!/bin/sh\n")

        scenario = AndroidStudioScenario(repo_path=repo)

        sdk_root = tmp_path / "Library" / "Android" / "sdk"
        adb_path = sdk_root / "platform-tools" / "adb"
        emulator_path = sdk_root / "emulator" / "emulator"
        adb_path.parent.mkdir(parents=True)
        emulator_path.parent.mkdir(parents=True)
        adb_path.write_text("")
        emulator_path.write_text("")

        with patch.object(scenario, "_android_studio_installed", return_value=True):
            with patch("demo_framework.scenarios.android_studio.Path.home", return_value=tmp_path):
                with patch.object(scenario, "_resolve_command", side_effect=[None, None, None]):
                    with patch.object(scenario, "_first_booted_emulator_serial", return_value="emulator-5554"):
                        with patch.object(scenario, "_first_avd_name", return_value=None):
                            with patch.object(ProfiledBuildScenario, "setup", return_value=True):
                                ok = scenario.setup()

        assert ok is True
        assert scenario.adb_command == str(adb_path)
        assert scenario.emulator_command == str(emulator_path)

    def test_setup_fails_without_connected_device_or_avd(self, tmp_path: Path):
        repo = tmp_path / "hello-defender-android"
        manifest = repo / "app" / "src" / "main" / "AndroidManifest.xml"
        manifest.parent.mkdir(parents=True)
        manifest.write_text('<manifest package="com.microsoft.mdatp.xplat.hellodefender"/>')
        gradlew = repo / "gradlew"
        gradlew.write_text("#!/bin/sh\n")

        scenario = AndroidStudioScenario(repo_path=repo)

        with patch.object(scenario, "_android_studio_installed", return_value=True):
            with patch.object(scenario, "_resolve_android_sdk_tool", side_effect=[("/sdk/platform-tools/adb", []), ("/sdk/emulator/emulator", [])]):
                with patch.object(scenario, "_resolve_command", return_value=None):
                    with patch.object(scenario, "_first_booted_emulator_serial", return_value=None):
                        with patch.object(scenario, "_first_avd_name", return_value=None):
                            ok = scenario.setup()

        assert ok is False

    def test_android_studio_runs_tests_by_default(self, tmp_path: Path):
        scenario = AndroidStudioScenario(repo_path=tmp_path / "hello-defender-android")
        scenario.android_sdk_root = tmp_path / "android-sdk"

        manifest = tmp_path / "app" / "src" / "main" / "AndroidManifest.xml"
        manifest.parent.mkdir(parents=True)
        manifest.write_text('<manifest package="com.microsoft.mdatp.xplat.hellodefender"/>')

        apk = tmp_path / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
        apk.parent.mkdir(parents=True)
        apk.write_text("apk")

        with patch.object(scenario, "_ensure_emulator_serial", return_value="emulator-5554") as mock_ensure_emulator:
            with patch("demo_framework.scenarios.android_studio.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="com.microsoft.mdatp.xplat.hellodefender/.MainActivity")
                ok = scenario._run_build_command(tmp_path, "baseline")

        assert ok is True
        mock_ensure_emulator.assert_called_once()
        gradle_calls = [call.args[0] for call in mock_run.call_args_list if call.args and call.args[0] and call.args[0][0] in ("./gradlew", "gradle")]
        gradle_envs = [call.kwargs.get("env") for call in mock_run.call_args_list if call.args and call.args[0] and call.args[0][0] in ("./gradlew", "gradle")]
        assert any(call[-1] == "clean" for call in gradle_calls)
        assert any(call[-1] == "connectedDebugAndroidTest" for call in gradle_calls)
        assert any(call[-1] == "assembleDebug" for call in gradle_calls)
        assert all(env and env.get("ANDROID_SDK_ROOT") == str(scenario.android_sdk_root) for env in gradle_envs)
        assert all(env and env.get("ANDROID_HOME") == str(scenario.android_sdk_root) for env in gradle_envs)

    def test_android_studio_can_skip_tests_when_disabled(self, tmp_path: Path):
        scenario = AndroidStudioScenario(repo_path=tmp_path / "hello-defender-android", run_tests_by_default=False)
        scenario.android_sdk_root = tmp_path / "android-sdk"

        manifest = tmp_path / "app" / "src" / "main" / "AndroidManifest.xml"
        manifest.parent.mkdir(parents=True)
        manifest.write_text('<manifest package="com.microsoft.mdatp.xplat.hellodefender"/>')

        apk = tmp_path / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
        apk.parent.mkdir(parents=True)
        apk.write_text("apk")

        with patch.object(scenario, "_ensure_emulator_serial", return_value="emulator-5554") as mock_ensure_emulator:
            with patch("demo_framework.scenarios.android_studio.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="com.microsoft.mdatp.xplat.hellodefender/.MainActivity")
                ok = scenario._run_build_command(tmp_path, "optimized")

        assert ok is True
        mock_ensure_emulator.assert_called_once()
        gradle_calls = [call.args[0] for call in mock_run.call_args_list if call.args and call.args[0] and call.args[0][0] in ("./gradlew", "gradle")]
        gradle_envs = [call.kwargs.get("env") for call in mock_run.call_args_list if call.args and call.args[0] and call.args[0][0] in ("./gradlew", "gradle")]
        assert any(call[-1] == "clean" for call in gradle_calls)
        assert all(call[-1] != "connectedDebugAndroidTest" for call in gradle_calls)
        assert any(call[-1] == "assembleDebug" for call in gradle_calls)
        assert all(env and env.get("ANDROID_SDK_ROOT") == str(scenario.android_sdk_root) for env in gradle_envs)
        assert all(env and env.get("ANDROID_HOME") == str(scenario.android_sdk_root) for env in gradle_envs)
