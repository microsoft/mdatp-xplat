#!/bin/sh
set -eu

umask 077
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 is required to run Client Analyzer safely." >&2
    exit 1
fi

exec python3 - "$@" <<'PY'
import hashlib
import json
import os
import platform
import pwd
import re
import secrets
import stat
import sys
from pathlib import Path


OUTER_SHA256 = "5f906591d33d675f14d73d5b658a796cec7480b023b18d45c5d687713a4d4fbb"
STATE_PARENT = Path("/var/tmp")
WORKSPACE_PREFIX = "mde-client-analyzer-binary-"
CHUNK_BYTES = 1024 * 1024
ARCHIVES = {
    "x86_64": {
        "architecture": "amd64",
        "inner_sha256": "a500c00fe0dc2bb5b23ec9c771fd40694d111fa78d095d6ff77e4f0b36a23903",
        "entry_sha256": "b6b21fbc12b6d37be331a5e27a9741b43d35876645e02b26c8cafc4e623ed5e1",
    },
    "amd64": {
        "architecture": "amd64",
        "inner_sha256": "a500c00fe0dc2bb5b23ec9c771fd40694d111fa78d095d6ff77e4f0b36a23903",
        "entry_sha256": "b6b21fbc12b6d37be331a5e27a9741b43d35876645e02b26c8cafc4e623ed5e1",
    },
    "aarch64": {
        "architecture": "arm64",
        "inner_sha256": "ba8cc0c9766f5c937a90db00af6ed936ecdbfbba88049a383df814203af5066a",
        "entry_sha256": "a3b60a11eea093f9ec7b9bd7ea86a0e8bbc6f481116311dd678d69def49b5169",
    },
    "arm64": {
        "architecture": "arm64",
        "inner_sha256": "ba8cc0c9766f5c937a90db00af6ed936ecdbfbba88049a383df814203af5066a",
        "entry_sha256": "a3b60a11eea093f9ec7b9bd7ea86a0e8bbc6f481116311dd678d69def49b5169",
    },
}
REMOVED_ENVIRONMENT_VARIABLES = (
    "BASH_ENV",
    "CDPATH",
    "ENV",
    "GLOBIGNORE",
    "LD_AUDIT",
    "LD_LIBRARY_PATH",
    "LD_PRELOAD",
    "PYTHON",
    "PYTHONHOME",
    "PYTHONPATH",
    "VIRTUAL_ENV",
)


class RunError(Exception):
    pass


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while True:
            chunk = source.read(CHUNK_BYTES)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)


def validate_state_parent():
    parent_stat = os.lstat(STATE_PARENT)
    if not stat.S_ISDIR(parent_stat.st_mode):
        raise RunError(f"State parent is not a directory: {STATE_PARENT}")

    mode = stat.S_IMODE(parent_stat.st_mode)
    euid = os.geteuid()
    private_parent = parent_stat.st_uid == euid and mode & 0o022 == 0
    sticky_shared_parent = (
        parent_stat.st_uid == 0
        and mode & stat.S_ISVTX != 0
        and mode & 0o002 != 0
    )
    if not private_parent and not sticky_shared_parent:
        raise RunError(f"State parent is not trusted: {STATE_PARENT}")


def validate_directory(path):
    directory_stat = os.lstat(path)
    if (
        not stat.S_ISDIR(directory_stat.st_mode)
        or directory_stat.st_uid != os.geteuid()
        or stat.S_IMODE(directory_stat.st_mode) != 0o700
    ):
        raise RunError(f"Directory is not private: {path}")


def validate_regular_file(path, expected_mode):
    file_stat = os.lstat(path)
    if (
        not stat.S_ISREG(file_stat.st_mode)
        or file_stat.st_uid != os.geteuid()
        or file_stat.st_nlink != 1
        or stat.S_IMODE(file_stat.st_mode) != expected_mode
    ):
        raise RunError(f"File is not private and regular: {path}")


def load_manifest(path):
    validate_regular_file(path, 0o600)
    if path.stat().st_size > 16 * 1024:
        raise RunError("Client Analyzer manifest is unexpectedly large.")
    with path.open("r", encoding="utf-8") as manifest_file:
        manifest = json.load(manifest_file)
    if not isinstance(manifest, dict):
        raise RunError("Client Analyzer manifest is invalid.")
    return manifest


def private_environment(temp_directory):
    environment = os.environ.copy()
    for name in REMOVED_ENVIRONMENT_VARIABLES:
        environment.pop(name, None)
    environment["HOME"] = pwd.getpwuid(os.geteuid()).pw_dir
    environment["LANG"] = "C"
    environment["LC_ALL"] = "C"
    environment["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    environment["TMPDIR"] = str(temp_directory)
    return environment


def create_run_directory(workspace):
    runs_directory = workspace / "runs"
    try:
        os.mkdir(runs_directory, 0o700)
    except FileExistsError:
        validate_directory(runs_directory)

    for _ in range(10):
        run_directory = runs_directory / ("run-" + secrets.token_hex(16))
        try:
            os.mkdir(run_directory, 0o700)
        except FileExistsError:
            continue
        return run_directory
    raise RunError("Failed to allocate a private run directory.")


def main():
    if len(sys.argv) != 2:
        raise RunError("Pass exactly one workspace ID from the installer output.")

    workspace_id = sys.argv[1]
    if re.fullmatch(WORKSPACE_PREFIX + r"[0-9a-f]{32}", workspace_id) is None:
        raise RunError("Invalid Client Analyzer workspace ID.")

    validate_state_parent()
    workspace = STATE_PARENT / workspace_id
    validate_directory(workspace)
    payload = workspace / "payload"
    validate_directory(payload)

    machine = platform.machine().lower()
    archive_info = ARCHIVES.get(machine)
    if archive_info is None:
        raise RunError(f"Unsupported architecture: {machine or 'unknown'}")

    manifest = load_manifest(workspace / "manifest.json")
    expected_manifest = {
        "architecture": archive_info["architecture"],
        "artifact_sha256": OUTER_SHA256,
        "entrypoint": "payload/MDESupportTool",
        "entrypoint_sha256": archive_info["entry_sha256"],
        "format_version": 1,
        "inner_sha256": archive_info["inner_sha256"],
        "kind": "binary",
        "workspace_id": workspace_id,
    }
    if manifest != expected_manifest:
        raise RunError("Client Analyzer manifest failed validation.")

    entrypoint = payload / "MDESupportTool"
    validate_regular_file(entrypoint, 0o700)
    if sha256_file(entrypoint) != archive_info["entry_sha256"]:
        raise RunError("Client Analyzer entrypoint failed integrity verification.")

    run_directory = create_run_directory(workspace)
    print(f"Client Analyzer run directory: {run_directory}", flush=True)
    os.chdir(payload)
    os.execve(
        entrypoint,
        [str(entrypoint), "--bypass-disclaimer", "-d"],
        private_environment(run_directory),
    )


try:
    main()
except RunError as error:
    print(f"ERROR: {error}", file=sys.stderr)
    sys.exit(1)
except (OSError, ValueError, json.JSONDecodeError) as error:
    print(f"ERROR: Client Analyzer execution failed: {error}", file=sys.stderr)
    sys.exit(1)
except KeyboardInterrupt:
    sys.exit(130)
PY
