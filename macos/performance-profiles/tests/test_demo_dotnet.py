"""Live demo: MDE performance profiles vs. AV exclusions on a .NET build.

Run it:
    pytest -m integration -s -k dotnet

Requires: sudo, real-time protection on, the dotnet CLI, and git.

Primary workload: PowerShell (large real-world repo) when compatible and healthy.
Fallback workload: dotnet/samples project that restores/builds with public feeds.

The dotnet-build profile is the most precisely targeted in the set: it uses an
argument-regex to mute only `dotnet build` and `dotnet restore` — not
`dotnet run` or `dotnet test`. Any other process writing to the same output
directories is still fully monitored.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from demo_steps import Scenario, three_way_demo

POWERSHELL_REPO_URL = "https://github.com/PowerShell/PowerShell.git"
POWERSHELL_REPO_DIR = Path.home() / "demo" / "powershell-tests"
POWERSHELL_PROJECT = "src/powershell-unix/powershell-unix.csproj"

SAMPLES_REPO_URL = "https://github.com/dotnet/samples.git"
SAMPLES_REPO_DIR = Path.home() / "demo" / "dotnet-samples-tests"
SAMPLES_SCOPE = "core"

# Ordered from newest to oldest. The first entry compatible with the installed
# SDK set is selected automatically.
POWERSHELL_TAG_CANDIDATES: list[dict[str, str]] = [
    {"tag": "v7.7.0-preview.2", "sdk": "11.0.100"},
    {"tag": "v7.7.0-preview.1", "sdk": "11.0.100"},
    {"tag": "v7.6.3", "sdk": "10.0.301"},
    {"tag": "v7.6.2", "sdk": "10.0.300"},
    {"tag": "v7.6.1", "sdk": "10.0.202"},
    {"tag": "v7.6.0", "sdk": "10.0.201"},
    {"tag": "v7.6.0-rc.1", "sdk": "10.0.102"},
    {"tag": "v7.6.0-preview.6", "sdk": "10.0.100"},
    {"tag": "v7.5.8", "sdk": "9.0.315"},
    {"tag": "v7.5.7", "sdk": "9.0.314"},
    {"tag": "v7.5.6", "sdk": "9.0.313"},
    {"tag": "v7.5.5", "sdk": "9.0.312"},
    {"tag": "v7.5.4", "sdk": "9.0.306"},
    {"tag": "v7.5.3", "sdk": "9.0.304"},
    {"tag": "v7.5.2", "sdk": "9.0.301"},
    {"tag": "v7.5.1", "sdk": "9.0.203"},
]


def _installed_dotnet_sdks() -> list[str]:
    result = subprocess.run(["dotnet", "--list-sdks"], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return []
    versions = []
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        versions.append(line.split(" ", 1)[0])
    return versions


def _sdk_triplet(version: str) -> tuple[int, int, int] | None:
    # Accepts values like 10.0.102, 10.0.100-preview.2, 9.0.315.
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)", version.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def _sdk_compatible(required: str, installed: str) -> bool:
    """Return True when an installed SDK can satisfy a required SDK version.

    Approximates SDK roll-forward behavior for pinned global.json entries:
    same major/minor, same feature band, and installed patch >= required patch.
    """
    req = _sdk_triplet(required)
    ins = _sdk_triplet(installed)
    if not req or not ins:
        return False
    if (req[0], req[1]) != (ins[0], ins[1]):
        return False
    if (req[2] // 100) != (ins[2] // 100):
        return False
    return ins[2] >= req[2]


def _select_powershell_tag(installed_sdks: list[str]) -> dict[str, str] | None:
    for candidate in POWERSHELL_TAG_CANDIDATES:
        if any(_sdk_compatible(candidate["sdk"], sdk) for sdk in installed_sdks):
            return candidate
    return None


def _required_sdk_from_global_json(repo_dir: Path) -> str | None:
    global_json = repo_dir / "global.json"
    if not global_json.exists():
        return None
    try:
        data = json.loads(global_json.read_text())
    except ValueError:
        return None
    return str(data.get("sdk", {}).get("version", "")).strip() or None


def _clone_or_reclone(url: str, repo_dir: Path, extra_args: list[str] | None = None) -> None:
    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    if repo_dir.exists() and not (repo_dir / ".git").exists():
        shutil.rmtree(repo_dir, ignore_errors=True)
    if (repo_dir / ".git").exists():
        return
    args = ["git", "clone"] + (extra_args or []) + [url, str(repo_dir)]
    subprocess.run(args, check=True, timeout=600)


def _ensure_powershell_checked_out(tag: str) -> None:
    # Use tag-targeted shallow clone/fetch to avoid huge global tag downloads.
    _clone_or_reclone(POWERSHELL_REPO_URL, POWERSHELL_REPO_DIR, ["--depth", "1", "--branch", tag])

    has_tag = subprocess.run(
        ["git", "show-ref", "--verify", f"refs/tags/{tag}"],
        cwd=POWERSHELL_REPO_DIR,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0
    if not has_tag:
        subprocess.run(
            ["git", "fetch", "--depth", "1", "origin", f"refs/tags/{tag}:refs/tags/{tag}"],
            cwd=POWERSHELL_REPO_DIR,
            check=True,
            timeout=300,
        )

    subprocess.run(["git", "checkout", "--force", tag], cwd=POWERSHELL_REPO_DIR, check=True, timeout=120)


def _ensure_samples_checked_out() -> None:
    _clone_or_reclone(SAMPLES_REPO_URL, SAMPLES_REPO_DIR, ["--depth", "1"])
    subprocess.run(["git", "fetch", "--depth", "1", "origin", "main"], cwd=SAMPLES_REPO_DIR, check=False)
    subprocess.run(["git", "checkout", "--force", "main"], cwd=SAMPLES_REPO_DIR, check=True, timeout=120)


def _powershell_nuget_config(repo_dir: Path) -> Path:
    cfg = repo_dir / ".mde-public-nuget.config"
    if not cfg.exists():
        cfg.write_text(
            """<?xml version=\"1.0\" encoding=\"utf-8\"?>
