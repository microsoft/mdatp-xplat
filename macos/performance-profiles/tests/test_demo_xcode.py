"""Live demo: MDE performance profiles vs. AV exclusions on a Swift/Xcode build.

Run it:
    pytest -m integration -s -k xcode

Requires: sudo, real-time protection on, and `swift`. Clones microsoft/fluentui-apple
into ~/demo (reused if already present).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from demo_steps import Scenario, three_way_demo

REPO_URL = "https://github.com/microsoft/fluentui-apple.git"
REPO_DIR = Path.home() / "demo" / "fluentui-apple-tests"

SCENARIO = Scenario(
    name="xcode",
    build_cmd=["swift", "build", "-c", "release"],
    eicar_subdir=".build",
    profiles=["xcode", "xcode-ide-tree", "git"],
    exclusion_subdirs=[".build", "DerivedData"],
)


@pytest.fixture(scope="session")
def xcode_repo():
    if shutil.which("swift") is None:
        pytest.skip("swift not installed")
    if not (REPO_DIR / "Package.swift").exists():
        REPO_DIR.parent.mkdir(parents=True, exist_ok=True)
        if REPO_DIR.exists():
            shutil.rmtree(REPO_DIR, ignore_errors=True)
        subprocess.run(["git", "clone", "--depth", "1", REPO_URL, str(REPO_DIR)], check=True)
    return REPO_DIR


@pytest.mark.integration
@pytest.mark.slow
def test_xcode_profiles_compared_to_exclusions(xcode_repo, report, require_rtp, clean_mde):
    three_way_demo(xcode_repo, SCENARIO, report)
