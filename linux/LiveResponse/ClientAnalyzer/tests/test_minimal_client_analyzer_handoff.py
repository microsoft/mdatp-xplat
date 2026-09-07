import contextlib
import copy
import hashlib
import importlib.util
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
ACTION_PATH = CLIENT_ANALYZER_DIR / "client_analyzer_handoff.py"
SPEC = importlib.util.spec_from_file_location("client_analyzer_handoff", ACTION_PATH)
ACTION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ACTION)

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
    "InstallXMDEClientAnalyzer.sh": "install-binary",
    "InstallXMDEPythonClientAnalyzer.sh": "install-python",
    "MDESupportTool.sh": "run-binary",
    "MDEPythonSupportTool.sh": "run-python",
}


def sha256_bytes(content):
    return hashlib.sha256(content).hexdigest()


def add_zip_file(archive, name, content, mode=0o600, file_type=stat.S_IFREG):
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (file_type | mode) << 16
    archive.writestr(info, content)


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


def create_python_archive(path, entrypoint=None):
    entrypoint = entrypoint if entrypoint is not None else python_entrypoint()
    with zipfile.ZipFile(path, "w") as archive:
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
        self.original_configs = copy.deepcopy(ACTION.CONFIGS)
        self.original_umask = os.umask(0o077)
        ACTION.STATE_PARENT = self.state_parent
        self.machine_patcher = mock.patch.object(
            ACTION.platform,
            "machine",
            return_value="x86_64",
        )
        self.machine_patcher.start()

    def tearDown(self):
        self.machine_patcher.stop()
        ACTION.STATE_PARENT = self.original_state_parent
        ACTION.CONFIGS.clear()
        ACTION.CONFIGS.update(self.original_configs)
        os.umask(self.original_umask)
        self.temporary_directory.cleanup()

    def configure_binary(self, archive, architecture):
        hashes = create_binary_archive(archive, architecture)
        config = ACTION.CONFIGS["binary"]
        config["download_url"] = str(archive)
        config["outer_sha256"] = hashes["outer_sha256"]
        config["archives"][architecture]["inner_sha256"] = hashes["inner_sha256"]
        config["archives"][architecture]["entry_sha256"] = hashes["entry_sha256"]
        return hashes

    def configure_python(self, archive, entrypoint=None):
        hashes = create_python_archive(archive, entrypoint)
        config = ACTION.CONFIGS["python"]
        config["download_url"] = str(archive)
        config["outer_sha256"] = hashes["outer_sha256"]
        config["entry_sha256"] = hashes["entry_sha256"]
        return hashes

    def copy_download(self, _url, destination):
        source = Path(ACTION.CONFIGS[self.active_kind]["download_url"])
        shutil_copy(source, destination)

    def install(self, kind):
        self.active_kind = kind
        output = io.StringIO()
        with mock.patch.object(ACTION, "download_file", side_effect=self.copy_download):
            with contextlib.redirect_stdout(output):
                ACTION.install(kind)
        prefix = ACTION.CONFIGS[kind]["workspace_prefix"]
        match = re.search(
            rf"workspace ID: ({re.escape(prefix)}[0-9a-f]{{16}})",
            output.getvalue(),
        )
        self.assertIsNotNone(match, output.getvalue())
        return match.group(1)

    def run_without_exec(self, kind, workspace_id):
        with mock.patch.object(ACTION.os, "chdir") as change_directory:
            with mock.patch.object(ACTION.os, "execve") as execute:
                ACTION.run(kind, workspace_id)
        execute.assert_called_once()
        return change_directory, execute.call_args.args


def shutil_copy(source, destination):
    destination.write_bytes(source.read_bytes())
    destination.chmod(0o600)