<configuration>
  <packageSources>
    <clear />
    <add key=\"nuget.org\" value=\"https://api.nuget.org/v3/index.json\" />
  </packageSources>
</configuration>
"""
        )
    return cfg


def _restore_powershell_for_phase(app_dir: Path) -> None:
    cfg = _powershell_nuget_config(app_dir)
    subprocess.run(
        [
            "dotnet",
            "restore",
            POWERSHELL_PROJECT,
            "--configfile",
            str(cfg),
            "/p:NuGetAudit=false",
        ],
        cwd=app_dir,
        check=True,
        timeout=300,
    )


def _can_use_powershell_repo(app_dir: Path) -> bool:
    # PowerShell build invokes git-describe. If this fails in the current checkout,
    # fallback to the public samples workload.
    desc_ok = subprocess.run(
        ["git", "describe", "--abbrev=60", "--long"],
        cwd=app_dir,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0
    if not desc_ok:
        return False

    try:
        _restore_powershell_for_phase(app_dir)
    except subprocess.SubprocessError:
        return False

    build_ok = subprocess.run(
        [
            "dotnet",
            "build",
            POWERSHELL_PROJECT,
            "-c",
            "Release",
            "-t:Rebuild",
            "--no-restore",
            "--disable-build-servers",
            "-p:UseSharedCompilation=false",
        ],
        cwd=app_dir,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=600,
    ).returncode == 0
    if not build_ok:
        return False

    return True


def _scenario_for_powershell() -> Scenario:
    return Scenario(
        name="dotnet",
        # Restore runs before each phase outside timed measurement. Timed work uses
        # Rebuild + disabled build servers/shared compilation to avoid near-no-op
        # incremental behavior.
        build_cmd=[
            "dotnet", "build", POWERSHELL_PROJECT, "-c", "Release", "-t:Rebuild",
            "--no-restore", "--disable-build-servers", "-p:UseSharedCompilation=false",
        ],
        eicar_subdir="src/powershell-unix",
        profiles=["dotnet-build", "git"],
        exclusion_subdirs=["src/powershell-unix"],
        # Keep cleanup targeted so we never delete repository content.
        clean_paths=["src/powershell-unix/bin", "src/powershell-unix/obj", "artifacts"],
        pre_build=_restore_powershell_for_phase,
    )


def _scenario_for_samples() -> Scenario:
    # Build many example projects for a realistic timed workload. Some projects
    # are platform-specific, so continue on failures and require a minimum number
    # of successful builds to keep the benchmark meaningful and deterministic.
    repo_build_cmd = """
