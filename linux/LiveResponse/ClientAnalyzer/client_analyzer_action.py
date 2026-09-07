#!/usr/bin/env python3

import hashlib
import io
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
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath


STATE_PARENT = Path("/var/tmp")
ALLOWED_DOWNLOAD_SCHEMES = {"https"}
MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 1024
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_BYTES = 128 * 1024 * 1024
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


class ActionError(Exception):
    pass


class RestrictedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        if urllib.parse.urlsplit(new_url).scheme.lower() not in ALLOWED_DOWNLOAD_SCHEMES:
            raise ActionError("Download redirect used a disallowed URL scheme.")
        return super().redirect_request(
            request,
            file_pointer,
            code,
            message,
            headers,
            new_url,
        )


def validate_state_parent():
    parent_stat = os.lstat(STATE_PARENT)
    if not stat.S_ISDIR(parent_stat.st_mode):
        raise ActionError(f"State parent is not a directory: {STATE_PARENT}")

    mode = stat.S_IMODE(parent_stat.st_mode)
    euid = os.geteuid()
    private_parent = parent_stat.st_uid == euid and mode & 0o022 == 0
    sticky_shared_parent = (
        parent_stat.st_uid == 0
        and mode & stat.S_ISVTX != 0
        and mode & 0o002 != 0
    )
    if not private_parent and not sticky_shared_parent:
        raise ActionError(f"State parent is not trusted: {STATE_PARENT}")


def create_private_directory(parent, prefix):
    for _ in range(10):
        directory = parent / (prefix + secrets.token_hex(16))
        try:
            os.mkdir(directory, 0o700)
        except FileExistsError:
            continue
        validate_directory(directory)
        return directory
    raise ActionError("Failed to allocate a unique private directory.")


def validate_directory(path):
    directory_stat = os.lstat(path)
    if (
        not stat.S_ISDIR(directory_stat.st_mode)
        or directory_stat.st_uid != os.geteuid()
        or stat.S_IMODE(directory_stat.st_mode) != 0o700
    ):
        raise ActionError(f"Directory is not private: {path}")


def validate_regular_file(path, expected_mode):
    file_stat = os.lstat(path)
    if (
        not stat.S_ISREG(file_stat.st_mode)
        or file_stat.st_uid != os.geteuid()
        or file_stat.st_nlink != 1
        or stat.S_IMODE(file_stat.st_mode) != expected_mode
    ):
        raise ActionError(f"File is not private and regular: {path}")


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(url, destination):
    if urllib.parse.urlsplit(url).scheme.lower() not in ALLOWED_DOWNLOAD_SCHEMES:
        raise ActionError("Download URL used a disallowed URL scheme.")

    opener = urllib.request.build_opener(RestrictedRedirectHandler())
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "mdatp-xplat-client-analyzer"},
    )
    with opener.open(request, timeout=120) as response:
        if (
            urllib.parse.urlsplit(response.geturl()).scheme.lower()
            not in ALLOWED_DOWNLOAD_SCHEMES
        ):
            raise ActionError("Download resolved to a disallowed URL scheme.")

        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_DOWNLOAD_BYTES:
            raise ActionError("Download exceeded the maximum allowed size.")

        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        file_descriptor = os.open(destination, flags, 0o600)
        total = 0
        with os.fdopen(file_descriptor, "wb") as output:
            while True:
                chunk = response.read(CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    raise ActionError("Download exceeded the maximum allowed size.")
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())


