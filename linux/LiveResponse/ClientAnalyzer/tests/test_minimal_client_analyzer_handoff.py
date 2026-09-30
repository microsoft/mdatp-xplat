import contextlib
import hashlib
import io
import os
import re
import signal
import stat
import subprocess
import tempfile
import types
import unittest
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from unittest import mock


CLIENT_ANALYZER_DIR = Path(__file__).resolve().parents[1]
PYTHON_INSTALLER_PATH = CLIENT_ANALYZER_DIR / "InstallXMDEPythonClientAnalyzer.sh"


def embedded_python_source(path=PYTHON_INSTALLER_PATH):
    source = path.read_text(encoding="utf-8")
    start = source.index("<<'PYTHON'\n") + len("<<'PYTHON'\n")
    end = source.rindex("\nPYTHON\n")
    return source[start:end]


ACTION = types.ModuleType("client_analyzer_handoff")
ACTION.__file__ = str(PYTHON_INSTALLER_PATH)
exec(compile(embedded_python_source(), str(PYTHON_INSTALLER_PATH), "exec"), ACTION.__dict__)

BINARY_URL = "https://go.microsoft.com/fwlink/?linkid=2336125"
BINARY_SHA256 = "5f906591d33d675f14d73d5b658a796cec7480b023b18d45c5d687713a4d4fbb"
BINARY_HASHES = {
    "amd64": {
        "machine": "x86_64",
        "inner_name": "SupportToolLinuxamd64Binary.zip",
        "inner_sha256": "a500c00fe0dc2bb5b23ec9c771fd40694d111fa78d095d6ff77e4f0b36a23903",
        "entry_sha256": "b6b21fbc12b6d37be331a5e27a9741b43d35876645e02b26c8cafc4e623ed5e1",
    },
    "arm64": {
        "machine": "aarch64",
        "inner_name": "SupportToolLinuxarm64Binary.zip",
        "inner_sha256": "ba8cc0c9766f5c937a90db00af6ed936ecdbfbba88049a383df814203af5066a",
        "entry_sha256": "a3b60a11eea093f9ec7b9bd7ea86a0e8bbc6f481116311dd678d69def49b5169",
    },
}
PYTHON_URL = "https://go.microsoft.com/fwlink/?linkid=2336046"
PYTHON_SHA256 = "0b7c350a1c19e049416b1c8fb7ed857569ddcc32fb90453a3fccd083487c0b4e"
PYTHON_ENTRY_SHA256 = (
    "00a03ca9b9f9c6d985ef48f8bcaae5cd08b37af551a452d005847d612fb67ffe"
)
WRAPPERS = {
    "InstallXMDEPythonClientAnalyzer.sh": "install-python",
    "MDEPythonSupportTool.sh": "run-python",
}
BINARY_WRAPPERS = {
    "InstallXMDEClientAnalyzer.sh": "install",
    "MDESupportTool.sh": "run",
}


def sha256_bytes(content):
    return hashlib.sha256(content).hexdigest()


def add_zip_file(archive, name, content, mode=0o600, file_type=stat.S_IFREG):
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (file_type | mode) << 16
    archive.writestr(info, content)


def add_zip_directory(archive, name, mode=0o775):
    info = zipfile.ZipInfo(f"{name.rstrip('/')}/")
    info.create_system = 3
    info.external_attr = (stat.S_IFDIR | mode) << 16
    archive.writestr(info, b"")


def binary_entrypoint():
    return b"#!/bin/sh\nexit 0\n"


def python_entrypoint(setup_exit_code=0):
    return f"#!/bin/sh\nexit {setup_exit_code}\n".encode("utf-8")


def python_user_site_entrypoint():
    return b"""#!/bin/sh
user_base="$PWD/.deps"
site_dir=$(PYTHONUSERBASE="$user_base" python3 -c 'import site; print(site.getusersitepackages())')
mkdir -p "$site_dir"
printf 'VALUE = 1\\n' > "$site_dir/workspace_dependency.py"
PYTHONUSERBASE="$user_base" python3 -c 'import workspace_dependency'
"""


def create_binary_archive(path, architecture):
    entrypoint = binary_entrypoint()
    inner_buffer = io.BytesIO()
    with zipfile.ZipFile(inner_buffer, "w") as inner_archive:
        add_zip_file(inner_archive, "MDESupportTool", entrypoint, mode=0o700)
    inner_content = inner_buffer.getvalue()
    with zipfile.ZipFile(path, "w") as outer_archive:
        add_zip_file(
            outer_archive,
            BINARY_HASHES[architecture]["inner_name"],
            inner_content,
        )
    return {
        "outer_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "inner_sha256": sha256_bytes(inner_content),
        "entry_sha256": sha256_bytes(entrypoint),
    }


