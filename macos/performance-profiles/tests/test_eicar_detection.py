"""Standalone EICAR detection check — the signal the whole demo relies on.

Fast (no build): proves real-time protection catches an EICAR file in a normal
directory, and that an AV folder exclusion stops it from being detected. If this fails,
the scenario demos can't be trusted, so run it first:

    pytest -m integration -s -k eicar

RTP only scans paths it monitors; per-user temp dirs (/private/var/folders) are
not, so this probes a directory under $HOME.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

import mde

SCRATCH = Path.home() / "demo" / "eicar-pytest"


def _diagnostics(result: mde.EicarResult) -> str:
    threats = subprocess.run(
        ["mdatp", "threat", "list"], capture_output=True, text=True, check=False
    ).stdout or "(empty)"
    return (
        f"\nEICAR not detected — diagnostics:\n"
        f"  path           : {result.path}\n"
        f"  file_exists    : {result.file_exists} (still on disk → RTP never removed it)\n"
        f"  threat_count   : before={result.count_before} after={result.count_after}\n"
        f"  waited         : {result.elapsed:.0f}s\n"
        f"  rtp_enabled    : {mde.rtp_enabled()}\n"
        f"  mdatp threat list:\n{threats}\n"
    )


@pytest.fixture
def scratch_dir():
    SCRATCH.mkdir(parents=True, exist_ok=True)
    yield SCRATCH
    shutil.rmtree(SCRATCH, ignore_errors=True)


@pytest.mark.integration
def test_eicar_detection_and_exclusion_gap(scratch_dir, require_rtp, clean_mde):
    # 1. RTP catches EICAR written to an ordinary (unexcluded) directory.
    watched = scratch_dir / "watched"
    result = mde.eicar_probe(watched)
    if result.path.exists():
        result.path.unlink()
    assert result.detected, _diagnostics(result)

    # 2. An AV folder exclusion stops that same file from being detected.
    excluded = scratch_dir / "excluded"
    excluded.mkdir()
    mde.add_exclusion(excluded)
    try:
        assert not mde.eicar_detected(excluded, timeout=15), (
            "AV folder exclusion should create a detection gap"
        )
    finally:
        mde.remove_exclusion(excluded)
