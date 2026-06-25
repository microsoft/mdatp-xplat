"""Live demo: MDE performance profiles vs. AV exclusions on a VS Code build.

Run it:
    pytest -m integration -s -k vscode

Requires: sudo, real-time protection on, Node.js, and npm. Clones
microsoft/vscode (tag 1.122.1) into ~/demo and runs `npm install` once (heavy,
several minutes) — both are reused if already present.

Unlike the xcode scenario, the npm compile reads/writes tens of thousands of
files across node_modules/out/.build, so AV folder exclusions produce a clear
build-time drop here. node_modules is excluded from scanning but installed once
and never deleted between builds.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from demo_steps import Scenario, three_way_demo

REPO_URL = "https://github.com/microsoft/vscode.git"
REPO_DIR = Path.home() / "demo" / "vscode-tests"
REPO_TAG = "1.122.1"
REQUIRED_NODE_MAJOR = 22  # vscode 1.122.1 hard-gates on Node 22.x (see .nvmrc / preinstall).

SCENARIO = Scenario(
    name="vscode",
    build_cmd=["npm", "run", "compile"],
    eicar_subdir="out",
    profiles=["node", "git", "vscode", "vscode-tree"],
    exclusion_subdirs=["node_modules", "out", ".build"],
    # node_modules is excluded from scanning but installed once — never delete it.
    clean_paths=["node_modules/.cache", "out", ".build"],
    clean_globs=["*.tsbuildinfo"],
)


def _node_major() -> int | None:
    out = subprocess.run(["node", "-v"], capture_output=True, text=True)
    try:
        return int(out.stdout.strip().lstrip("v").split(".")[0])
    except (ValueError, IndexError):
        return None


def _ensure_required_node() -> None:
    """Put a Node {REQUIRED_NODE_MAJOR}.x on PATH so install + build use it.

    vscode's native modules must be built and run with the pinned Node major.
    Prefer a Homebrew node@22 if present; skip cleanly if no match is available.
    """
    if _node_major() == REQUIRED_NODE_MAJOR:
        return
    prefix = subprocess.run(
        ["brew", "--prefix", f"node@{REQUIRED_NODE_MAJOR}"], capture_output=True, text=True
    ).stdout.strip()
    bindir = Path(prefix) / "bin" if prefix else None
    if bindir and (bindir / "node").exists():
        os.environ["PATH"] = f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"
    if _node_major() != REQUIRED_NODE_MAJOR:
        pytest.skip(
            f"vscode {REPO_TAG} requires Node {REQUIRED_NODE_MAJOR}.x — "
            f"install it (e.g. `brew install node@{REQUIRED_NODE_MAJOR}`)"
        )


@pytest.fixture(scope="session")
def vscode_repo():
    if shutil.which("npm") is None:
        pytest.skip("npm not installed")
    _ensure_required_node()
    if not (REPO_DIR / "package.json").exists():
        REPO_DIR.parent.mkdir(parents=True, exist_ok=True)
        if REPO_DIR.exists():
            shutil.rmtree(REPO_DIR, ignore_errors=True)
        subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", REPO_TAG, REPO_URL, str(REPO_DIR)],
            check=True,
        )
    if not (REPO_DIR / "node_modules").exists():
        # One-time dependency install — outside the timed phases.
        subprocess.run(["npm", "install"], cwd=REPO_DIR, check=True)
    return REPO_DIR


@pytest.mark.integration
@pytest.mark.slow
def test_vscode_profiles_compared_to_exclusions(vscode_repo, report, require_rtp, clean_mde):
    three_way_demo(vscode_repo, SCENARIO, report)