def normalized_members(archive):
    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_MEMBERS:
        raise ActionError("Archive contains too many entries.")

    records = []
    names = set()
    expanded_bytes = 0
    for info in infos:
        name = info.filename
        trimmed_name = name[:-1] if name.endswith("/") else name
        if (
            not trimmed_name
            or name.startswith("/")
            or "\\" in name
            or PurePosixPath(name).is_absolute()
        ):
            raise ActionError(f"Archive contains an unsafe path: {name!r}")

        parts = trimmed_name.split("/")
        if any(part in ("", ".", "..") for part in parts):
            raise ActionError(f"Archive contains an unsafe path: {name!r}")

        normalized_name = "/".join(parts)
        if normalized_name in names:
            raise ActionError(f"Archive contains a duplicate path: {normalized_name}")
        names.add(normalized_name)

        if info.flag_bits & 0x1:
            raise ActionError(f"Archive contains an encrypted entry: {normalized_name}")
        if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise ActionError(f"Archive uses unsupported compression: {normalized_name}")
        if info.file_size > MAX_MEMBER_BYTES:
            raise ActionError(f"Archive entry is too large: {normalized_name}")

        expanded_bytes += info.file_size
        if expanded_bytes > MAX_EXPANDED_BYTES:
            raise ActionError("Archive expands beyond the maximum allowed size.")

        source_mode = info.external_attr >> 16
        file_type = stat.S_IFMT(source_mode)
        is_directory = info.is_dir()
        allowed_types = (0, stat.S_IFDIR) if is_directory else (0, stat.S_IFREG)
        if file_type not in allowed_types:
            raise ActionError(
                f"Archive contains a link or special file: {normalized_name}"
            )
        records.append((info, parts, normalized_name, is_directory, source_mode))

    file_names = {
        normalized_name
        for _, _, normalized_name, is_directory, _ in records
        if not is_directory
    }
    for file_name in file_names:
        if any(name.startswith(file_name + "/") for name in names):
            raise ActionError(f"Archive uses a file as a directory: {file_name}")
    return records


def extract_archive(archive, destination):
    records = normalized_members(archive)
    os.mkdir(destination, 0o700)
    archive.extractall(destination)
    for _, parts, normalized_name, is_directory, source_mode in records:
        output_path = destination.joinpath(*parts)
        output_stat = os.lstat(output_path)
        expected_type = stat.S_IFDIR if is_directory else stat.S_IFREG
        if (
            stat.S_IFMT(output_stat.st_mode) != expected_type
            or output_stat.st_uid != os.geteuid()
        ):
            raise ActionError(f"Archive entry was extracted unsafely: {normalized_name}")
        os.chmod(
            output_path,
            0o700 if is_directory or source_mode & 0o111 else 0o600,
        )


def read_member(archive, member_name):
    matches = [
        info
        for info, _, normalized_name, is_directory, _ in normalized_members(archive)
        if normalized_name == member_name and not is_directory
    ]
    if len(matches) != 1:
        raise ActionError(f"Archive is missing required file: {member_name}")
    content = archive.read(matches[0])
    if len(content) > MAX_MEMBER_BYTES:
        raise ActionError(f"Archive entry is too large: {member_name}")
    return content


def resolve_architecture(kind, machine=None):
    if kind == "python":
        return "any", None
    machine = platform.machine().lower() if machine is None else machine
    architecture = ARCH_ALIASES.get(machine)
    if architecture is None:
        raise ActionError(f"Unsupported architecture: {machine or 'unknown'}")
    return architecture, CONFIGS["binary"]["archives"][architecture]


def entrypoint_sha256(kind, archive_info):
    if kind == "binary":
        return archive_info["entry_sha256"]
    return CONFIGS["python"]["entry_sha256"]


def validate_entrypoint(path, expected_sha256):
    entry_stat = os.lstat(path)
    if (
        not stat.S_ISREG(entry_stat.st_mode)
        or entry_stat.st_uid != os.geteuid()
        or entry_stat.st_nlink != 1
    ):
        raise ActionError("Client Analyzer entrypoint is not a private regular file.")
    if sha256_file(path) != expected_sha256:
        raise ActionError("Client Analyzer entrypoint failed integrity verification.")
    os.chmod(path, 0o700)


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