class TestSourceAndWrappers(unittest.TestCase):
    def test_scripts_remove_legacy_paths(self):
        paths = [
            ACTION_PATH,
            *(CLIENT_ANALYZER_DIR / name for name in WRAPPERS),
        ]
        for path in paths:
            with self.subTest(path=path.name):
                self.assertNotIn(
                    "/tmp/XMDEClientAnalyzer",
                    path.read_text(encoding="utf-8"),
                )

    def test_wrappers_dispatch_to_package_local_helper(self):
        for name, command in WRAPPERS.items():
            with self.subTest(wrapper=name):
                source = (CLIENT_ANALYZER_DIR / name).read_text(encoding="utf-8")
                self.assertLessEqual(len(source.splitlines()), 16)
                self.assertIn("client_analyzer_handoff.py", source)
                self.assertIn(command, source)

    def test_helper_pins_current_artifacts(self):
        source = ACTION_PATH.read_text(encoding="utf-8")
        self.assertIn(BINARY_URL, source)
        self.assertIn(BINARY_SHA256, source)
        self.assertIn(PYTHON_URL, source)
        self.assertIn(PYTHON_SHA256, source)
        for values in BINARY_HASHES.values():
            self.assertIn(values["inner_sha256"], source)
            self.assertIn(values["entry_sha256"], source)

    def test_wrappers_pass_only_fixed_mode_and_user_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory)
            capture = package / "arguments.txt"
            helper = package / "client_analyzer_handoff.py"
            helper.write_text(
                "import os, sys\n"
                "open(os.environ['CAPTURE_FILE'], 'w').write('\\n'.join(sys.argv[1:]))\n",
                encoding="utf-8",
            )
            for name, command in WRAPPERS.items():
                wrapper = package / name
                wrapper.write_text(
                    (CLIENT_ANALYZER_DIR / name).read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
                arguments = ["workspace-token"] if command.startswith("run-") else []
                result = subprocess.run(
                    ["/bin/sh", str(wrapper), *arguments],
                    check=False,
                    capture_output=True,
                    text=True,
                    env={**os.environ, "CAPTURE_FILE": str(capture)},
                    timeout=120,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    capture.read_text(encoding="utf-8").splitlines(),
                    [command, *arguments],
                )


class TestInstallerAndRunner(HandoffTestCase):
    def test_binary_amd64_and_arm64(self):
        for architecture, machine in (("amd64", "x86_64"), ("arm64", "aarch64")):
            with self.subTest(architecture=architecture):
                archive = self.root / f"{architecture}.zip"
                self.configure_binary(archive, architecture)
                with mock.patch.object(ACTION.platform, "machine", return_value=machine):
                    workspace_id = self.install("binary")
                    _, execute_arguments = self.run_without_exec(
                        "binary",
                        workspace_id,
                    )
                entrypoint, arguments, environment = execute_arguments
                self.assertEqual(
                    arguments,
                    [str(entrypoint), "--bypass-disclaimer", "-d"],
                )
                self.assertRegex(environment["TMPDIR"], r"/runs/run-[0-9a-f]{16}$")

    def test_python_setup_and_run(self):
        archive = self.root / "python.zip"
        self.configure_python(archive)
        workspace_id = self.install("python")
        _, execute_arguments = self.run_without_exec("python", workspace_id)
        entrypoint, arguments, environment = execute_arguments
        self.assertEqual(arguments, [str(entrypoint), "--bypass-disclaimer", "-d"])
        self.assertEqual(environment["PYTHONDONTWRITEBYTECODE"], "1")

    def test_python_setup_ignores_python_no_user_site(self):
        archive = self.root / "python-user-site.zip"
        self.configure_python(archive, python_user_site_entrypoint())
        with mock.patch.dict(os.environ, {"PYTHONNOUSERSITE": "1"}):
            self.install("python")

    def test_digest_failure_removes_workspace(self):
        archive = self.root / "binary.zip"
        self.configure_binary(archive, "amd64")
        ACTION.CONFIGS["binary"]["outer_sha256"] = "0" * 64
        self.active_kind = "binary"
        with mock.patch.object(ACTION, "download_file", side_effect=self.copy_download):
            with self.assertRaisesRegex(ACTION.HandoffError, "integrity verification"):
                ACTION.install("binary")
        self.assertEqual(list(self.state_parent.iterdir()), [])

    def test_setup_failure_removes_workspace(self):
        archive = self.root / "python.zip"
        self.configure_python(archive, python_entrypoint(7))
        self.active_kind = "python"
        with mock.patch.object(ACTION, "download_file", side_effect=self.copy_download):
            with self.assertRaisesRegex(ACTION.HandoffError, "exit code 7"):
                ACTION.install("python")
        self.assertEqual(list(self.state_parent.iterdir()), [])

    def test_termination_removes_workspace(self):
        previous_handler = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM, ACTION.handle_termination)
        self.active_kind = "binary"
        try:
            with mock.patch.object(
                ACTION,
                "download_file",
                side_effect=lambda *_args: os.kill(os.getpid(), signal.SIGTERM),
            ):
                with self.assertRaisesRegex(ACTION.HandoffError, "interrupted"):
                    ACTION.install("binary")
            self.assertEqual(list(self.state_parent.iterdir()), [])
        finally:
            signal.signal(signal.SIGTERM, previous_handler)

    def test_invalid_token_is_rejected(self):
        with self.assertRaisesRegex(ACTION.HandoffError, "Invalid"):
            ACTION.run("binary", "../unexpected")

    def test_completion_record_tampering_is_rejected(self):
        archive = self.root / "binary.zip"
        self.configure_binary(archive, "amd64")
        workspace_id = self.install("binary")
        completion = self.state_parent / workspace_id / "complete"
        completion.write_text("invalid\n", encoding="utf-8")
        completion.chmod(0o600)
        with self.assertRaisesRegex(ACTION.HandoffError, "completion record"):
            ACTION.run("binary", workspace_id)

    def test_entrypoint_tampering_is_rejected(self):
        archive = self.root / "binary.zip"
        self.configure_binary(archive, "amd64")
        workspace_id = self.install("binary")
        entrypoint = self.state_parent / workspace_id / "payload/MDESupportTool"
        entrypoint.write_bytes(entrypoint.read_bytes() + b"\n")
        with self.assertRaisesRegex(ACTION.HandoffError, "integrity verification"):
            ACTION.run("binary", workspace_id)


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
