#!/bin/sh
set -eu

umask 077
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 is required to install Client Analyzer safely." >&2
    exit 1
fi

exec python3 - "$@" <<'PY'
import hashlib
import io
import json
import os
import platform
import secrets
import signal
import shutil
import stat
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath


DOWNLOAD_URL = "https://go.microsoft.com/fwlink/?linkid=2336125"
OUTER_SHA256 = "5f906591d33d675f14d73d5b658a796cec7480b023b18d45c5d687713a4d4fbb"
STATE_PARENT = Path("/var/tmp")
WORKSPACE_PREFIX = "mde-client-analyzer-binary-"
ALLOWED_DOWNLOAD_SCHEMES = {"https"}
MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 1024
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_BYTES = 128 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
ARCHIVES = {
    "x86_64": {
        "architecture": "amd64",
        "inner_name": "SupportToolLinuxamd64Binary.zip",
        "inner_sha256": "a500c00fe0dc2bb5b23ec9c771fd40694d111fa78d095d6ff77e4f0b36a23903",
        "entry_sha256": "b6b21fbc12b6d37be331a5e27a9741b43d35876645e02b26c8cafc4e623ed5e1",
    },
    "amd64": {
        "architecture": "amd64",
        "inner_name": "SupportToolLinuxamd64Binary.zip",
        "inner_sha256": "a500c00fe0dc2bb5b23ec9c771fd40694d111fa78d095d6ff77e4f0b36a23903",
        "entry_sha256": "b6b21fbc12b6d37be331a5e27a9741b43d35876645e02b26c8cafc4e623ed5e1",
    },
    "aarch64": {
        "architecture": "arm64",
        "inner_name": "SupportToolLinuxarm64Binary.zip",
        "inner_sha256": "ba8cc0c9766f5c937a90db00af6ed936ecdbfbba88049a383df814203af5066a",
        "entry_sha256": "a3b60a11eea093f9ec7b9bd7ea86a0e8bbc6f481116311dd678d69def49b5169",
    },
    "arm64": {
        "architecture": "arm64",
        "inner_name": "SupportToolLinuxarm64Binary.zip",
        "inner_sha256": "ba8cc0c9766f5c937a90db00af6ed936ecdbfbba88049a383df814203af5066a",
        "entry_sha256": "a3b60a11eea093f9ec7b9bd7ea86a0e8bbc6f481116311dd678d69def49b5169",
    },
}


class InstallError(Exception):
    pass


class RestrictedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        if urllib.parse.urlsplit(new_url).scheme.lower() not in ALLOWED_DOWNLOAD_SCHEMES:
            raise InstallError("Download redirect used a disallowed URL scheme.")
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
        raise InstallError(f"State parent is not a directory: {STATE_PARENT}")

    mode = stat.S_IMODE(parent_stat.st_mode)
    euid = os.geteuid()
    private_parent = parent_stat.st_uid == euid and mode & 0o022 == 0
    sticky_shared_parent = (
        parent_stat.st_uid == 0
        and mode & stat.S_ISVTX != 0
        and mode & 0o002 != 0
    )
    if not private_parent and not sticky_shared_parent:
        raise InstallError(f"State parent is not trusted: {STATE_PARENT}")


def create_workspace():
    for _ in range(10):
        token = WORKSPACE_PREFIX + secrets.token_hex(16)
        workspace = STATE_PARENT / token
        try:
            os.mkdir(workspace, 0o700)
        except FileExistsError:
            continue
        workspace_stat = os.lstat(workspace)
        if (
            not stat.S_ISDIR(workspace_stat.st_mode)
            or workspace_stat.st_uid != os.geteuid()
            or stat.S_IMODE(workspace_stat.st_mode) != 0o700
        ):
            raise InstallError("Failed to create a private workspace.")
        return workspace
    raise InstallError("Failed to allocate a unique private workspace.")


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while True:
            chunk = source.read(CHUNK_BYTES)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)


def sha256_bytes(content):
    return hashlib.sha256(content).hexdigest()


