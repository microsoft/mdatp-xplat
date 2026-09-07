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
import pwd
import re
import secrets
import stat
import sys
from pathlib import Path


OUTER_SHA256 = "0b7c350a1c19e049416b1c8fb7ed857569ddcc32fb90453a3fccd083487c0b4e"
ENTRYPOINT_SHA256 = "00a03ca9b9f9c6d985ef48f8bcaae5cd08b37af551a452d005847d612fb67ffe"
STATE_PARENT = Path("/var/tmp")
WORKSPACE_PREFIX = "mde-client-analyzer-python-"
CHUNK_BYTES = 1024 * 1024
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
    "PYTHONNOUSERSITE",
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
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
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

    manifest = load_manifest(workspace / "manifest.json")
    expected_manifest = {
        "architecture": "any",
        "artifact_sha256": OUTER_SHA256,
        "entrypoint": "payload/mde_support_tool.sh",
        "entrypoint_sha256": ENTRYPOINT_SHA256,
        "format_version": 1,
        "kind": "python",
        "workspace_id": workspace_id,
    }
    if manifest != expected_manifest:
        raise RunError("Client Analyzer manifest failed validation.")

    entrypoint = payload / "mde_support_tool.sh"
    validate_regular_file(entrypoint, 0o700)
    if sha256_file(entrypoint) != ENTRYPOINT_SHA256:
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
