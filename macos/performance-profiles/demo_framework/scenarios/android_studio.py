"""Android Studio emulator demo scenario.

Uses a local Android app and measures emulator test/build/install/launch
workflow impact with MDE performance profiles.
"""

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

from .base import ScenarioConfig
from .profiled_build import ProfiledBuildScenario
from ..ui import print_error, print_info


class AndroidStudioScenario(ProfiledBuildScenario):
    """Demo scenario for a local Android Studio app on emulator."""

    def __init__(
        self,
        repo_path: Optional[Path] = None,
        profile_change_policy: str = "prompt",
        run_tests_by_default: bool = True,
        enable_client_analyzer: Optional[bool] = None,
        enable_exclusion_workflow: Optional[bool] = None,
    ):
        default_repo = Path(__file__).resolve().parents[2] / "apps" / "hello-defender-android"
        config = ScenarioConfig(
            name="HelloDefender Android Emulator Demo",
            description="Demo showing MDE impact on a local Android emulator workflow",
            repo_url="https://developer.android.com/studio",
            repo_path=repo_path or default_repo,
            build_command="gradle clean + test + assemble + adb install + adb launch",
            profiles=["android-studio", "android-studio-tree", "java", "git"],
            estimated_duration_minutes=12,
        )
        self.run_tests_by_default = run_tests_by_default
        super().__init__(
            config=config,
            build_command=["./gradlew", "assembleDebug"],
            tool_checks=[],
            repo_validation_file=None,
            clone_in_timed_phases=False,
            build_cleanup_paths=[".gradle", "app/build"],
            recommend_keywords={
                "android-studio": ["android studio", "gradle", "kotlin", "dex", "aapt", "android"],
                "android-studio-tree": [".gradle", "build/intermediates", "build/generated", "javac", "kapt"],
                "java": ["java", "javac", "jvm", "kotlinc"],
                "git": ["/git", "git-core", "git "],
            },
            enable_client_analyzer=False if enable_client_analyzer is None else enable_client_analyzer,
            enable_exclusion_workflow=enable_exclusion_workflow,
            profile_change_policy=profile_change_policy,
        )
        self.adb_command = "adb"
        self.emulator_command = "emulator"
        self.android_sdk_root: Optional[Path] = None

    @staticmethod
    def _resolve_command(cmd: str) -> Optional[str]:
        result = subprocess.run(["which", cmd], capture_output=True, text=True, timeout=5, check=False)
        resolved = (result.stdout or "").strip()
        if result.returncode == 0 and resolved:
            return resolved
        return None

    @staticmethod
    def _android_sdk_roots():
        roots = []
        for env_name in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
            value = os.environ.get(env_name)
            if value:
                roots.append(Path(value).expanduser())

        roots.append(Path.home() / "Library" / "Android" / "sdk")

        unique_roots = []
        seen = set()
        for root in roots:
            root_str = str(root)
            if root_str not in seen:
                unique_roots.append(root)
                seen.add(root_str)
        return unique_roots

    @classmethod
    def _resolve_android_sdk_tool(cls, tool_subpath: str, fallback_name: str):
        resolved = cls._resolve_command(fallback_name)
        if resolved:
            return resolved, [f"PATH:{fallback_name} -> {resolved}"]

        diagnostics = [f"PATH:{fallback_name} -> (not found)"]

        for sdk_root in cls._android_sdk_roots():
            candidate = sdk_root / tool_subpath
            diagnostics.append(f"SDK:{candidate} exists={candidate.exists()}")
            if candidate.exists():
                return str(candidate), diagnostics

        return None, diagnostics

    @staticmethod
    def _android_studio_installed() -> bool:
        return Path("/Applications/Android Studio.app").exists()

    def setup(self) -> bool:
        """Require Android Studio tooling only for this scenario."""
        sdk_roots = [str(root) for root in self._android_sdk_roots()]
        self._log_line(f"android.setup sdk_roots={sdk_roots}")

        if not self._android_studio_installed():
            self._log_line("android.setup android_studio=/Applications/Android Studio.app exists=False")
            print_error("Android Studio is not installed: /Applications/Android Studio.app not found")
            print_info("Install Android Studio, then re-run this scenario.")
            return False
        self._log_line("android.setup android_studio=/Applications/Android Studio.app exists=True")

        adb_command, adb_diagnostics = self._resolve_android_sdk_tool("platform-tools/adb", "adb")
        for line in adb_diagnostics:
            self._log_line(f"android.setup adb {line}")
        if not adb_command:
            self._log_line("android.setup adb resolution=failed")
            print_error("adb not found in PATH")
            print_info("Install Android platform-tools (SDK Manager) and ensure adb is installed.")
            return False
        self.adb_command = adb_command
        self.android_sdk_root = Path(adb_command).resolve().parents[1]
        self._log_line(f"android.setup adb resolution={adb_command}")

        emulator_command, emulator_diagnostics = self._resolve_android_sdk_tool("emulator/emulator", "emulator")
        for line in emulator_diagnostics:
            self._log_line(f"android.setup emulator {line}")
        if not emulator_command:
            self._log_line("android.setup emulator resolution=failed")
            print_error("emulator not found in PATH")
            print_info("Install Android Emulator (SDK Manager) and ensure emulator is installed.")
            return False
        self.emulator_command = emulator_command
        if self.android_sdk_root is None:
            self.android_sdk_root = Path(emulator_command).resolve().parents[1]
        self._log_line(f"android.setup emulator resolution={emulator_command}")
        self._log_line(f"android.setup sdk_root={self.android_sdk_root}")

        if not self.config.repo_path.exists():
            print_error(f"Local app path not found: {self.config.repo_path}")
            print_info("Expected an in-repo Android app project (or pass --repo to override).")
            return False

        if not (self.config.repo_path / "app" / "src" / "main" / "AndroidManifest.xml").exists():
            self._log_line("android.setup manifest exists=False")
            print_error("Android project manifest not found at app/src/main/AndroidManifest.xml")
            return False
        self._log_line("android.setup manifest exists=True")

        gradlew_exists = (self.config.repo_path / "gradlew").exists()
        gradle_command = self._resolve_command("gradle")
        self._log_line(f"android.setup gradlew exists={gradlew_exists}")
        self._log_line(f"android.setup gradle path={gradle_command or '(not found)'}")
        if not gradlew_exists and not gradle_command:
            print_error("No gradle wrapper found and gradle command is unavailable")
            print_info("Add a gradle wrapper (gradlew) to the project or install gradle.")
            return False

        connected_serial = self._first_booted_emulator_serial()
        avd_name = self._first_avd_name()
        self._log_line(f"android.setup connected_serial={connected_serial or '(none)'}")
        self._log_line(f"android.setup avd_name={avd_name or '(none)'}")
        if not connected_serial and not avd_name:
            print_error("No Android emulator or device is available")
            print_info("Create an Android Virtual Device in Android Studio Device Manager, or start/connect a device, then re-run this scenario.")
            return False

        return super().setup()

    def _first_booted_emulator_serial(self) -> Optional[str]:
        result = subprocess.run([self.adb_command, "devices"], capture_output=True, text=True, timeout=10, check=False)
        for line in (result.stdout or "").splitlines():
            parts = line.strip().split()
            if len(parts) == 2 and parts[1] == "device" and parts[0].startswith("emulator-"):
                return parts[0]
        return None

    def _first_avd_name(self) -> Optional[str]:
        result = subprocess.run([self.emulator_command, "-list-avds"], capture_output=True, text=True, timeout=10, check=False)
        names = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
        return names[0] if names else None

    def _ensure_emulator_serial(self) -> Optional[str]:
        serial = self._first_booted_emulator_serial()
        if serial:
            return serial

        avd_name = self._first_avd_name()
        if not avd_name:
            return None

        subprocess.Popen(
            [self.emulator_command, "-avd", avd_name, "-no-snapshot-load"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        deadline = time.time() + 180
        while time.time() < deadline:
            serial = self._first_booted_emulator_serial()
            if serial:
                subprocess.run([self.adb_command, "-s", serial, "wait-for-device"], timeout=20, check=False)
                return serial
            time.sleep(2)

        return None

    @staticmethod
    def _manifest_package_name(cwd: Path) -> Optional[str]:
        # Prefer namespace from app/build.gradle.kts (modern AGP; manifest package= is deprecated)
        build_gradle = cwd / "app" / "build.gradle.kts"
        if build_gradle.exists():
            try:
                text = build_gradle.read_text()
                m = re.search(r'namespace\s*=\s*"([^"]+)"', text)
                if m:
                    return m.group(1)
            except Exception:
                pass

        # Groovy build.gradle fallback
        build_gradle_groovy = cwd / "app" / "build.gradle"
        if build_gradle_groovy.exists():
            try:
                text = build_gradle_groovy.read_text()
                m = re.search(r'namespace\s+"([^"]+)"', text)
                if m:
                    return m.group(1)
            except Exception:
                pass

        # Legacy: package= in AndroidManifest.xml
        manifest = cwd / "app" / "src" / "main" / "AndroidManifest.xml"
        try:
            text = manifest.read_text()
        except Exception:
            return None
        match = re.search(r'package\s*=\s*"([^"]+)"', text)
        return match.group(1) if match else None

    @staticmethod
    def _gradle_base_command(cwd: Path):
        gradlew = cwd / "gradlew"
        if gradlew.exists():
            return ["./gradlew"]
        return ["gradle"]

    def _android_env(self):
        env = dict(os.environ)
        if self.android_sdk_root:
            sdk_root = str(self.android_sdk_root)
            env["ANDROID_SDK_ROOT"] = sdk_root
            env["ANDROID_HOME"] = sdk_root
        return env

    def _run_build_command(self, cwd: Path, label: str) -> bool:
        """Clean/test/build app for emulator, then install + launch app."""
        gradle_cmd = self._gradle_base_command(cwd)
        android_env = self._android_env()
        serial = None

        if self.run_tests_by_default:
            serial = self._ensure_emulator_serial()
            if not serial:
                return False

        clean_result = subprocess.run(gradle_cmd + ["clean"], cwd=cwd, env=android_env, timeout=1200, check=False)
        if clean_result.returncode != 0:
            return False

        if self.run_tests_by_default:
            test_result = subprocess.run(
                gradle_cmd + ["connectedDebugAndroidTest"],
                cwd=cwd,
                env=android_env,
                timeout=2400,
                check=False,
            )
            if test_result.returncode != 0:
                return False

        build_result = subprocess.run(
            gradle_cmd + ["assembleDebug"],
            cwd=cwd,
            env=android_env,
            timeout=1800,
            check=False,
        )
        if build_result.returncode != 0:
            return False

        apk_path = cwd / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
        if not apk_path.exists():
            return False

        if not serial:
            serial = self._ensure_emulator_serial()
            if not serial:
                return False

        install_result = subprocess.run(
            [self.adb_command, "-s", serial, "install", "-r", str(apk_path)],
            cwd=cwd,
            env=android_env,
            timeout=120,
            check=False,
        )
        if install_result.returncode != 0:
            return False

        package_name = self._manifest_package_name(cwd)
        if not package_name:
            return False

        resolve_result = subprocess.run(
            [self.adb_command, "-s", serial, "shell", "cmd", "package", "resolve-activity", "--brief", package_name],
            cwd=cwd,
            env=android_env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        launch_activity = None
        if resolve_result.returncode == 0:
            for line in (resolve_result.stdout or "").splitlines():
                stripped = line.strip()
                if stripped and "/" in stripped and not stripped.startswith("priority"):
                    launch_activity = stripped

        if not launch_activity:
            launch_activity = f"{package_name}/.MainActivity"

        launch_result = subprocess.run(
            [self.adb_command, "-s", serial, "shell", "am", "start", "-n", launch_activity],
            cwd=cwd,
            env=android_env,
            timeout=30,
            check=False,
        )
        return launch_result.returncode == 0
