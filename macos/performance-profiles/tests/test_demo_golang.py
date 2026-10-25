"""Live demo: MDE performance profiles vs. AV exclusions on a Go build.

Run it:
    pytest -m integration -s -k golang

Requires: sudo, real-time protection on, the `go` toolchain, and git. Uses a
repo-scale workload from golang/example to keep the timed window meaningful.

The google-golang profile covers the entire Go toolchain by signing ID
(go, compile, link, asm, vet, cover, cgo) — a clean, no-IDE story. Any other
process writing to the same directories is still fully monitored.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from demo_steps import Scenario, three_way_demo

EXAMPLE_REPO_URL = "https://github.com/golang/example.git"
EXAMPLE_REPO_DIR = Path.home() / "demo" / "golang-example-tests"

# Go writes most of its work to user-level caches, not the app dir, so the
# exclusion phase must cover those for an apples-to-apples comparison with the
# google-golang profile (which mutes the toolchain by signing ID wherever it
# writes). GOCACHE = build cache, GOMODCACHE = downloaded module cache.
GO_BUILD_CACHE = "~/Library/Caches/go-build"
GO_MOD_CACHE = "~/go/pkg"

SCENARIO = Scenario(
    name="golang",
    build_cmd=[
        "bash",
        "-lc",
        """
set -euo pipefail
git status --porcelain >/dev/null
echo "golang-example workload on commit $(git rev-parse --short HEAD)"

success=0
failed=0
total=0

while IFS= read -r pkg; do
    total=$((total+1))
    echo "golang-example building [$total]: $pkg"
    if python - "$pkg" <<'PY'
import subprocess
import sys

pkg = sys.argv[1]
cmd = ["go", "build", pkg]

try:
    completed = subprocess.run(cmd, timeout=120)
    raise SystemExit(completed.returncode)
except subprocess.TimeoutExpired:
    print(f"build timeout (120s): {pkg}", file=sys.stderr)
    raise SystemExit(124)
PY
    then
        success=$((success+1))
    else
        failed=$((failed+1))
    fi

    if (( total % 10 == 0 )); then
        echo "golang-example progress: total=$total success=$success failed=$failed"
    fi
done < <(go list ./... | sort)

echo "golang-example build summary: total=$total success=$success failed=$failed"
if [[ "$success" -lt 15 ]]; then
    echo "Too few successful packages built for a meaningful run (need >=15)." >&2
    exit 1
fi
""".strip(),
    ],
    eicar_subdir=".",
    profiles=["google-golang", "git"],
    exclusion_subdirs=["."],
    exclusion_abs_paths=[GO_BUILD_CACHE, GO_MOD_CACHE],
    pre_build=lambda app_dir: subprocess.run(
        ["go", "clean", "-cache", "-testcache"],
        cwd=app_dir,
        check=True,
        timeout=120,
    ),
)


def _clone_or_reclone(url: str, repo_dir: Path) -> None:
    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    if repo_dir.exists() and not (repo_dir / ".git").exists():
        shutil.rmtree(repo_dir, ignore_errors=True)
    if (repo_dir / ".git").exists():
        return
    subprocess.run(["git", "clone", "--depth", "1", url, str(repo_dir)], check=True, timeout=600)


def _ensure_example_checked_out() -> None:
    _clone_or_reclone(EXAMPLE_REPO_URL, EXAMPLE_REPO_DIR)
    subprocess.run(["git", "fetch", "--depth", "1", "origin", "master"], cwd=EXAMPLE_REPO_DIR, check=False)
    subprocess.run(["git", "checkout", "--force", "master"], cwd=EXAMPLE_REPO_DIR, check=True, timeout=120)


@pytest.fixture(scope="session")
def golang_app():
    if shutil.which("go") is None:
        pytest.fail(
            "\n".join(
                [
                    "Go toolchain is required for the golang performance-profile demo.",
                    "Install Go, then re-run:",
                    "  1) brew install go",
                    "  2) go version",
                    "  3) sudo -v && python -m pytest -m integration -s -k golang",
                ]
            ),
            pytrace=False,
        )
    if shutil.which("git") is None:
        pytest.fail(
            "\n".join(
                [
                    "git is required for the golang performance-profile demo.",
                    "Install git, then re-run:",
                    "  1) brew install git",
                    "  2) git --version",
                    "  3) sudo -v && python -m pytest -m integration -s -k golang",
                ]
            ),
            pytrace=False,
        )
    _ensure_example_checked_out()
    if not (EXAMPLE_REPO_DIR / "go.mod").exists():
        pytest.fail(
            "\n".join(
                [
                    f"Required Go example repo content is missing: {EXAMPLE_REPO_DIR}/go.mod",
                    "Ensure repository clone completed successfully, then re-run:",
                    "  sudo -v && python -m pytest -m integration -s -k golang",
                ]
            ),
            pytrace=False,
        )
    return EXAMPLE_REPO_DIR


@pytest.mark.integration
@pytest.mark.slow
def test_golang_profiles_compared_to_exclusions(golang_app, report, require_rtp, clean_mde):
    three_way_demo(golang_app, SCENARIO, report)