def create_python_archive(path, entrypoint=None, nested_directory_modes=()):
    entrypoint = entrypoint if entrypoint is not None else python_entrypoint()
    with zipfile.ZipFile(path, "w") as archive:
        for name, mode in nested_directory_modes:
            add_zip_directory(archive, name, mode)
        add_zip_file(archive, "mde_support_tool.sh", entrypoint, mode=0o700)
    return {
        "outer_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "entry_sha256": sha256_bytes(entrypoint),
    }


class HandoffTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.state_parent = self.root / "state"
        self.state_parent.mkdir(mode=0o700)
        self.original_state_parent = ACTION.STATE_PARENT
        self.original_config = ACTION.CONFIG.copy()
        self.original_umask = os.umask(0o077)
        ACTION.STATE_PARENT = self.state_parent

    def tearDown(self):
        ACTION.STATE_PARENT = self.original_state_parent
        ACTION.CONFIG.clear()
        ACTION.CONFIG.update(self.original_config)
        os.umask(self.original_umask)
        self.temporary_directory.cleanup()

    def configure_python(self, archive, entrypoint=None):
        hashes = create_python_archive(archive, entrypoint)
        ACTION.CONFIG["download_url"] = str(archive)
        ACTION.CONFIG["outer_sha256"] = hashes["outer_sha256"]
        ACTION.CONFIG["entry_sha256"] = hashes["entry_sha256"]
        return hashes

    def copy_download(self, _url, destination):
        source = Path(ACTION.CONFIG["download_url"])
        shutil_copy(source, destination)

    def install(self):
        output = io.StringIO()
        with mock.patch.object(ACTION, "download_file", side_effect=self.copy_download):
            with contextlib.redirect_stdout(output):
                ACTION.install()
        prefix = ACTION.CONFIG["workspace_prefix"]
        match = re.search(
            rf"workspace ID: ({re.escape(prefix)}[0-9a-f]{{16}})",
            output.getvalue(),
        )
        self.assertIsNotNone(match, output.getvalue())
        return match.group(1)

    def run_without_exec(self, workspace_id):
        with mock.patch.object(ACTION.os, "chdir") as change_directory:
            with mock.patch.object(ACTION.os, "execve") as execute:
                ACTION.run(workspace_id)
        execute.assert_called_once()
        return change_directory, execute.call_args.args


def shutil_copy(source, destination):
    destination.write_bytes(source.read_bytes())
    destination.chmod(0o600)


