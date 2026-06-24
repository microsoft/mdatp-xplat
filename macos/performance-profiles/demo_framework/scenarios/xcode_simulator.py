"""Apple-template iOS simulator demo scenario.

Uses a local Xcode template app and measures simulator build/install/launch
workflow impact with MDE performance profiles.
"""

import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from .base import ScenarioConfig
from .profiled_build import ProfiledBuildScenario
from ..ui import print_error, print_info


class XcodeSimulatorScenario(ProfiledBuildScenario):
    """Demo scenario for a local Apple-template iOS app on Simulator."""

    def __init__(
        self,
        repo_path: Optional[Path] = None,
        profile_change_policy: str = "prompt",
        run_tests_by_default: bool = True,
    ):
        default_repo = Path(__file__).resolve().parents[2] / "apps" / "hello-defender-ios"
        config = ScenarioConfig(
            name="HelloDefender iOS Simulator Demo",
            description="Demo showing MDE impact on a local HelloDefender iOS simulator workflow",
            repo_url="https://developer.apple.com/xcode/",
            repo_path=repo_path or default_repo,
            build_command="xcodebuild test + simctl install + simctl launch",
            profiles=["xcode", "ios-simulator-tree", "iphone-simulator-tree", "git"],
            estimated_duration_minutes=10,
        )
        self.run_tests_by_default = run_tests_by_default
        super().__init__(
            config=config,
            build_command=["xcodebuild", "build"],
            tool_checks=[
                ["xcodebuild", "-version"],
                ["xcrun", "--version"],
            ],
            repo_validation_file=None,
            clone_in_timed_phases=False,
            build_cleanup_paths=[".mde-derived"],
            default_exclusions=[
                {"type": "folder", "rel": ".mde-derived"},
            ],
            eicar_subdir=".mde-derived",
            profile_change_policy=profile_change_policy,
        )

    def setup(self) -> bool:
        """Require a local Apple-template app instead of cloning third-party sources."""
        if not self.config.repo_path.exists():
            print_error(f"Local app path not found: {self.config.repo_path}")
            print_info("Expected an in-repo HelloDefender app project (or pass --repo to override).")
            return False

        project_files = sorted(self.config.repo_path.glob("*.xcodeproj"))
        if not project_files:
            print_error("No .xcodeproj found in local app path")
            print_info("Point --repo to a folder containing your Apple-template iOS app project.")
            return False

        return super().setup()

    def _detect_project_and_scheme(self, cwd: Path):
        """Pick the first local project and a runnable scheme."""
        project_files = sorted(cwd.glob("*.xcodeproj"))
        if not project_files:
            return None, None

        project = project_files[0]
        result = subprocess.run(
            ["xcodebuild", "-list", "-project", project.name],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        lines = (result.stdout or "").splitlines()

        scheme = None
        in_schemes = False
        for line in lines:
            stripped = line.strip()
            if stripped == "Schemes:":
                in_schemes = True
                continue
            if in_schemes:
                if not stripped:
                    continue
                scheme = stripped
                break

        return project, scheme

    def _first_bootable_simulator_udid(self) -> Optional[str]:
        """Pick a simulator UDID, preferring a currently booted device."""
        result = subprocess.run(
            ["xcrun", "simctl", "list", "devices", "available"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        lines = (result.stdout or "").splitlines()

        for line in lines:
            if "(Booted)" in line and "(" in line:
                parts = line.split("(")
                if len(parts) >= 2:
                    return parts[1].split(")")[0].strip()

        for line in lines:
            if "iPhone" in line and "(Shutdown)" in line and "(" in line:
                parts = line.split("(")
                if len(parts) >= 2:
                    return parts[1].split(")")[0].strip()

        return None

    def _bundle_identifier(self, app_path: Path) -> Optional[str]:
        """Read CFBundleIdentifier from app Info.plist."""
        plist_path = app_path / "Info.plist"
        result = subprocess.run(
            ["/usr/libexec/PlistBuddy", "-c", "Print :CFBundleIdentifier", str(plist_path)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        bundle_id = (result.stdout or "").strip()
        return bundle_id or None

    def _run_build_command(self, cwd: Path, label: str) -> bool:
        """Build app for simulator, boot simulator, then install + launch app."""
        project, scheme = self._detect_project_and_scheme(cwd)
        if not project or not scheme:
            return False

        derived = cwd / ".mde-derived"

        clean_cmd = [
            "xcodebuild",
            "-project", project.name,
            "-scheme", scheme,
            "-destination", "generic/platform=iOS Simulator",
            "-derivedDataPath", str(derived),
            "clean",
        ]

        clean_result = subprocess.run(clean_cmd, cwd=cwd, timeout=1200, check=False)
        if clean_result.returncode != 0:
            return False

        build_cmd = [
            "xcodebuild",
            "-project", project.name,
            "-scheme", scheme,
            "-destination", "generic/platform=iOS Simulator",
            "-derivedDataPath", str(derived),
            "build",
        ]

        if self.run_tests_by_default:
            test_cmd = [
                "xcodebuild",
                "-project", project.name,
                "-scheme", scheme,
                "-destination", "platform=iOS Simulator,name=iPhone 16",
                "-derivedDataPath", str(derived),
                "test",
            ]
            test_result = subprocess.run(test_cmd, cwd=cwd, timeout=2400, check=False)
            if test_result.returncode != 0:
                return False

        build_result = subprocess.run(build_cmd, cwd=cwd, timeout=1800, check=False)
        if build_result.returncode != 0:
            return False

        app_candidates = sorted((derived / "Build" / "Products" / "Debug-iphonesimulator").glob("*.app"))
        if not app_candidates:
            return False
        app_path = app_candidates[0]

        if not app_path.exists():
            return False

        udid = self._first_bootable_simulator_udid()
        if not udid:
            return False

        sim_home = Path(tempfile.gettempdir()) / f"mde-sim-home-{label.lower()}"
        sim_env = {"SIMULATOR_SHARED_RESOURCES_DIRECTORY": str(sim_home)}

        subprocess.run(["open", "-a", "Simulator"], cwd=cwd, timeout=30, check=False)
        subprocess.run(["xcrun", "simctl", "boot", udid], cwd=cwd, env=sim_env, timeout=60, check=False)
        subprocess.run(["xcrun", "simctl", "bootstatus", udid, "-b"], cwd=cwd, env=sim_env, timeout=120, check=False)

        install_result = subprocess.run(
            ["xcrun", "simctl", "install", udid, str(app_path)],
            cwd=cwd,
            env=sim_env,
            timeout=60,
            check=False,
        )
        if install_result.returncode != 0:
            return False

        bundle_id = self._bundle_identifier(app_path)
        if not bundle_id:
            return False

        launch_result = subprocess.run(
            ["xcrun", "simctl", "launch", udid, bundle_id],
            cwd=cwd,
            env=sim_env,
            timeout=60,
            check=False,
        )
        return launch_result.returncode == 0
