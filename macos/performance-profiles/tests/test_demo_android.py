"""Live demo: MDE performance profiles vs. AV exclusions on an Android build.

Run it:
    pytest -m integration -s -k android

Requires: sudo, real-time protection on, an Android SDK (ANDROID_SDK_ROOT /
ANDROID_HOME or the default ~/Library/Android/sdk) with platform-tools (adb) and
an emulator + at least one AVD, and a JDK (Android Studio's bundled JBR is used
as a fallback). Uses the local HelloDefender Android app in
apps/hello-defender-android — no clone needed.

Mirrors the xcode-simulator demo: each phase runs `./gradlew assembleDebug`, then
installs and launches the APK on a booted emulator *inside the timed window* so
the full build→install→launch workflow's scan-load is measured. The build writes
into app/build and .gradle; install/launch writes into the emulator's data image
under ~/.android/avd. The AV-exclusions phase therefore excludes those build dirs
plus the emulator tree (what a real Android dev would exclude), and the perf
profiles (`android-studio` + `android-studio-tree`) cover the same trees — so it's
an apples-to-apples comparison.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

from demo_steps import Scenario, three_way_demo

APP_DIR = Path(__file__).resolve().parents[1] / "apps" / "hello-defender-android"
PACKAGE = "com.microsoft.mdatp.xplat.hellodefender"
LAUNCH_COMPONENT = f"{PACKAGE}/.MainActivity"
APK_REL = "app/build/outputs/apk/debug/app-debug.apk"
# The emulator data tree adb install/launch writes into — the analog of iOS's
# CoreSimulator. The android-studio profiles cover this, so the exclusions phase
# excludes it too for an apples-to-apples comparison.
EMULATOR_TREE = "~/.android/avd"

SCENARIO = Scenario(
    name="android",
    build_cmd=["./gradlew", "assembleDebug"],
    eicar_subdir="app/build",
    profiles=["android-studio", "android-studio-tree", "openjdk-javac", "git"],
    exclusion_subdirs=[".gradle", "app/build"],
    exclusion_abs_paths=[EMULATOR_TREE],
)


# ── Android SDK / JDK resolution ─────────────────────────────────────────

def _android_sdk_root() -> Path | None:
    for env in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
        value = os.environ.get(env)
        if value and Path(value).expanduser().exists():
            return Path(value).expanduser()
    default = Path.home() / "Library" / "Android" / "sdk"
    return default if default.exists() else None


def _ensure_jdk() -> None:
    """Make sure gradlew can find a JDK; fall back to Android Studio's bundled JBR."""
    if os.environ.get("JAVA_HOME") and Path(os.environ["JAVA_HOME"]).exists():
        return
    jbr = Path("/Applications/Android Studio.app/Contents/jbr/Contents/Home")
    if jbr.exists():
        os.environ["JAVA_HOME"] = str(jbr)


def _adb(sdk: Path) -> str:
    return str(sdk / "platform-tools" / "adb")


def _emulator(sdk: Path) -> str:
    return str(sdk / "emulator" / "emulator")


# ── Emulator orchestration ───────────────────────────────────────────────

def _booted_serial(adb: str) -> str | None:
    out = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=15).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == "device" and parts[0].startswith("emulator-"):
            return parts[0]
    return None


def _boot_emulator(adb: str, emulator: str):
    """Return (serial, booted_by_us). Reuses a running emulator if one exists,
    otherwise boots the first AVD headlessly and waits for sys.boot_completed."""
    serial = _booted_serial(adb)
    if serial:
        return serial, False

    avds = subprocess.run(
        [emulator, "-list-avds"], capture_output=True, text=True, timeout=15
    ).stdout.split()
    if not avds:
        pytest.skip("no Android AVD available to boot (create one in Device Manager)")

    subprocess.Popen(
        [emulator, "-avd", avds[0], "-no-snapshot-load", "-no-window", "-no-audio", "-no-boot-anim"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    deadline = time.time() + 300
    while time.time() < deadline:
        serial = _booted_serial(adb)
        if serial:
            subprocess.run([adb, "-s", serial, "wait-for-device"], timeout=30, check=False)
            done = subprocess.run(
                [adb, "-s", serial, "shell", "getprop", "sys.boot_completed"],
                capture_output=True, text=True, timeout=15, check=False,
            ).stdout.strip()
            if done == "1":
                return serial, True
        time.sleep(3)

    raise RuntimeError("Android emulator did not finish booting within 300s")


def _install_and_launch(repo: Path, serial: str, adb: str) -> None:
    """Install and launch the freshly built APK on the emulator.

    Runs inside the timed build window so install (push APK into the emulator's
    data image) and launch scan-load is part of the same measurement. Raises on
    failure so the phase fails loudly, like a build error.
    """
    apk = repo / APK_REL
    if not apk.exists():
        raise RuntimeError(f"APK not found at {apk} — did assembleDebug succeed?")
    subprocess.run([adb, "-s", serial, "install", "-r", str(apk)], check=True, timeout=180)
    subprocess.run(
        [adb, "-s", serial, "shell", "am", "start", "-n", LAUNCH_COMPONENT],
        check=True, timeout=60,
    )


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def android_app():
    gradlew = APP_DIR / "gradlew"
    if not gradlew.exists():
        pytest.skip(f"local Android app not found at {APP_DIR}")
    sdk = _android_sdk_root()
    if sdk is None:
        pytest.skip("Android SDK not found (set ANDROID_SDK_ROOT or install to ~/Library/Android/sdk)")
    if not Path(_adb(sdk)).exists():
        pytest.skip("adb not found (install Android platform-tools)")
    if not Path(_emulator(sdk)).exists():
        pytest.skip("emulator not found (install the Android Emulator)")
    os.environ.setdefault("ANDROID_SDK_ROOT", str(sdk))
    os.environ.setdefault("ANDROID_HOME", str(sdk))
    _ensure_jdk()
    if not os.access(gradlew, os.X_OK):
        gradlew.chmod(0o755)
    return APP_DIR


@pytest.fixture(scope="session")
def android_emulator(android_app):
    sdk = _android_sdk_root()
    adb = _adb(sdk)
    serial, booted_by_us = _boot_emulator(adb, _emulator(sdk))
    yield serial, adb
    if booted_by_us:
        subprocess.run([adb, "-s", serial, "emu", "kill"], check=False, timeout=30)


@pytest.mark.integration
@pytest.mark.slow
def test_android_profiles_compared_to_exclusions(
    android_app, android_emulator, report, require_rtp, clean_mde
):
    serial, adb = android_emulator
    SCENARIO.post_build = lambda repo: _install_and_launch(repo, serial, adb)
    three_way_demo(android_app, SCENARIO, report)