class TestSourceAndWrappers(unittest.TestCase):
    def test_scripts_remove_legacy_paths(self):
        paths = [
            *(CLIENT_ANALYZER_DIR / name for name in WRAPPERS),
            *(CLIENT_ANALYZER_DIR / name for name in BINARY_WRAPPERS),
        ]
        for path in paths:
            with self.subTest(path=path.name):
                self.assertNotIn(
                    "/tmp/XMDEClientAnalyzer",
                    path.read_text(encoding="utf-8"),
                )

    def test_actions_are_self_contained(self):
        for name, command in WRAPPERS.items():
            with self.subTest(action=name):
                source = (CLIENT_ANALYZER_DIR / name).read_text(encoding="utf-8")
                self.assertIn(f"python3 - {command}", source)
                self.assertIn("<<'PYTHON'", source)
                self.assertNotIn("client_analyzer_handoff.py", source)
                self.assertNotIn('dirname -- "$0"', source)

        for name, command in BINARY_WRAPPERS.items():
            with self.subTest(action=name):
                source = (CLIENT_ANALYZER_DIR / name).read_text(encoding="utf-8")
                self.assertIn(f'{command} "$@"', source)
                self.assertNotIn("client_analyzer_binary_handoff.sh", source)
                self.assertNotIn("python3", source)
                self.assertNotIn('dirname -- "$0"', source)

    def test_actions_embed_current_artifact_pins(self):
        python_source = (
            CLIENT_ANALYZER_DIR / "InstallXMDEPythonClientAnalyzer.sh"
        ).read_text(encoding="utf-8")
        binary_source = (
            CLIENT_ANALYZER_DIR / "InstallXMDEClientAnalyzer.sh"
        ).read_text(encoding="utf-8")
        self.assertIn(PYTHON_URL, python_source)
        self.assertIn(PYTHON_SHA256, python_source)
        self.assertIn(BINARY_URL, binary_source)
        self.assertIn(BINARY_SHA256, binary_source)
        for values in BINARY_HASHES.values():
            self.assertIn(values["inner_sha256"], binary_source)
            self.assertIn(values["entry_sha256"], binary_source)

    def test_actions_reject_invalid_workspace_ids_via_stdin(self):
        installers = (
            "InstallXMDEClientAnalyzer.sh",
            "InstallXMDEPythonClientAnalyzer.sh",
        )
        for name in installers:
            with self.subTest(action=name):
                source = (CLIENT_ANALYZER_DIR / name).read_text(encoding="utf-8")
                result = subprocess.run(
                    ["/bin/sh", "-s", "../unexpected"],
                    input=source,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    "Install actions do not accept parameters", result.stderr
                )

        runners = ("MDESupportTool.sh", "MDEPythonSupportTool.sh")
        for name in runners:
            with self.subTest(action=name):
                source = (CLIENT_ANALYZER_DIR / name).read_text(encoding="utf-8")
                result = subprocess.run(
                    ["/bin/sh", "-s", "../unexpected"],
                    input=source,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Invalid Client Analyzer workspace ID", result.stderr)


class TestShellBinaryHandoff(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.state_parent = self.root / "state"
        self.state_parent.mkdir(mode=0o700)
        self.archive = self.root / "binary.zip"
        self.entrypoint = (
            b"#!/bin/sh\n"
            b"printf '%s\\n' \"$@\" > \"$TMPDIR/arguments\"\n"
        )
        self.hashes = self.create_archive()
        self.bin_directory = self.root / "bin"
        self.bin_directory.mkdir(mode=0o700)
        self.write_curl_stub()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def create_archive(self, unsafe_member=None):
        inner_buffer = io.BytesIO()
        with zipfile.ZipFile(inner_buffer, "w") as inner_archive:
            if unsafe_member is not None:
                add_zip_file(inner_archive, unsafe_member, b"unexpected")
            add_zip_file(inner_archive, "MDESupportTool", self.entrypoint, mode=0o700)
        inner_content = inner_buffer.getvalue()
        with zipfile.ZipFile(self.archive, "w") as outer_archive:
            add_zip_file(
                outer_archive,
                BINARY_HASHES["amd64"]["inner_name"],
                inner_content,
            )
        return {
            "outer_sha256": sha256_bytes(self.archive.read_bytes()),
            "inner_sha256": sha256_bytes(inner_content),
            "entry_sha256": sha256_bytes(self.entrypoint),
        }

    def write_curl_stub(self):
        curl = self.bin_directory / "curl"
        curl.write_text(
            "#!/bin/sh\n"
            "previous=\n"
            "for argument in \"$@\"; do\n"
            "    if [ \"$previous\" = --output ]; then\n"
            "        cp \"$TEST_ARCHIVE\" \"$argument\"\n"
            "        chmod 600 \"$argument\"\n"
            "        exit 0\n"
            "    fi\n"
            "    previous=$argument\n"
            "done\n"
            "exit 1\n",
            encoding="utf-8",
        )
        curl.chmod(0o700)

    def helper(self, **overrides):
        source = (CLIENT_ANALYZER_DIR / "InstallXMDEClientAnalyzer.sh").read_text(
            encoding="utf-8"
        )
        suffix = '\ninstall "$@"\n'
        self.assertTrue(source.endswith(suffix))
        source = source[: -len(suffix)]
        replacements = {
            "state_parent=/var/tmp": f"state_parent={self.state_parent}",
            "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin": (
                f"PATH={self.bin_directory}:/usr/local/sbin:/usr/local/bin:"
                "/usr/sbin:/usr/bin:/sbin:/bin"
            ),
            f"outer_sha256={BINARY_SHA256}": (
                f"outer_sha256={self.hashes['outer_sha256']}"
            ),
            f"amd64_inner_sha256={BINARY_HASHES['amd64']['inner_sha256']}": (
                f"amd64_inner_sha256={self.hashes['inner_sha256']}"
            ),
            f"amd64_entry_sha256={BINARY_HASHES['amd64']['entry_sha256']}": (
                f"amd64_entry_sha256={self.hashes['entry_sha256']}"
            ),
        }
        replacements.update(overrides)
        for old, new in replacements.items():
            self.assertIn(old, source)
            source = source.replace(old, new)
        source += (
            '\ncase "${1:-}" in\n'
            '    install) shift; install "$@" ;;\n'
            '    run) shift; run "$@" ;;\n'
            '    *) fail "Unsupported command." ;;\n'
            "esac\n"
        )
        helper = self.root / "client_analyzer_binary_handoff.sh"
        helper.write_text(source, encoding="utf-8")
        helper.chmod(0o700)
        return helper

    def invoke(self, helper, *arguments):
        return subprocess.run(
            ["/bin/sh", str(helper), *arguments],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "TEST_ARCHIVE": str(self.archive)},
            timeout=120,
        )

    def install(self, helper):
        result = self.invoke(helper, "install")
        self.assertEqual(result.returncode, 0, result.stderr)
        match = re.search(
            r"workspace ID: (mde-client-analyzer-binary-[0-9a-f]{16})",
            result.stdout,
        )
        self.assertIsNotNone(match, result.stdout)
        return match.group(1)

    def test_shell_helper_installs_and_runs_with_fixed_arguments(self):
        helper = self.helper()
        workspace_id = self.install(helper)
        result = self.invoke(helper, "run", workspace_id)
        self.assertEqual(result.returncode, 0, result.stderr)
        runs = self.state_parent / workspace_id / "runs"
        arguments = next(runs.glob("run-*/arguments"))
        self.assertEqual(
            arguments.read_text(encoding="utf-8").splitlines(),
            ["--bypass-disclaimer", "-d"],
        )

    def test_shell_helper_rejects_tampered_entrypoint(self):
        helper = self.helper()
        workspace_id = self.install(helper)
        entrypoint = self.state_parent / workspace_id / "payload/MDESupportTool"
        entrypoint.write_bytes(entrypoint.read_bytes() + b"\n")
        entrypoint.chmod(0o700)
        result = self.invoke(helper, "run", workspace_id)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("integrity verification", result.stderr)

    def test_shell_helper_rejects_invalid_token_and_completion_record(self):
        helper = self.helper()
        invalid_token = self.invoke(helper, "run", "../unexpected")
        self.assertNotEqual(invalid_token.returncode, 0)
        self.assertIn("Invalid Client Analyzer workspace ID", invalid_token.stderr)

        workspace_id = self.install(helper)
        completion = self.state_parent / workspace_id / "complete"
        completion.write_text("invalid\n", encoding="utf-8")
        completion.chmod(0o600)
        tampered_completion = self.invoke(helper, "run", workspace_id)
        self.assertNotEqual(tampered_completion.returncode, 0)
        self.assertIn("completion record", tampered_completion.stderr)

    def test_shell_helper_rejects_unsafe_archive_and_cleans_workspace(self):
        self.hashes = self.create_archive(unsafe_member="../escaped")
        helper = self.helper()
        result = self.invoke(helper, "install")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsafe member", result.stderr)
        self.assertEqual(
            list(self.state_parent.iterdir()),
            [],
            [path.name for path in self.state_parent.rglob("*")],
        )

    def test_shell_helper_rejects_archive_link_and_cleans_workspace(self):
        inner_buffer = io.BytesIO()
        with zipfile.ZipFile(inner_buffer, "w") as inner_archive:
            add_zip_file(
                inner_archive,
                "linked",
                b"MDESupportTool",
                file_type=stat.S_IFLNK,
            )
            add_zip_file(
                inner_archive,
                "MDESupportTool",
                self.entrypoint,
                mode=0o700,
            )
        inner_content = inner_buffer.getvalue()
        with zipfile.ZipFile(self.archive, "w") as outer_archive:
            add_zip_file(
                outer_archive,
                BINARY_HASHES["amd64"]["inner_name"],
                inner_content,
            )
        self.hashes = {
            "outer_sha256": sha256_bytes(self.archive.read_bytes()),
            "inner_sha256": sha256_bytes(inner_content),
            "entry_sha256": sha256_bytes(self.entrypoint),
        }
        helper = self.helper()
        result = self.invoke(helper, "install")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Archive contains a link", result.stderr)
        self.assertEqual(
            list(self.state_parent.iterdir()),
            [],
            [path.name for path in self.state_parent.rglob("*")],
        )

    def test_shell_helper_removes_nested_payload_after_failed_install(self):
        inner_buffer = io.BytesIO()
        with zipfile.ZipFile(inner_buffer, "w") as inner_archive:
            add_zip_file(inner_archive, "nested/manifest", b"missing entrypoint")
        inner_content = inner_buffer.getvalue()
        with zipfile.ZipFile(self.archive, "w") as outer_archive:
            add_zip_file(
                outer_archive,
                BINARY_HASHES["amd64"]["inner_name"],
                inner_content,
            )
        self.hashes = {
            "outer_sha256": sha256_bytes(self.archive.read_bytes()),
            "inner_sha256": sha256_bytes(inner_content),
            "entry_sha256": sha256_bytes(self.entrypoint),
        }
        helper = self.helper()
        result = self.invoke(helper, "install")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("File is not private and regular", result.stderr)
        self.assertEqual(
            list(self.state_parent.iterdir()),
            [],
            [path.name for path in self.state_parent.rglob("*")],
        )


class TestInstallerAndRunner(HandoffTestCase):
    def test_python_setup_and_run(self):
        archive = self.root / "python.zip"
        self.configure_python(archive)
        workspace_id = self.install()
        _, execute_arguments = self.run_without_exec(workspace_id)
        entrypoint, arguments, environment = execute_arguments
        self.assertEqual(arguments, [str(entrypoint), "--bypass-disclaimer", "-d"])
        self.assertEqual(environment["PYTHONDONTWRITEBYTECODE"], "1")

    def test_python_setup_ignores_python_no_user_site(self):
        archive = self.root / "python-user-site.zip"
        self.configure_python(archive, python_user_site_entrypoint())
        with mock.patch.dict(os.environ, {"PYTHONNOUSERSITE": "1"}):
            self.install()

    def test_python_setup_normalizes_published_directory_permissions(self):
        archive = self.root / "python-directory-modes.zip"
        hashes = create_python_archive(
            archive,
            nested_directory_modes=(
                ("mde_tools", 0o775),
                ("mde_tools/.deps", 0o775),
            ),
        )
        ACTION.CONFIG["download_url"] = str(archive)
        ACTION.CONFIG["outer_sha256"] = hashes["outer_sha256"]
        ACTION.CONFIG["entry_sha256"] = hashes["entry_sha256"]
        workspace_id = self.install()

        payload = self.state_parent / workspace_id / "payload"
        self.assertEqual(stat.S_IMODE((payload / "mde_tools").stat().st_mode), 0o700)
        self.assertEqual(
            stat.S_IMODE((payload / "mde_tools/.deps").stat().st_mode),
            0o700,
        )

    def test_digest_failure_removes_workspace(self):
        archive = self.root / "python.zip"
        self.configure_python(archive)
        ACTION.CONFIG["outer_sha256"] = "0" * 64
        with mock.patch.object(ACTION, "download_file", side_effect=self.copy_download):
            with self.assertRaisesRegex(ACTION.HandoffError, "integrity verification"):
                ACTION.install()
        self.assertEqual(list(self.state_parent.iterdir()), [])

    def test_setup_failure_removes_workspace(self):
        archive = self.root / "python.zip"
        self.configure_python(archive, python_entrypoint(7))
        with mock.patch.object(ACTION, "download_file", side_effect=self.copy_download):
            with self.assertRaisesRegex(ACTION.HandoffError, "exit code 7"):
                ACTION.install()
        self.assertEqual(list(self.state_parent.iterdir()), [])

    def test_termination_removes_workspace(self):
        previous_handler = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM, ACTION.handle_termination)
        try:
            with mock.patch.object(
                ACTION,
                "download_file",
                side_effect=lambda *_args: os.kill(os.getpid(), signal.SIGTERM),
            ):
                with self.assertRaisesRegex(ACTION.HandoffError, "interrupted"):
                    ACTION.install()
            self.assertEqual(list(self.state_parent.iterdir()), [])
        finally:
            signal.signal(signal.SIGTERM, previous_handler)

    def test_invalid_token_is_rejected(self):
        with self.assertRaisesRegex(ACTION.HandoffError, "Invalid"):
            ACTION.run("../unexpected")

    def test_completion_record_tampering_is_rejected(self):
        archive = self.root / "python.zip"
        self.configure_python(archive)
        workspace_id = self.install()
        completion = self.state_parent / workspace_id / "complete"
        completion.write_text("invalid\n", encoding="utf-8")
        completion.chmod(0o600)
        with self.assertRaisesRegex(ACTION.HandoffError, "completion record"):
            ACTION.run(workspace_id)

    def test_entrypoint_tampering_is_rejected(self):
        archive = self.root / "python.zip"
        self.configure_python(archive)
        workspace_id = self.install()
        entrypoint = self.state_parent / workspace_id / "payload/mde_support_tool.sh"
        entrypoint.write_bytes(entrypoint.read_bytes() + b"\n")
        with self.assertRaisesRegex(ACTION.HandoffError, "integrity verification"):
            ACTION.run(workspace_id)

    def test_archive_path_traversal_is_rejected_before_extraction(self):
        archive = self.root / "python.zip"
        create_python_archive(archive)
        with zipfile.ZipFile(archive, "a") as archive_file:
            add_zip_file(archive_file, "../escaped", b"unexpected")
        ACTION.CONFIG["download_url"] = str(archive)
        ACTION.CONFIG["outer_sha256"] = sha256_bytes(archive.read_bytes())
        with mock.patch.object(ACTION, "download_file", side_effect=self.copy_download):
            with self.assertRaisesRegex(ACTION.HandoffError, "unsafe member"):
                ACTION.install()
        self.assertEqual(list(self.state_parent.iterdir()), [])


