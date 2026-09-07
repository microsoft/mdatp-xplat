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
import unittest
import urllib.request
import zipfile
from pathlib import Path
from unittest import mock


CLIENT_ANALYZER_DIR = Path(__file__).resolve().parents[1]
ACTION_PATH = CLIENT_ANALYZER_DIR / "client_analyzer_action.py"
SPEC = importlib.util.spec_from_file_location("client_analyzer_action", ACTION_PATH)
ACTION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ACTION)

BINARY_URL = "https://go.microsoft.com/fwlink/?linkid=2336125"
BINARY_SHA256 = "5f906591d33d675f14d73d5b658a796cec7480b023b18d45c5d687713a4d4fbb"
BINARY_HASHES = {
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


def create_binary_archive(path, architecture="amd64", extra_entries=None):
    entrypoint = binary_entrypoint()
    inner_buffer = io.BytesIO()
    with zipfile.ZipFile(inner_buffer, "w") as inner_archive:
        add_zip_file(inner_archive, "MDESupportTool", entrypoint, mode=0o700)
        for info, content in extra_entries or ():
            inner_archive.writestr(info, content)
    inner_content = inner_buffer.getvalue()

    inner_name = BINARY_HASHES[architecture]["inner_name"]
    with zipfile.ZipFile(path, "w") as outer_archive:
        add_zip_file(outer_archive, inner_name, inner_content)

    return {
        "outer_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "inner_sha256": sha256_bytes(inner_content),
        "entry_sha256": sha256_bytes(entrypoint),
    }


def create_python_archive(path, entrypoint=None, extra_entries=None):
    entrypoint = entrypoint if entrypoint is not None else python_entrypoint()
    with zipfile.ZipFile(path, "w") as archive:
        add_zip_file(archive, "mde_support_tool.sh", entrypoint, mode=0o700)
        for info, content in extra_entries or ():
            archive.writestr(info, content)
    return {
        "outer_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "entry_sha256": sha256_bytes(entrypoint),
    }


class ActionTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.state_parent = self.root / "state"
        self.state_parent.mkdir(mode=0o700)
        self.original_state_parent = ACTION.STATE_PARENT
        self.original_schemes = ACTION.ALLOWED_DOWNLOAD_SCHEMES
        self.original_configs = copy.deepcopy(ACTION.CONFIGS)
        ACTION.STATE_PARENT = self.state_parent
        ACTION.ALLOWED_DOWNLOAD_SCHEMES = {"file"}
        self.machine_patcher = mock.patch.object(
            ACTION.platform,
            "machine",
            return_value="x86_64",
        )
        self.machine_patcher.start()

    def tearDown(self):
        self.machine_patcher.stop()
        ACTION.STATE_PARENT = self.original_state_parent
        ACTION.ALLOWED_DOWNLOAD_SCHEMES = self.original_schemes
        ACTION.CONFIGS.clear()
        ACTION.CONFIGS.update(self.original_configs)
        self.temporary_directory.cleanup()

    def configure_binary(self, archive, architecture="amd64"):
        hashes = create_binary_archive(archive, architecture)
        config = ACTION.CONFIGS["binary"]
        config["download_url"] = archive.as_uri()
        config["outer_sha256"] = hashes["outer_sha256"]
        config["archives"][architecture]["inner_sha256"] = hashes["inner_sha256"]
        config["archives"][architecture]["entry_sha256"] = hashes["entry_sha256"]
        return hashes

    def configure_python(self, archive, entrypoint=None, extra_entries=None):
        hashes = create_python_archive(archive, entrypoint, extra_entries)
        config = ACTION.CONFIGS["python"]
        config["download_url"] = archive.as_uri()
        config["outer_sha256"] = hashes["outer_sha256"]
        config["entry_sha256"] = hashes["entry_sha256"]
        return hashes

    def install(self, kind):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            ACTION.install(kind)
        match = re.search(
            rf"workspace ID: ({re.escape(ACTION.CONFIGS[kind]['workspace_prefix'])}[0-9a-f]{{32}})",
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


class TestSourceAndWrappers(unittest.TestCase):
    def test_actions_do_not_use_legacy_shared_paths(self):
        for path in (ACTION_PATH, *(CLIENT_ANALYZER_DIR / name for name in WRAPPERS)):
            with self.subTest(path=path.name):
                self.assertNotIn(
                    "/tmp/XMDEClientAnalyzer",
                    path.read_text(encoding="utf-8"),
                )

    def test_wrappers_are_thin_package_local_dispatchers(self):
        for name, command in WRAPPERS.items():
            with self.subTest(wrapper=name):
                lines = (CLIENT_ANALYZER_DIR / name).read_text(
                    encoding="utf-8"
                ).splitlines()
                self.assertLessEqual(len(lines), 16)
                self.assertIn("client_analyzer_action.py", "\n".join(lines))
                self.assertIn(command, lines[-1])

    def test_helper_pins_current_artifacts_and_both_binary_architectures(self):
        helper = ACTION_PATH.read_text(encoding="utf-8")
        self.assertIn(BINARY_URL, helper)
        self.assertIn(BINARY_SHA256, helper)
        self.assertIn(PYTHON_URL, helper)
        self.assertIn(PYTHON_SHA256, helper)
        for hashes in BINARY_HASHES.values():
            self.assertIn(hashes["inner_sha256"], helper)
            self.assertIn(hashes["entry_sha256"], helper)

    def test_wrappers_route_to_package_helper(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory)
            capture = package / "arguments.txt"
            helper = package / "client_analyzer_action.py"
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
                expected = [command, *arguments]
                self.assertEqual(
                    capture.read_text(encoding="utf-8").splitlines(),
                    expected,
                )


class TestDownloadSchemeControls(ActionTestCase):
    def test_initial_url_rejects_http_without_retaining_state(self):
        for kind in ("binary", "python"):
            with self.subTest(kind=kind):
                ACTION.ALLOWED_DOWNLOAD_SCHEMES = {"https"}
                ACTION.CONFIGS[kind]["download_url"] = (
                    "http://127.0.0.1/client-analyzer.zip"
                )
                with self.assertRaisesRegex(ACTION.ActionError, "disallowed URL scheme"):
                    ACTION.install(kind)
                self.assertEqual(list(self.state_parent.iterdir()), [])

    def test_redirect_handler_rejects_https_to_http(self):
        ACTION.ALLOWED_DOWNLOAD_SCHEMES = {"https"}
        handler = ACTION.RestrictedRedirectHandler()
        with self.assertRaisesRegex(ACTION.ActionError, "disallowed URL scheme"):
            handler.redirect_request(
                None,
                None,
                302,
                "Found",
                {},
                "http://127.0.0.1/client-analyzer.zip",
            )

    def test_final_url_rejects_http(self):
        class FakeResponse:
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, _exception_type, _exception, _traceback):
                return False

            def geturl(self):
                return "http://127.0.0.1/client-analyzer.zip"

        class FakeOpener:
            def open(self, _request, timeout):
                self.timeout = timeout
                return FakeResponse()

        ACTION.ALLOWED_DOWNLOAD_SCHEMES = {"https"}
        with mock.patch.object(
            ACTION.urllib.request,
            "build_opener",
            return_value=FakeOpener(),
        ):
            with self.assertRaisesRegex(
                ACTION.ActionError,
                "resolved to a disallowed URL scheme",
            ):
                ACTION.download_file(
                    "https://example.invalid/client-analyzer.zip",
                    self.root / "archive.zip",
                )


class TestInstallers(ActionTestCase):
    def test_binary_installer_supports_amd64_and_arm64(self):
        cases = (("amd64", "x86_64"), ("arm64", "aarch64"))
        for architecture, machine in cases:
            with self.subTest(architecture=architecture):
                archive = self.root / f"{architecture}.zip"
                self.configure_binary(archive, architecture)
                with mock.patch.object(ACTION.platform, "machine", return_value=machine):
                    workspace_id = self.install("binary")
                workspace = self.state_parent / workspace_id
                completion = (workspace / "complete").read_text(
                    encoding="utf-8"
                ).split()
                self.assertEqual(completion[2], architecture)
                self.assertEqual(stat.S_IMODE(workspace.stat().st_mode), 0o700)
                self.assertEqual(
                    stat.S_IMODE((workspace / "complete").stat().st_mode),
                    0o600,
                )
                self.assertEqual(
                    stat.S_IMODE(
                        (workspace / "payload/MDESupportTool").stat().st_mode
                    ),
                    0o700,
                )

    def test_python_installer_prepares_dependencies(self):
        archive = self.root / "python.zip"
        self.configure_python(archive)
        workspace_id = self.install("python")
        self.assertTrue((self.state_parent / workspace_id / "complete").is_file())

    def test_python_installer_clears_python_no_user_site(self):
        archive = self.root / "python-user-site.zip"
        self.configure_python(archive, python_user_site_entrypoint())
        with mock.patch.dict(os.environ, {"PYTHONNOUSERSITE": "1"}):
            self.install("python")

    def test_digest_failure_removes_workspace(self):
        archive = self.root / "binary.zip"
        self.configure_binary(archive)
        ACTION.CONFIGS["binary"]["outer_sha256"] = "0" * 64
        with self.assertRaisesRegex(ACTION.ActionError, "integrity verification"):
            ACTION.install("binary")
        self.assertEqual(list(self.state_parent.iterdir()), [])

    def test_traversal_is_rejected_before_writing_outside_workspace(self):
        traversal = zipfile.ZipInfo("../escaped")
        traversal.create_system = 3
        traversal.external_attr = (stat.S_IFREG | 0o600) << 16
        archive = self.root / "binary.zip"
        hashes = create_binary_archive(
            archive,
            extra_entries=[(traversal, b"blocked")],
        )
        config = ACTION.CONFIGS["binary"]
        config["download_url"] = archive.as_uri()
        config["outer_sha256"] = hashes["outer_sha256"]
        config["archives"]["amd64"]["inner_sha256"] = hashes["inner_sha256"]
        config["archives"]["amd64"]["entry_sha256"] = hashes["entry_sha256"]
        with self.assertRaisesRegex(ACTION.ActionError, "unsafe path"):
            ACTION.install("binary")
        self.assertFalse((self.state_parent / "escaped").exists())
        self.assertEqual(list(self.state_parent.iterdir()), [])

    def test_symlink_archive_entry_is_rejected(self):
        symlink = zipfile.ZipInfo("payload-link")
        symlink.create_system = 3
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive = self.root / "python.zip"
        self.configure_python(
            archive,
            extra_entries=[(symlink, b"/etc/passwd")],
        )
        with self.assertRaisesRegex(ACTION.ActionError, "link or special file"):
            ACTION.install("python")
        self.assertEqual(list(self.state_parent.iterdir()), [])

    def test_setup_failure_removes_python_workspace(self):
        archive = self.root / "python.zip"
        self.configure_python(archive, python_entrypoint(setup_exit_code=7))
        with self.assertRaisesRegex(ACTION.ActionError, "exit code 7"):
            ACTION.install("python")
        self.assertEqual(list(self.state_parent.iterdir()), [])

    def test_termination_signal_removes_workspace(self):
        previous_handler = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM, ACTION.handle_termination)
        try:
            for kind in ("binary", "python"):
                with self.subTest(kind=kind):
                    with mock.patch.object(
                        ACTION,
                        "download_file",
                        side_effect=lambda *_args: os.kill(os.getpid(), signal.SIGTERM),
                    ):
                        with self.assertRaisesRegex(
                            ACTION.ActionError,
                            "interrupted by signal",
                        ):
                            ACTION.install(kind)
                    self.assertEqual(list(self.state_parent.iterdir()), [])
        finally:
            signal.signal(signal.SIGTERM, previous_handler)

    def test_unsupported_architecture_creates_no_state(self):
        with mock.patch.object(ACTION.platform, "machine", return_value="unsupported"):
            with self.assertRaisesRegex(ACTION.ActionError, "Unsupported architecture"):
                ACTION.install("binary")
        self.assertEqual(list(self.state_parent.iterdir()), [])