def download_file(destination):
    scheme = urllib.parse.urlsplit(DOWNLOAD_URL).scheme.lower()
    if scheme not in ALLOWED_DOWNLOAD_SCHEMES:
        raise InstallError("Download URL used a disallowed URL scheme.")

    opener = urllib.request.build_opener(RestrictedRedirectHandler())
    request = urllib.request.Request(
        DOWNLOAD_URL,
        headers={"User-Agent": "mdatp-xplat-client-analyzer"},
    )
    with opener.open(request, timeout=120) as response:
        final_scheme = urllib.parse.urlsplit(response.geturl()).scheme.lower()
        if final_scheme not in ALLOWED_DOWNLOAD_SCHEMES:
            raise InstallError("Download resolved to a disallowed URL scheme.")

        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_DOWNLOAD_BYTES:
            raise InstallError("Download exceeded the maximum allowed size.")

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
                    raise InstallError("Download exceeded the maximum allowed size.")
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())


def normalized_members(archive):
    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_MEMBERS:
        raise InstallError("Archive contains too many entries.")

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
            raise InstallError(f"Archive contains an unsafe path: {name!r}")

        parts = trimmed_name.split("/")
        if any(part in ("", ".", "..") for part in parts):
            raise InstallError(f"Archive contains an unsafe path: {name!r}")

        normalized_name = "/".join(parts)
        if normalized_name in names:
            raise InstallError(f"Archive contains a duplicate path: {normalized_name}")
        names.add(normalized_name)

        if info.flag_bits & 0x1:
            raise InstallError(f"Archive contains an encrypted entry: {normalized_name}")
        if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise InstallError(
                f"Archive uses unsupported compression: {normalized_name}"
            )
        if info.file_size > MAX_MEMBER_BYTES:
            raise InstallError(f"Archive entry is too large: {normalized_name}")

        expanded_bytes += info.file_size
        if expanded_bytes > MAX_EXPANDED_BYTES:
            raise InstallError("Archive expands beyond the maximum allowed size.")

        source_mode = info.external_attr >> 16
        file_type = stat.S_IFMT(source_mode)
        is_directory = info.is_dir()
        allowed_types = (0, stat.S_IFDIR) if is_directory else (0, stat.S_IFREG)
        if file_type not in allowed_types:
            raise InstallError(
                f"Archive contains a link or special file: {normalized_name}"
            )

        records.append((info, parts, normalized_name, is_directory, source_mode))

    file_names = {
        normalized_name
        for _, _, normalized_name, is_directory, _ in records
        if not is_directory
    }
    for file_name in file_names:
        prefix = file_name + "/"
        if any(name.startswith(prefix) for name in names):
            raise InstallError(f"Archive uses a file as a directory: {file_name}")

    return records


def ensure_directory(root, parts):
    current = root
    for part in parts:
        current = current / part
        try:
            os.mkdir(current, 0o700)
        except FileExistsError:
            current_stat = os.lstat(current)
            if (
                not stat.S_ISDIR(current_stat.st_mode)
                or current_stat.st_uid != os.geteuid()
                or stat.S_IMODE(current_stat.st_mode) != 0o700
            ):
                raise InstallError(f"Unsafe extraction directory: {current}")
    return current


def extract_archive(archive, destination):
    records = normalized_members(archive)
    os.mkdir(destination, 0o700)

    for _, parts, _, is_directory, _ in sorted(
        records,
        key=lambda record: (not record[3], len(record[1])),
    ):
        if is_directory:
            ensure_directory(destination, parts)

    for info, parts, normalized_name, is_directory, source_mode in records:
        if is_directory:
            continue

        parent = ensure_directory(destination, parts[:-1])
        output_path = parent / parts[-1]
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        file_descriptor = os.open(output_path, flags, 0o600)
        written = 0
        with archive.open(info, "r") as source, os.fdopen(
            file_descriptor,
            "wb",
        ) as output:
            while True:
                chunk = source.read(CHUNK_BYTES)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_MEMBER_BYTES:
                    raise InstallError(f"Archive entry is too large: {normalized_name}")
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())

        if written != info.file_size:
            raise InstallError(f"Archive entry size changed: {normalized_name}")

        output_mode = 0o700 if source_mode & 0o111 else 0o600
        os.chmod(output_path, output_mode)


