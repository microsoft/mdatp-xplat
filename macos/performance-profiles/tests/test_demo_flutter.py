"""Live demo: MDE performance profiles vs. AV exclusions on a Flutter build.

Run it:
    pytest -m integration -s -k flutter

Requires: sudo, real-time protection on, and the `flutter` CLI with the macOS
desktop toolchain enabled. Uses the local HelloDefender Flutter app in
apps/hello-defender-flutter — no clone needed.

The flutter-dart profile covers the `dart` binary and `flutter_tools.snapshot`
by team ID / signing ID, so it mutes the dart/flutter toolchain wherever it
writes. Any other process writing to the same directories is still fully
monitored.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from demo_steps import Scenario, three_way_demo

APP_DIR = Path(__file__).resolve().parents[1] / "apps" / "hello-defender-flutter"
CORESIM_FRAMEWORK = Path("/Library/Developer/PrivateFrameworks/CoreSimulator.framework/Versions/A/CoreSimulator")

# Flutter writes most of its work into the user pub-cache (downloaded packages)
# and into the in-repo .dart_tool/ + build/ trees. The flutter-dart profile
# mutes the toolchain wherever it writes; for an apples-to-apples comparison
# the exclusions phase covers the in-repo dirs plus the pub cache.
PUB_CACHE = "~/.pub-cache"

SCENARIO = Scenario(
    name="flutter",
    # macos desktop target — keeps the demo CLI-only without needing an emulator.
    build_cmd=["flutter", "build", "macos", "--release"],
    eicar_subdir="build",
    profiles=["flutter-dart", "git"],
    exclusion_subdirs=[".dart_tool", "build"],
    exclusion_abs_paths=[PUB_CACHE],
    clean_paths=[".dart_tool", "build"],
)


def _ensure_scaffolded(app_dir: Path) -> None:
    """`flutter build macos` needs the macos/ runner. Run `flutter create .` once
    to materialize it (and ios/android stubs); subsequent runs are no-ops."""
    if (app_dir / "macos" / "Runner.xcodeproj").exists():
        return
    subprocess.run(
        ["flutter", "create", "--platforms=macos", "."],
        cwd=app_dir, check=True, timeout=300,
    )


def _ensure_xcode_ready_for_flutter() -> None:
    if shutil.which("xcodebuild") is None:
        pytest.fail(
            "\n".join(
                [
                    "Xcode command line tools are required for the flutter performance-profile demo.",
                    "Install/initialize Xcode tools, then re-run:",
                    "  1) xcode-select --install",
                    "  2) sudo xcodebuild -runFirstLaunch",
                    "  3) xcodebuild -version",
                    "  4) sudo -v && python -m pytest -m integration -s -k flutter",
                ]
            ),
            pytrace=False,
        )

    if not CORESIM_FRAMEWORK.exists():
        pytest.fail(
            "\n".join(
                [
                    "Xcode first-launch components are not initialized for Flutter macOS builds.",
                    f"Missing required framework: {CORESIM_FRAMEWORK}",
                    "Initialize Xcode and re-run:",
                    "  1) sudo xcodebuild -runFirstLaunch",
                    "  2) xcodebuild -runFirstLaunch -checkForNewerComponents",
                    "  3) xcodebuild -version",
                    "  4) sudo -v && python -m pytest -m integration -s -k flutter",
                ]
            ),
            pytrace=False,
        )


@pytest.fixture(scope="session")
def flutter_app():
    if shutil.which("flutter") is None:
        pytest.fail(
            "\n".join(
                [
                    "Flutter CLI is required for the flutter performance-profile demo.",
                    "Install Flutter, then re-run:",
                    "  1) brew install --cask flutter",
                    "  2) flutter --version",
                    "  3) sudo -v && python -m pytest -m integration -s -k flutter",
                ]
            ),
            pytrace=False,
        )
    if not (APP_DIR / "pubspec.yaml").exists():
        pytest.fail(
            "\n".join(
                [
                    f"Required local Flutter app not found: {APP_DIR}",
                    "Ensure the repository is complete, then re-run:",
                    "  sudo -v && python -m pytest -m integration -s -k flutter",
                ]
            ),
            pytrace=False,
        )
    _ensure_xcode_ready_for_flutter()
    _ensure_scaffolded(APP_DIR)
    return APP_DIR


@pytest.mark.integration
@pytest.mark.slow
def test_flutter_profiles_compared_to_exclusions(flutter_app, report, require_rtp, clean_mde):
    three_way_demo(flutter_app, SCENARIO, report)