class TestRunners(ActionTestCase):
    def install_binary(self, architecture="amd64", machine="x86_64"):
        archive = self.root / f"{architecture}.zip"
        self.configure_binary(archive, architecture)
        with mock.patch.object(ACTION.platform, "machine", return_value=machine):
            return self.install("binary")

    def install_python(self):
        archive = self.root / "python.zip"
        self.configure_python(archive)
        return self.install("python")

    def test_runners_use_fixed_diagnostic_arguments(self):
        cases = (
            ("binary", self.install_binary(), "x86_64"),
            ("python", self.install_python(), "x86_64"),
        )
        for kind, workspace_id, machine in cases:
            with self.subTest(kind=kind):
                with mock.patch.object(ACTION.platform, "machine", return_value=machine):
                    _, execute_arguments = self.run_without_exec(kind, workspace_id)
                entrypoint, arguments, environment = execute_arguments
                self.assertEqual(
                    arguments,
                    [str(entrypoint), "--bypass-disclaimer", "-d"],
                )
                self.assertRegex(
                    environment["TMPDIR"],
                    r"/runs/run-[0-9a-f]{32}$",
                )

    def test_arm64_runner_uses_arm64_completion_record(self):
        workspace_id = self.install_binary("arm64", "aarch64")
        with mock.patch.object(ACTION.platform, "machine", return_value="aarch64"):
            self.run_without_exec("binary", workspace_id)

    def test_tampered_entrypoint_is_rejected(self):
        workspace_id = self.install_binary()
        entrypoint = self.state_parent / workspace_id / "payload/MDESupportTool"
        entrypoint.write_bytes(entrypoint.read_bytes() + b"\n")
        with self.assertRaisesRegex(ACTION.ActionError, "integrity verification"):
            ACTION.run("binary", workspace_id)

    def test_invalid_workspace_identifier_is_rejected(self):
        with self.assertRaisesRegex(ACTION.ActionError, "Invalid"):
            ACTION.run("binary", "../unexpected")

    def test_extra_parameters_are_rejected(self):
        with self.assertRaisesRegex(ACTION.ActionError, "exactly one workspace"):
            ACTION.main(("run-binary", "token", "unexpected"))

    def test_modified_completion_record_is_rejected(self):
        workspace_id = self.install_binary()
        completion = self.state_parent / workspace_id / "complete"
        completion.write_text("invalid\n", encoding="utf-8")
        completion.chmod(0o600)
        with self.assertRaisesRegex(ACTION.ActionError, "completion record"):
            ACTION.run("binary", workspace_id)


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

    def test_published_binary_archive(self):
        content = self.download(BINARY_URL)
        self.assertEqual(sha256_bytes(content), BINARY_SHA256)
        with zipfile.ZipFile(io.BytesIO(content), "r") as archive:
            inner_archives = {
                architecture: archive.read(hashes["inner_name"])
                for architecture, hashes in BINARY_HASHES.items()
            }
        for architecture, inner_content in inner_archives.items():
            with self.subTest(architecture=architecture):
                self.assertEqual(
                    sha256_bytes(inner_content),
                    BINARY_HASHES[architecture]["inner_sha256"],
                )
                with zipfile.ZipFile(io.BytesIO(inner_content), "r") as archive:
                    self.assertEqual(
                        sha256_bytes(archive.read("MDESupportTool")),
                        BINARY_HASHES[architecture]["entry_sha256"],
                    )

    def test_published_python_archive(self):
        content = self.download(PYTHON_URL)
        self.assertEqual(sha256_bytes(content), PYTHON_SHA256)
        with zipfile.ZipFile(io.BytesIO(content), "r") as archive:
            self.assertEqual(
                sha256_bytes(archive.read("mde_support_tool.sh")),
                PYTHON_ENTRY_SHA256,
            )


if __name__ == "__main__":
    unittest.main()