set -euo pipefail
git status --porcelain >/dev/null
echo "samples-core workload on commit $(git rev-parse --short HEAD)"
success=0
failed=0
total=0
while IFS= read -r proj; do
    total=$((total+1))
    echo "samples-core building [$total]: $proj"
    if python - "$proj" <<'PY'
import subprocess
import sys

proj = sys.argv[1]
cmd = [
    "dotnet",
    "build",
    proj,
    "-c",
    "Release",
    "-t:Rebuild",
    "--disable-build-servers",
    "-p:UseSharedCompilation=false",
    "-v:minimal",
    "--nologo",
]

try:
    completed = subprocess.run(cmd, timeout=240)
    raise SystemExit(completed.returncode)
except subprocess.TimeoutExpired:
    print(f"build timeout (240s): {proj}", file=sys.stderr)
    raise SystemExit(124)
PY
    then
        success=$((success+1))
    else
        failed=$((failed+1))
    fi
    if (( total % 5 == 0 )); then
        echo "samples-core progress: total=$total success=$success failed=$failed"
    fi
done < <(find core -type f -name '*.csproj' | sort)
echo "samples-core build summary: total=$total success=$success failed=$failed"
if [[ "$success" -lt 20 ]]; then
    echo "Too few successful projects built for a meaningful run." >&2
    exit 1
fi
""".strip()

    return Scenario(
        name="dotnet",
        build_cmd=[
            "bash", "-lc", repo_build_cmd,
        ],
        eicar_subdir=SAMPLES_SCOPE,
        profiles=["dotnet-build", "git"],
        exclusion_subdirs=[SAMPLES_SCOPE],
        clean_paths=[
            f"{SAMPLES_SCOPE}/.mde-clean-placeholder",
        ],
        clean_globs=[
            f"{SAMPLES_SCOPE}/**/bin",
            f"{SAMPLES_SCOPE}/**/obj",
        ],
    )


def _choose_workload(installed_sdks: list[str]) -> tuple[Path, Scenario]:
    # Prefer the public samples workload for a stable, repo-scale benchmark.
    _ensure_samples_checked_out()
    return SAMPLES_REPO_DIR, _scenario_for_samples()


@pytest.fixture(scope="session")
def dotnet_app():
    if shutil.which("dotnet") is None:
        pytest.fail(
            "\n".join(
                [
                    "dotnet CLI is required for the dotnet performance-profile demo.",
                    "Install .NET SDK, then re-run:",
                    "  1) brew install --cask dotnet-sdk",
                    "  2) dotnet --list-sdks",
                    "  3) sudo -v && python -m pytest -m integration -s -k dotnet",
                ]
            ),
            pytrace=False,
        )
    if shutil.which("git") is None:
        pytest.fail(
            "\n".join(
                [
                    "git is required for the dotnet performance-profile demo.",
                    "Install git, then re-run:",
                    "  1) brew install git",
                    "  2) git --version",
                    "  3) sudo -v && python -m pytest -m integration -s -k dotnet",
                ]
            ),
            pytrace=False,
        )

    installed_sdks = _installed_dotnet_sdks()
    if not installed_sdks:
        pytest.fail(
            "\n".join(
                [
                    "No dotnet SDKs were found for the dotnet performance-profile demo.",
                    "Install a supported SDK, then re-run:",
                    "  1) brew install --cask dotnet-sdk",
                    "  2) dotnet --list-sdks",
                    "  3) sudo -v && python -m pytest -m integration -s -k dotnet",
                ]
            ),
            pytrace=False,
        )

    return _choose_workload(installed_sdks)


@pytest.mark.integration
@pytest.mark.slow
def test_dotnet_profiles_compared_to_exclusions(dotnet_app, report, require_rtp, clean_mde):
    app_dir, scenario = dotnet_app
    three_way_demo(app_dir, scenario, report)