def read_member(archive, member_name):
    records = normalized_members(archive)
    matches = [
        info
        for info, _, normalized_name, is_directory, _ in records
        if normalized_name == member_name and not is_directory
    ]
    if len(matches) != 1:
        raise InstallError(f"Archive is missing required file: {member_name}")
    content = archive.read(matches[0])
    if len(content) > MAX_MEMBER_BYTES:
        raise InstallError(f"Archive entry is too large: {member_name}")
    return content


def validate_entrypoint(path, expected_sha256):
    entry_stat = os.lstat(path)
    if (
        not stat.S_ISREG(entry_stat.st_mode)
        or entry_stat.st_uid != os.geteuid()
        or entry_stat.st_nlink != 1
    ):
        raise InstallError("Client Analyzer entrypoint is not a private regular file.")
    if sha256_file(path) != expected_sha256:
        raise InstallError("Client Analyzer entrypoint failed integrity verification.")
    os.chmod(path, 0o700)


def write_manifest(path, content):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    file_descriptor = os.open(path, flags, 0o600)
    with os.fdopen(file_descriptor, "w", encoding="utf-8") as output:
        json.dump(content, output, sort_keys=True)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())


def handle_termination(signal_number, _frame):
    raise InstallError(f"Installation interrupted by signal {signal_number}.")


def main():
    if len(sys.argv) != 1:
        raise InstallError("This installer does not accept parameters.")
    validate_state_parent()

    machine = platform.machine().lower()
    archive_info = ARCHIVES.get(machine)
    if archive_info is None:
        raise InstallError(f"Unsupported architecture: {machine or 'unknown'}")

    workspace = None
    completed = False
    try:
        workspace = create_workspace()
        outer_archive = workspace / "client-analyzer.zip"
        download_file(outer_archive)
        if sha256_file(outer_archive) != OUTER_SHA256:
            raise InstallError("Client Analyzer archive failed integrity verification.")

        with zipfile.ZipFile(outer_archive, "r") as outer_zip:
            inner_content = read_member(outer_zip, archive_info["inner_name"])
        if sha256_bytes(inner_content) != archive_info["inner_sha256"]:
            raise InstallError(
                "Architecture-specific Client Analyzer archive failed integrity verification."
            )

        payload = workspace / "payload"
        with zipfile.ZipFile(io.BytesIO(inner_content), "r") as inner_zip:
            extract_archive(inner_zip, payload)

        entrypoint = payload / "MDESupportTool"
        validate_entrypoint(entrypoint, archive_info["entry_sha256"])
        outer_archive.unlink()
        write_manifest(
            workspace / "manifest.json",
            {
                "architecture": archive_info["architecture"],
                "artifact_sha256": OUTER_SHA256,
                "entrypoint": "payload/MDESupportTool",
                "entrypoint_sha256": archive_info["entry_sha256"],
                "format_version": 1,
                "inner_sha256": archive_info["inner_sha256"],
                "kind": "binary",
                "workspace_id": workspace.name,
            },
        )
        completed = True
        print(f"Client Analyzer binary installed in private workspace: {workspace.name}")
        print(f"Run MDESupportTool.sh with workspace ID: {workspace.name}")
        return 0
    finally:
        if not completed and workspace is not None and workspace.exists():
            shutil.rmtree(workspace)


signal.signal(signal.SIGHUP, handle_termination)
signal.signal(signal.SIGTERM, handle_termination)

try:
    sys.exit(main())
except InstallError as error:
    print(f"ERROR: {error}", file=sys.stderr)
    sys.exit(1)
except (OSError, ValueError, urllib.error.URLError, zipfile.BadZipFile) as error:
    print(f"ERROR: Client Analyzer installation failed: {error}", file=sys.stderr)
    sys.exit(1)
except KeyboardInterrupt:
    sys.exit(130)
PY
