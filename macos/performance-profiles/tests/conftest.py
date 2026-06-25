"""Pytest fixtures for the live MDE performance-profile demos.

These fixtures are opt-in — only the integration tests request them, so the
existing framework unit tests are unaffected. They guarantee the endpoint is
returned to its original profile/exclusion state even if a test fails.
"""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

import pytest

# Make the sibling helper modules importable as top-level (tests/ is a package).
sys.path.insert(0, str(Path(__file__).parent))

import mde


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: live demo that drives mdatp and runs real builds")
    config.addinivalue_line("markers", "slow: takes minutes (real clone + build)")


@pytest.fixture(scope="session")
def require_sudo():
    """Authenticate sudo once, then keep the credential warm for the whole session.

    macOS expires the sudo timestamp after a few minutes, so without this every
    `sudo mdatp ...` call during a long build would re-prompt for a password or
    fingerprint. A background thread refreshes the timestamp every 60s so the
    user authenticates exactly once.
    """
    if subprocess.run(["sudo", "-n", "true"], capture_output=True).returncode != 0:
        # Prompt once, interactively, before tests start.
        if subprocess.run(["sudo", "-v"]).returncode != 0:
            pytest.skip("sudo is required for the live MDE demos")

    stop = threading.Event()

    def _keepalive():
        while not stop.wait(60):
            subprocess.run(["sudo", "-n", "-v"], capture_output=True)

    refresher = threading.Thread(target=_keepalive, daemon=True)
    refresher.start()
    try:
        yield True
    finally:
        stop.set()


@pytest.fixture
def require_rtp(require_sudo):
    """Skip a test if real-time protection is off (detection can't be shown)."""
    if not mde.rtp_enabled():
        pytest.skip("real-time protection is disabled — enable it to run the demo")
    return True


@pytest.fixture
def clean_mde(require_sudo):
    """Reset MDE to its pre-test state — for both setup and teardown.

    Snapshots the applied profiles and folder exclusions before the test, then
    removes anything the test added afterwards. This guarantees each scenario
    starts clean and leaves the endpoint exactly as it found it, even on failure.
    """
    from pathlib import Path

    profiles_before = set(mde.list_applied_profiles())
    exclusions_before = set(mde.list_exclusion_paths())

    def restore():
        for name in sorted(set(mde.list_applied_profiles()) - profiles_before):
            mde.remove_profiles([name])
        for path in sorted(set(mde.list_exclusion_paths()) - exclusions_before):
            mde.remove_exclusion(Path(path))

    restore()   # setup: clear any leftovers from an interrupted previous run
    yield
    restore()   # teardown: undo whatever this test applied



@pytest.fixture(scope="session")
def report():
    """Collect each scenario's 3-way numbers and print one table at the end."""
    rows = []

    class Report:
        def record(self, scenario, baseline, exclusions, profiles,
                   baseline_caught, exclusions_caught, profiles_caught,
                   applied_profiles=None, added_exclusions=None):
            rows.append((scenario, baseline, exclusions, profiles,
                         baseline_caught, exclusions_caught, profiles_caught,
                         list(applied_profiles or []), list(added_exclusions or [])))

    yield Report()

    if not rows:
        return

    def icon(caught):
        return "detected ✅" if caught else "not detected ⚠️"

    def cpu(m):
        return f"{m.mde_cpu:.1f}%" if m.mde_cpu is not None else "n/a"

    def drop(base, val):
        if base.mde_cpu is None or val.mde_cpu is None:
            return ""
        diff = base.mde_cpu - val.mde_cpu
        sign = "-" if diff >= 0 else "+"
        return f"({sign}{abs(diff):.1f}%)"

    def tdelta(base, val):
        if not base.elapsed:
            return ""
        pct = (base.elapsed - val.elapsed) / base.elapsed * 100
        word = "faster" if pct >= 0 else "slower"
        return f"({abs(pct):.1f}% {word})"

    print("\n\n=== MDE Performance Profiles — Demo Results ===\n")
    header = f"{'Scenario / metric':<22}{'Baseline':>14}{'Exclusions':>22}{'Profiles':>22}"
    print(header)
    print("-" * len(header))
    for (name, base, excl, prof, base_c, excl_c, prof_c, _profiles, _excl) in rows:
        print(f"{name:<22}")
        print(f"{'  build time':<22}{f'{base.elapsed:.1f}s':>14}{f'{excl.elapsed:.1f}s ' + tdelta(base, excl):>22}{f'{prof.elapsed:.1f}s ' + tdelta(base, prof):>22}")
        print(f"{'  MDE scan CPU':<22}{cpu(base):>14}{cpu(excl) + ' ' + drop(base, excl):>22}{cpu(prof) + ' ' + drop(base, prof):>22}")
        print(f"{'  EICAR':<22}{icon(base_c):>14}{icon(excl_c):>22}{icon(prof_c):>22}")

    print("\nApplied during each scenario:")
    for (name, _b, _e, _p, _bc, _ec, _pc, profiles, exclusions) in rows:
        print(f"  {name}:")
        print(f"    perf profiles  : {', '.join(profiles) or 'none'}")
        print(f"    AV exclusions  : {', '.join(exclusions) or 'none'}")

    print(
        "\nMDE scan CPU is sampled during each build as the scanner's load signal."
        "\nCustomer-configured AV folder exclusions cut it the most — but they stop"
        "\nreal-time protection from seeing threats there (EICAR slips through the"
        "\nexcluded build dir). Performance profiles keep the build fast while"
        "\nreal-time protection stays effective (EICAR still detected). The EICAR row"
        "\nis the bottom line: only profiles avoid the protection gap.\n"
    )