def load_completion_record(path):
    validate_regular_file(path, 0o600)
    if path.stat().st_size > 1024:
        raise ActionError("Client Analyzer completion record is unexpectedly large.")
    return path.read_text(encoding="utf-8")


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
    setup_directory = workspace / "setup"
    os.mkdir(setup_directory, 0o700)
    try:
        result = subprocess.run(
            [str(entrypoint)],
            cwd=str(payload),
            env=private_environment(setup_directory, python_action=True),
            check=False,
        )
    finally:
        if setup_directory.exists():
            shutil.rmtree(setup_directory)
    if result.returncode != 0:
        raise ActionError(
            f"Client Analyzer dependency preparation failed with exit code {result.returncode}."
        )
    if sha256_file(entrypoint) != CONFIGS["python"]["entry_sha256"]:
        raise ActionError("Client Analyzer entrypoint changed during setup.")


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
        if sha256_file(archive_path) != config["outer_sha256"]:
            raise ActionError("Client Analyzer archive failed integrity verification.")

        payload = workspace / "payload"
        if kind == "binary":
            with zipfile.ZipFile(archive_path, "r") as outer_archive:
                inner_content = read_member(outer_archive, archive_info["inner_name"])
            if hashlib.sha256(inner_content).hexdigest() != archive_info["inner_sha256"]:
                raise ActionError(
                    "Architecture-specific Client Analyzer archive failed integrity verification."
                )
            with zipfile.ZipFile(io.BytesIO(inner_content), "r") as inner_archive:
                extract_archive(inner_archive, payload)
        else:
            with zipfile.ZipFile(archive_path, "r") as archive:
                extract_archive(archive, payload)

        entrypoint = payload / config["entrypoint"]
        validate_entrypoint(
            entrypoint,
            entrypoint_sha256(kind, archive_info),
        )
        archive_path.unlink()
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
    runs_directory = workspace / "runs"
    try:
        os.mkdir(runs_directory, 0o700)
    except FileExistsError:
        validate_directory(runs_directory)
    return create_private_directory(runs_directory, "run-")


def run(kind, workspace_id):
    config = CONFIGS[kind]
    if (
        re.fullmatch(
            re.escape(config["workspace_prefix"]) + r"[0-9a-f]{32}",
            workspace_id,
        )
        is None
    ):
        raise ActionError("Invalid Client Analyzer workspace ID.")

    validate_state_parent()
    workspace = STATE_PARENT / workspace_id
    validate_directory(workspace)
    payload = workspace / "payload"
    validate_directory(payload)
    architecture, archive_info = resolve_architecture(kind)
    if (
        load_completion_record(workspace / "complete")
        != completion_record(kind, architecture, workspace_id, archive_info)
    ):
        raise ActionError("Client Analyzer completion record failed validation.")

    entrypoint = payload / config["entrypoint"]
    validate_regular_file(entrypoint, 0o700)
    if sha256_file(entrypoint) != entrypoint_sha256(kind, archive_info):
        raise ActionError("Client Analyzer entrypoint failed integrity verification.")

    run_directory = create_run_directory(workspace)
    print(f"Client Analyzer run directory: {run_directory}", flush=True)
    os.chdir(payload)
    os.execve(
        entrypoint,
        [str(entrypoint), "--bypass-disclaimer", "-d"],
        private_environment(run_directory, python_action=kind == "python"),
    )


def handle_termination(signal_number, _frame):
    raise ActionError(f"Installation interrupted by signal {signal_number}.")


def main(arguments):
    if not arguments:
        raise ActionError("Missing Client Analyzer action.")

    command = arguments[0]
    if command in ("install-binary", "install-python"):
        if len(arguments) != 1:
            raise ActionError("Install actions do not accept parameters.")
        install(command[len("install-"):])
        return

    if command in ("run-binary", "run-python"):
        if len(arguments) != 2:
            raise ActionError("Pass exactly one workspace ID from the installer output.")
        run(command[len("run-"):], arguments[1])
        return

    raise ActionError(f"Unknown Client Analyzer action: {command}")


def cli():
    signal.signal(signal.SIGHUP, handle_termination)
    signal.signal(signal.SIGTERM, handle_termination)
    try:
        main(sys.argv[1:])
    except ActionError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except (OSError, ValueError, urllib.error.URLError, zipfile.BadZipFile) as error:
        print(f"ERROR: Client Analyzer action failed: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(cli())
