#!/usr/bin/env python3

import hashlib
import os
import platform
import pwd
import re
import secrets
import signal
import shutil
import stat
import subprocess
import sys
from pathlib import Path


STATE_PARENT = Path("/var/tmp")
CHUNK_BYTES = 1024 * 1024
ARCH_ALIASES = {
    "x86_64": "amd64",
    "amd64": "amd64",
    "aarch64": "arm64",
    "arm64": "arm64",
}
CONFIGS = {
    "binary": {
        "download_url": "https://go.microsoft.com/fwlink/?linkid=2336125",
        "outer_sha256": "5f906591d33d675f14d73d5b658a796cec7480b023b18d45c5d687713a4d4fbb",
        "workspace_prefix": "mde-client-analyzer-binary-",
        "entrypoint": "MDESupportTool",
        "archives": {
            "amd64": {
                "inner_name": "SupportToolLinuxamd64Binary.zip",
                "inner_sha256": "a500c00fe0dc2bb5b23ec9c771fd40694d111fa78d095d6ff77e4f0b36a23903",
                "entry_sha256": "b6b21fbc12b6d37be331a5e27a9741b43d35876645e02b26c8cafc4e623ed5e1",
            },
            "arm64": {
                "inner_name": "SupportToolLinuxarm64Binary.zip",
                "inner_sha256": "ba8cc0c9766f5c937a90db00af6ed936ecdbfbba88049a383df814203af5066a",
                "entry_sha256": "a3b60a11eea093f9ec7b9bd7ea86a0e8bbc6f481116311dd678d69def49b5169",
            },
        },
    },
    "python": {
        "download_url": "https://go.microsoft.com/fwlink/?linkid=2336046",
        "outer_sha256": "0b7c350a1c19e049416b1c8fb7ed857569ddcc32fb90453a3fccd083487c0b4e",
        "workspace_prefix": "mde-client-analyzer-python-",
        "entrypoint": "mde_support_tool.sh",
        "entry_sha256": "00a03ca9b9f9c6d985ef48f8bcaae5cd08b37af551a452d005847d612fb67ffe",
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
    "PYTHONNOUSERSITE",
    "PYTHONPATH",
    "VIRTUAL_ENV",
)


class HandoffError(Exception):
    pass


def validate_state_parent():
    parent_stat = os.lstat(STATE_PARENT)
    if not stat.S_ISDIR(parent_stat.st_mode):
        raise HandoffError(f"State parent is not a directory: {STATE_PARENT}")
    mode = stat.S_IMODE(parent_stat.st_mode)
    euid = os.geteuid()
    private_parent = parent_stat.st_uid == euid and mode & 0o022 == 0
    sticky_shared_parent = (
        parent_stat.st_uid == 0
        and mode & stat.S_ISVTX != 0
        and mode & 0o002 != 0
    )
    if not private_parent and not sticky_shared_parent:
        raise HandoffError(f"State parent is not trusted: {STATE_PARENT}")


def validate_directory(path):
    value = os.lstat(path)
    if (
        not stat.S_ISDIR(value.st_mode)
        or value.st_uid != os.geteuid()
        or stat.S_IMODE(value.st_mode) != 0o700
    ):
        raise HandoffError(f"Directory is not private: {path}")


def validate_file(path, expected_mode=None):
    value = os.lstat(path)
    if (
        not stat.S_ISREG(value.st_mode)
        or value.st_uid != os.geteuid()
        or value.st_nlink != 1
    ):
        raise HandoffError(f"File is not private and regular: {path}")
    if expected_mode is not None and stat.S_IMODE(value.st_mode) != expected_mode:
        raise HandoffError(f"File has unsafe permissions: {path}")


def create_private_directory(parent, prefix):
    for _ in range(10):
        path = parent / (prefix + secrets.token_hex(8))
        try:
            os.mkdir(path, 0o700)
        except FileExistsError:
            continue
        validate_directory(path)
        return path
    raise HandoffError("Failed to allocate a unique private directory.")


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256(path, expected, label):
    if sha256_file(path) != expected:
        raise HandoffError(f"{label} failed integrity verification.")


def run_tool(arguments, label, **kwargs):
    result = subprocess.run(arguments, check=False, **kwargs)
    if result.returncode != 0:
        raise HandoffError(f"{label} failed with exit code {result.returncode}.")


def download_file(url, destination):
    run_tool(
        [
            "curl",
            "-q",
            "--fail",
            "--silent",
            "--show-error",
            "--location",
            "--proto",
            "=https",
            "--proto-redir",
            "=https",
            "--max-redirs",
            "5",
            "--connect-timeout",
            "30",
            "--max-time",
            "180",
            "--max-filesize",
            "67108864",
            "--output",
            str(destination),
            url,
        ],
        "Client Analyzer download",
    )
    validate_file(destination, 0o600)


def normalize_payload(payload):
    for root, directories, files in os.walk(payload, followlinks=False):
        root_path = Path(root)
        validate_directory(root_path)
        for name in directories:
            path = root_path / name
            if path.is_symlink():
                raise HandoffError(f"Archive contains a link: {path}")
            os.chmod(path, 0o700)
        for name in files:
            path = root_path / name
            validate_file(path)
            current_mode = stat.S_IMODE(os.lstat(path).st_mode)
            os.chmod(path, 0o700 if current_mode & 0o111 else 0o600)


def resolve_architecture(kind):
    if kind == "python":
        return "any", None
    machine = platform.machine().lower()
    architecture = ARCH_ALIASES.get(machine)
    if architecture is None:
        raise HandoffError(f"Unsupported architecture: {machine or 'unknown'}")
    return architecture, CONFIGS["binary"]["archives"][architecture]


def entrypoint_sha256(kind, archive_info):
    if kind == "binary":
        return archive_info["entry_sha256"]
    return CONFIGS["python"]["entry_sha256"]


def extract_payload(kind, archive_path, payload, archive_info, workspace):
    os.mkdir(payload, 0o700)
    if kind == "binary":
        inner_archive = workspace / archive_info["inner_name"]
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        file_descriptor = os.open(inner_archive, flags, 0o600)
        with os.fdopen(file_descriptor, "wb") as output:
            run_tool(
                ["unzip", "-p", str(archive_path), archive_info["inner_name"]],
                "Architecture-specific archive extraction",
                stdout=output,
            )
        verify_sha256(
            inner_archive,
            archive_info["inner_sha256"],
            "Architecture-specific archive",
        )
        run_tool(
            ["unzip", "-tq", str(inner_archive)],
            "Archive validation",
            stdout=subprocess.DEVNULL,
        )
        run_tool(
            ["unzip", "-q", str(inner_archive), "-d", str(payload)],
            "Client Analyzer extraction",
        )
        inner_archive.unlink()
    else:
        run_tool(
            ["unzip", "-tq", str(archive_path)],
            "Archive validation",
            stdout=subprocess.DEVNULL,
        )
        run_tool(
            ["unzip", "-q", str(archive_path), "-d", str(payload)],
            "Client Analyzer extraction",
        )
    normalize_payload(payload)


def completion_record(kind, architecture, workspace_id, archive_info):
    config = CONFIGS[kind]
    inner_sha256 = archive_info["inner_sha256"] if archive_info else "-"
    return (
        " ".join(
            (
                "1",
                kind,
                architecture,
                config["outer_sha256"],
                inner_sha256,
                entrypoint_sha256(kind, archive_info),
                workspace_id,
            )
        )
        + "\n"
    )


def write_completion_record(path, content):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    file_descriptor = os.open(path, flags, 0o600)
    with os.fdopen(file_descriptor, "w", encoding="utf-8") as output:
        output.write(content)
        output.flush()
        os.fsync(output.fileno())


def private_environment(temp_directory, python_action=False):
    environment = os.environ.copy()
    for name in REMOVED_ENVIRONMENT_VARIABLES:
        environment.pop(name, None)
    environment["HOME"] = pwd.getpwuid(os.geteuid()).pw_dir
    environment["LANG"] = "C"
    environment["LC_ALL"] = "C"
    environment["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    environment["TMPDIR"] = str(temp_directory)
    if python_action:
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def prepare_python_dependencies(entrypoint, payload, workspace):
    setup_directory = create_private_directory(workspace, "setup-")
    try:
        run_tool(
            [str(entrypoint)],
            "Client Analyzer dependency preparation",
            cwd=str(payload),
            env=private_environment(setup_directory, python_action=True),
        )
    finally:
        if setup_directory.exists():
            shutil.rmtree(setup_directory)
    verify_sha256(
        entrypoint,
        CONFIGS["python"]["entry_sha256"],
        "Client Analyzer entrypoint",
    )


def install(kind):
    config = CONFIGS[kind]
    validate_state_parent()
    architecture, archive_info = resolve_architecture(kind)
    workspace = None
    completed = False
    try:
        workspace = create_private_directory(
            STATE_PARENT,
            config["workspace_prefix"],
        )
        archive_path = workspace / "client-analyzer.zip"
        download_file(config["download_url"], archive_path)
        verify_sha256(
            archive_path,
            config["outer_sha256"],
            "Client Analyzer archive",
        )

        payload = workspace / "payload"
        extract_payload(kind, archive_path, payload, archive_info, workspace)
        archive_path.unlink()

        entrypoint = payload / config["entrypoint"]
        validate_file(entrypoint)
        os.chmod(entrypoint, 0o700)
        verify_sha256(
            entrypoint,
            entrypoint_sha256(kind, archive_info),
            "Client Analyzer entrypoint",
        )
        if kind == "python":
            prepare_python_dependencies(entrypoint, payload, workspace)

        write_completion_record(
            workspace / "complete",
            completion_record(kind, architecture, workspace.name, archive_info),
        )
        completed = True
        print(f"Client Analyzer {kind} installed in private workspace: {workspace.name}")
        print(f"Run the matching support action with workspace ID: {workspace.name}")
    finally:
        if not completed and workspace is not None and workspace.exists():
            shutil.rmtree(workspace)


def create_run_directory(workspace):
    runs = workspace / "runs"
    try:
        os.mkdir(runs, 0o700)
    except FileExistsError:
        validate_directory(runs)
    return create_private_directory(runs, "run-")


def run(kind, workspace_id):
    config = CONFIGS[kind]
    if re.fullmatch(
        re.escape(config["workspace_prefix"]) + r"[0-9a-f]{16}",
        workspace_id,
    ) is None:
        raise HandoffError("Invalid Client Analyzer workspace ID.")

    validate_state_parent()
    workspace = STATE_PARENT / workspace_id
    validate_directory(workspace)
    payload = workspace / "payload"
    validate_directory(payload)
    architecture, archive_info = resolve_architecture(kind)

    completion = workspace / "complete"
    validate_file(completion, 0o600)
    if completion.read_text(encoding="utf-8") != completion_record(
        kind,
        architecture,
        workspace_id,
        archive_info,
    ):
        raise HandoffError("Client Analyzer completion record failed validation.")

    entrypoint = payload / config["entrypoint"]
    validate_file(entrypoint, 0o700)
    verify_sha256(
        entrypoint,
        entrypoint_sha256(kind, archive_info),
        "Client Analyzer entrypoint",
    )

    run_directory = create_run_directory(workspace)
    print(f"Client Analyzer run directory: {run_directory}", flush=True)
    os.chdir(payload)
    os.execve(
        entrypoint,
        [str(entrypoint), "--bypass-disclaimer", "-d"],
        private_environment(run_directory, python_action=kind == "python"),
    )


def handle_termination(signal_number, _frame):
    raise HandoffError(f"Installation interrupted by signal {signal_number}.")


def main(arguments):
    if not arguments:
        raise HandoffError("Missing Client Analyzer action.")
    command = arguments[0]
    if command in ("install-binary", "install-python"):
        if len(arguments) != 1:
            raise HandoffError("Install actions do not accept parameters.")
        install(command[len("install-"):])
        return
    if command in ("run-binary", "run-python"):
        if len(arguments) != 2:
            raise HandoffError("Pass exactly one workspace ID from the installer.")
        run(command[len("run-"):], arguments[1])
        return
    raise HandoffError(f"Unknown Client Analyzer action: {command}")


def cli():
    os.umask(0o077)
    signal.signal(signal.SIGHUP, handle_termination)
    signal.signal(signal.SIGTERM, handle_termination)
    try:
        main(sys.argv[1:])
    except HandoffError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as error:
        print(f"ERROR: Client Analyzer action failed: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(cli())