class TestDownloadCommand(HandoffTestCase):
    def test_curl_is_https_only_and_bounded(self):
        captured = {}

        def fake_run(arguments, check, **_kwargs):
            captured["arguments"] = arguments
            output = Path(arguments[arguments.index("--output") + 1])
            output.write_bytes(b"content")
            output.chmod(0o600)
            return types.SimpleNamespace(returncode=0)

        with mock.patch.object(ACTION.subprocess, "run", side_effect=fake_run):
            ACTION.download_file("https://example.invalid/archive.zip", self.root / "a")

        arguments = captured["arguments"]
        for required in (
            "-q",
            "--fail",
            "--location",
            "--proto",
            "=https",
            "--proto-redir",
            "--max-filesize",
            "67108864",
        ):
            self.assertIn(required, arguments)


def audit_archive(archive):
    names = set()
    total = 0
    for info in archive.infolist():
        name = info.filename
        trimmed = name[:-1] if name.endswith("/") else name
        parts = trimmed.split("/")
        if (
            not trimmed
            or name.startswith("/")
            or "\\" in name
            or PurePosixPath(name).is_absolute()
            or any(part in ("", ".", "..") for part in parts)
        ):
            raise AssertionError(f"Unsafe archive path: {name}")
        normalized = "/".join(parts)
        if normalized in names:
            raise AssertionError(f"Duplicate archive path: {normalized}")
        names.add(normalized)
        file_type = stat.S_IFMT(info.external_attr >> 16)
        allowed = (0, stat.S_IFDIR) if info.is_dir() else (0, stat.S_IFREG)
        if file_type not in allowed:
            raise AssertionError(f"Link or special archive entry: {normalized}")
        total += info.file_size
    if len(names) > 1024 or total > 128 * 1024 * 1024:
        raise AssertionError("Archive exceeds reviewed limits.")


