"""Live demo: MDE performance profiles vs. AV exclusions on an iOS Simulator build.

Run it:
    pytest -m integration -s -k xcode_simulator

Requires: sudo, real-time protection on, and Xcode (`xcodebuild` / `xcrun`). Uses
the local HelloDefender iOS app in apps/hello-defender-ios — no clone needed.

Each phase compiles the app for a *generic* iOS Simulator destination (no booted
device needed for the build), then installs and launches it on a booted simulator
*inside the timed window* so the full build→install→launch workflow's scan-load is
measured. The build writes into a DerivedData dir (Xcode's standard build-cache
name, so the `xcode` profile recognizes it); install/launch writes into
~/Library/Developer/CoreSimulator. The AV-exclusions phase therefore excludes both
trees (what a real iOS dev would exclude), and the perf profiles
(`xcode` + `ios-simulator-tree` + `iphone-simulator-tree`) cover the same trees —
so it's an apples-to-apples comparison.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from demo_steps import Scenario, three_way_demo

APP_DIR = Path(__file__).resolve().parents[1] / "apps" / "hello-defender-ios"
# Build into a dir literally named "DerivedData" (Xcode's standard name) so the
# `xcode` performance profile recognizes it as the build cache and relieves
# scanning there — a custom name like ".mde-derived" is not covered by the profile,
# which made profiles look like they cut no scan load.
DERIVED = "DerivedData"
BUNDLE_ID = "com.microsoft.mdatp.xplat.hellodefender"
# The iOS Simulator data tree install/launch writes into. The simulator-tree
# perf profiles cover this same tree, so the exclusions phase excludes it too.
SIMULATOR_TREE = "~/Library/Developer/CoreSimulator"


def _built_app(repo: Path) -> Path:
    products = repo / DERIVED / "Build" / "Products" / "Debug-iphonesimulator"
    apps = sorted(products.glob("*.app"))
    if not apps:
        raise RuntimeError(f"no built .app under {products} — did the build succeed?")
    return apps[0]


def _install_and_launch(repo: Path, udid: str) -> None:
    """Install and launch the freshly built app on the booted simulator.

    Runs inside the timed build window so the install (copy into the simulator's
    data container) and launch (process spawn) scan-load is part of the same
    measurement. Raises on failure so the phase fails loudly, like a build error.
    """
    app = _built_app(repo)
    subprocess.run(["xcrun", "simctl", "install", udid, str(app)], check=True, timeout=180)
    subprocess.run(["xcrun", "simctl", "launch", udid, BUNDLE_ID], check=True, timeout=120)


def _boot_simulator():
    """Return (udid, booted_by_us). Reuses a booted simulator if one exists,
    otherwise boots an available iPhone simulator and waits for it."""
    listing = subprocess.run(
        ["xcrun", "simctl", "list", "devices", "available", "--json"],
        capture_output=True, text=True, timeout=30, check=False,
    )
    devices = json.loads(listing.stdout or "{}").get("devices", {})
    all_devs = [d for runtime in devices.values() for d in runtime]

    booted = [d for d in all_devs if d.get("state") == "Booted"]
    if booted:
        return booted[0]["udid"], False

    iphones = [d for d in all_devs if "iPhone" in (d.get("name") or "")]
    target = iphones[0] if iphones else (all_devs[0] if all_devs else None)
    if target is None:
        pytest.fail(
            "\n".join(
                [
                    "No iOS Simulator runtime/device is available to boot.",
                    "Install an iOS simulator runtime in Xcode, then re-run:",
                    "  1) Open Xcode > Settings > Platforms and install an iOS runtime",
                    "  2) xcrun simctl list devices available",
                    "  3) sudo -v && python -m pytest -m integration -s -k xcode_simulator",
                ]
            ),
            pytrace=False,
        )

    udid = target["udid"]
    subprocess.run(["xcrun", "simctl", "boot", udid], check=False, timeout=120)
    subprocess.run(["xcrun", "simctl", "bootstatus", udid, "-b"], check=False, timeout=180)
    return udid, True


SCENARIO = Scenario(
    name="xcode-simulator",
    build_cmd=[
        "xcodebuild",
        "-project", "HelloDefender.xcodeproj",
        "-scheme", "HelloDefender",
        "-destination", "generic/platform=iOS Simulator",
        "-derivedDataPath", DERIVED,
        "build",
    ],
    eicar_subdir=DERIVED,
    profiles=["xcode", "ios-simulator-tree", "iphone-simulator-tree", "git"],
    exclusion_subdirs=[DERIVED],
    exclusion_abs_paths=[SIMULATOR_TREE],
)


@pytest.fixture(scope="session")
def ios_app():
    if shutil.which("xcodebuild") is None or shutil.which("xcrun") is None:
        pytest.fail(
            "\n".join(
                [
                    "Xcode command line tools (xcodebuild/xcrun) are required for the xcode_simulator demo.",
                    "Install them, then re-run:",
                    "  1) xcode-select --install",
                    "  2) xcodebuild -version && xcrun --version",
                    "  3) sudo -v && python -m pytest -m integration -s -k xcode_simulator",
                ]
            ),
            pytrace=False,
        )
    if not (APP_DIR / "HelloDefender.xcodeproj").exists():
        pytest.fail(
            "\n".join(
                [
                    f"Required local iOS app not found: {APP_DIR}",
                    "Ensure the repository is complete, then re-run:",
                    "  sudo -v && python -m pytest -m integration -s -k xcode_simulator",
                ]
            ),
            pytrace=False,
        )
    return APP_DIR


@pytest.fixture(scope="session")
def ios_simulator(ios_app):
    udid, booted_by_us = _boot_simulator()
    yield udid
    if booted_by_us:
        subprocess.run(["xcrun", "simctl", "shutdown", udid], check=False, timeout=60)


@pytest.mark.integration
@pytest.mark.slow
def test_xcode_simulator_profiles_compared_to_exclusions(
    ios_app, ios_simulator, report, require_rtp, clean_mde
):
    SCENARIO.post_build = lambda repo: _install_and_launch(repo, ios_simulator)
    three_way_demo(ios_app, SCENARIO, report)