@unittest.skipUnless(
    os.environ.get("RUN_NETWORK_INTEGRITY_TESTS") == "1",
    "Set RUN_NETWORK_INTEGRITY_TESTS=1 to verify published artifacts.",
)
class TestPublishedArtifactIntegrity(unittest.TestCase):
    def download(self, url):
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "mdatp-xplat-client-analyzer-test"},
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            content = response.read(64 * 1024 * 1024 + 1)
        self.assertLessEqual(len(content), 64 * 1024 * 1024)
        return content

    def test_binary_artifact(self):
        content = self.download(BINARY_URL)
        self.assertEqual(sha256_bytes(content), BINARY_SHA256)
        with zipfile.ZipFile(io.BytesIO(content), "r") as outer_archive:
            audit_archive(outer_archive)
            for architecture, expected in BINARY_HASHES.items():
                with self.subTest(architecture=architecture):
                    inner_content = outer_archive.read(expected["inner_name"])
                    self.assertEqual(
                        sha256_bytes(inner_content),
                        expected["inner_sha256"],
                    )
                    with zipfile.ZipFile(
                        io.BytesIO(inner_content),
                        "r",
                    ) as inner_archive:
                        audit_archive(inner_archive)
                        self.assertEqual(
                            sha256_bytes(inner_archive.read("MDESupportTool")),
                            expected["entry_sha256"],
                        )

    def test_python_artifact(self):
        content = self.download(PYTHON_URL)
        self.assertEqual(sha256_bytes(content), PYTHON_SHA256)
        with zipfile.ZipFile(io.BytesIO(content), "r") as archive:
            audit_archive(archive)
            self.assertEqual(
                sha256_bytes(archive.read("mde_support_tool.sh")),
                PYTHON_ENTRY_SHA256,
            )


if __name__ == "__main__":
    unittest.main()
