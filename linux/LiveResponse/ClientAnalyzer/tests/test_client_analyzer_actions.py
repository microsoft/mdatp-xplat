import hashlib
import io
import json
import os
import re
import signal
import stat
import subprocess
import tempfile
import time
import unittest
import urllib.request
import zipfile
from pathlib import Path


CLIENT_ANALYZER_DIR = Path(__file__).resolve().parents[1]
BINARY_INSTALLER = "InstallXMDEClientAnalyzer.sh"
PYTHON_INSTALLER = "InstallXMDEPythonClientAnalyzer.sh"
BINARY_RUNNER = "MDESupportTool.sh"
PYTHON_RUNNER = "MDEPythonSupportTool.sh"
BINARY_URL = "https://go.microsoft.com/fwlink/?linkid=2336125"
BINARY_SHA256 = "5f906591d33d675f14d73d5b658a796cec7480b023b18d45c5d687713a4d4fbb"
BINARY_INNER_SHA256 = (
    "a500c00fe0dc2bb5b23ec9c771fd40694d111fa78d095d6ff77e4f0b36a23903"
)
BINARY_ENTRY_SHA256 = (
    "b6b21fbc12b6d37be331a5e27a9741b43d35876645e02b26c8cafc4e623ed5e1"
)
BINARY_ARM64_INNER_SHA256 = (
    "ba8cc0c9766f5c937a90db00af6ed936ecdbfbba88049a383df814203af5066a"
)
BINARY_ARM64_ENTRY_SHA256 = (
    "a3b60a11eea093f9ec7b9bd7ea86a0e8bbc6f481116311dd678d69def49b5169"
)
PYTHON_URL = "https://go.microsoft.com/fwlink/?linkid=2336046"
PYTHON_SHA256 = "0b7c350a1c19e049416b1c8fb7ed857569ddcc32fb90453a3fccd083487c0b4e"
PYTHON_ENTRY_SHA256 = (
    "00a03ca9b9f9c6d985ef48f8bcaae5cd08b37af551a452d005847d612fb67ffe"
)


def read_script(name):
    return (CLIENT_ANALYZER_DIR / name).read_text(encoding="utf-8")


def sha256_bytes(content):
    return hashlib.sha256(content).hexdigest()


def add_zip_file(archive, name, content, mode=0o600, file_type=stat.S_IFREG):
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (file_type | mode) << 16
    archive.writestr(info, content)


def binary_entrypoint():
    return b"""#!/bin/sh
capture_file=${CAPTURE_FILE:?}
printf '%s\\n' "$#" > "$capture_file"
for argument in "$@"; do
    printf '<%s>\\n' "$argument" >> "$capture_file"
done
printf 'TMPDIR=<%s>\\n' "$TMPDIR" >> "$capture_file"
"""


def python_entrypoint(setup_exit_code=0):
    return f"""#!/bin/sh
if [ "$#" -eq 0 ]; then
    printf 'setup\\n' > "${{SETUP_CAPTURE_FILE:?}}"
    exit {setup_exit_code}
fi
capture_file=${{CAPTURE_FILE:?}}
printf '%s\\n' "$#" > "$capture_file"
for argument in "$@"; do
    printf '<%s>\\n' "$argument" >> "$capture_file"
done
printf 'TMPDIR=<%s>\\n' "$TMPDIR" >> "$capture_file"
""".encode("utf-8")


def python_user_site_entrypoint():
    return b"""#!/bin/sh
user_base="$PWD/.deps"
site_dir=$(PYTHONUSERBASE="$user_base" python3 -c 'import site; print(site.getusersitepackages())')
mkdir -p "$site_dir"
printf 'VALUE = 1\\n' > "$site_dir/workspace_dependency.py"
PYTHONUSERBASE="$user_base" python3 -c 'import workspace_dependency'
"""


def binary_architecture(architecture):
    if architecture == "amd64":
        return {
            "machine": "x86_64",
            "inner_name": "SupportToolLinuxamd64Binary.zip",
            "inner_sha256": BINARY_INNER_SHA256,
            "entry_sha256": BINARY_ENTRY_SHA256,
        }
    if architecture == "arm64":
        return {
            "machine": "aarch64",
            "inner_name": "SupportToolLinuxarm64Binary.zip",
            "inner_sha256": BINARY_ARM64_INNER_SHA256,
            "entry_sha256": BINARY_ARM64_ENTRY_SHA256,
        }
    raise AssertionError(f"Unsupported test architecture: {architecture}")


def create_binary_archive(
    path,
    architecture="amd64",
    entrypoint=None,
    extra_inner_entries=None,
):
    architecture_info = binary_architecture(architecture)
    entrypoint = entrypoint if entrypoint is not None else binary_entrypoint()
    inner_buffer = io.BytesIO()
    with zipfile.ZipFile(inner_buffer, "w") as inner_archive:
        add_zip_file(inner_archive, "MDESupportTool", entrypoint, mode=0o700)
        for info, content in extra_inner_entries or ():
            inner_archive.writestr(info, content)
    inner_content = inner_buffer.getvalue()

    with zipfile.ZipFile(path, "w") as outer_archive:
        add_zip_file(
            outer_archive,
            architecture_info["inner_name"],
            inner_content,
        )

    return {
        "outer_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "inner_sha256": sha256_bytes(inner_content),
        "entry_sha256": sha256_bytes(entrypoint),
        "architecture": architecture,
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


def replace_required(text, old, new):
    if old not in text:
        raise AssertionError(f"Required test replacement was not found: {old}")
    return text.replace(old, new)


def write_patched_script(directory, name, replacements):
    text = read_script(name)
    for old, new in replacements:
        text = replace_required(text, old, new)
    path = directory / name
    path.write_text(text, encoding="utf-8")
    path.chmod(0o700)
    return path


def common_replacements(state_parent):
    return [
        (
            'STATE_PARENT = Path("/var/tmp")',
            f"STATE_PARENT = Path({str(state_parent)!r})",
        ),
        (
            'ALLOWED_DOWNLOAD_SCHEMES = {"https"}',
            'ALLOWED_DOWNLOAD_SCHEMES = {"file"}',
        ),
    ]


def binary_installer_replacements(state_parent, archive, hashes):
    architecture_info = binary_architecture(hashes["architecture"])
    return common_replacements(state_parent) + [
        (f'DOWNLOAD_URL = "{BINARY_URL}"', f'DOWNLOAD_URL = {archive.as_uri()!r}'),
        (f'OUTER_SHA256 = "{BINARY_SHA256}"', f'OUTER_SHA256 = "{hashes["outer_sha256"]}"'),
        (architecture_info["inner_sha256"], hashes["inner_sha256"]),
        (architecture_info["entry_sha256"], hashes["entry_sha256"]),
        (
            "machine = platform.machine().lower()",
            f'machine = "{architecture_info["machine"]}"',
        ),
    ]


def binary_runner_replacements(state_parent, hashes):
    architecture_info = binary_architecture(hashes["architecture"])
    return [
        (
            'STATE_PARENT = Path("/var/tmp")',
            f"STATE_PARENT = Path({str(state_parent)!r})",
        ),
        (f'OUTER_SHA256 = "{BINARY_SHA256}"', f'OUTER_SHA256 = "{hashes["outer_sha256"]}"'),
        (architecture_info["inner_sha256"], hashes["inner_sha256"]),
        (architecture_info["entry_sha256"], hashes["entry_sha256"]),
        (
            "machine = platform.machine().lower()",
            f'machine = "{architecture_info["machine"]}"',
        ),
    ]


def python_installer_replacements(state_parent, archive, hashes):
    return common_replacements(state_parent) + [
        (f'DOWNLOAD_URL = "{PYTHON_URL}"', f'DOWNLOAD_URL = {archive.as_uri()!r}'),
        (f'OUTER_SHA256 = "{PYTHON_SHA256}"', f'OUTER_SHA256 = "{hashes["outer_sha256"]}"'),
        (PYTHON_ENTRY_SHA256, hashes["entry_sha256"]),
    ]


def python_runner_replacements(state_parent, hashes):
    return [
        (
            'STATE_PARENT = Path("/var/tmp")',
            f"STATE_PARENT = Path({str(state_parent)!r})",
        ),
        (f'OUTER_SHA256 = "{PYTHON_SHA256}"', f'OUTER_SHA256 = "{hashes["outer_sha256"]}"'),
        (PYTHON_ENTRY_SHA256, hashes["entry_sha256"]),
    ]


def run_script(path, *arguments, environment=None):
    merged_environment = os.environ.copy()
    if environment:
        merged_environment.update(environment)
    return subprocess.run(
        ["/bin/sh", str(path), *arguments],
        check=False,
        capture_output=True,
        text=True,
        env=merged_environment,
        timeout=120,
    )


def workspace_id(output, prefix):
    matches = re.findall(r"workspace ID: (" + re.escape(prefix) + r"[0-9a-f]{32})", output)
    if len(matches) != 1:
        raise AssertionError(f"Expected one workspace ID in output: {output}")
    return matches[0]


def embedded_installer_library(name):
    text = read_script(name)
    payload = text.split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    library = payload.split("\nsignal.signal(signal.SIGHUP", 1)[0]
    namespace = {"__name__": f"{name}_test"}
    exec(compile(library, name, "exec"), namespace)
    return namespace


class TestClientAnalyzerSourceContracts(unittest.TestCase):
    def test_actions_do_not_use_predictable_shared_tmp_paths(self):
        for script_name in (
            BINARY_INSTALLER,
            PYTHON_INSTALLER,
            BINARY_RUNNER,
            PYTHON_RUNNER,
        ):
            with self.subTest(script=script_name):
                self.assertNotIn("/tmp/XMDEClientAnalyzer", read_script(script_name))

    def test_installers_pin_current_archives(self):
        binary_installer = read_script(BINARY_INSTALLER)
        python_installer = read_script(PYTHON_INSTALLER)

        self.assertIn(BINARY_URL, binary_installer)
        self.assertIn(BINARY_SHA256, binary_installer)
        self.assertIn(BINARY_ARM64_INNER_SHA256, binary_installer)
        self.assertIn(BINARY_ARM64_ENTRY_SHA256, binary_installer)
        self.assertIn(PYTHON_URL, python_installer)
        self.assertIn(PYTHON_SHA256, python_installer)

    def test_installers_create_opaque_private_workspaces(self):
        self.assertIn(
            "mde-client-analyzer-binary-",
            read_script(BINARY_INSTALLER),
        )
        self.assertIn(
            "mde-client-analyzer-python-",
            read_script(PYTHON_INSTALLER),
        )

    def test_runners_reject_legacy_argument_forwarding(self):
        self.assertNotIn("./MDESupportTool $@", read_script(BINARY_RUNNER))
        self.assertNotIn(
            "./mde_support_tool.sh -d $@",
            read_script(PYTHON_RUNNER),
        )


class TestDownloadSchemeControls(unittest.TestCase):
    def test_installers_reject_non_https_initial_url_without_retaining_state(self):
        cases = (
            (BINARY_INSTALLER, BINARY_URL),
            (PYTHON_INSTALLER, PYTHON_URL),
        )
        for script_name, production_url in cases:
            with self.subTest(script=script_name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                state_parent = root / "state"
                scripts = root / "scripts"
                state_parent.mkdir(mode=0o700)
                scripts.mkdir(mode=0o700)
                installer = write_patched_script(
                    scripts,
                    script_name,
                    [
                        (
                            'STATE_PARENT = Path("/var/tmp")',
                            f"STATE_PARENT = Path({str(state_parent)!r})",
                        ),
                        (
                            f'DOWNLOAD_URL = "{production_url}"',
                            'DOWNLOAD_URL = "http://127.0.0.1/client-analyzer.zip"',
                        ),
                    ],
                )

                result = run_script(installer)

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("disallowed URL scheme", result.stderr)
                self.assertEqual(list(state_parent.iterdir()), [])

    def test_redirect_handler_rejects_https_to_http_downgrade(self):
        for script_name in (BINARY_INSTALLER, PYTHON_INSTALLER):
            with self.subTest(script=script_name):
                namespace = embedded_installer_library(script_name)
                handler = namespace["RestrictedRedirectHandler"]()

                with self.assertRaisesRegex(
                    namespace["InstallError"],
                    "disallowed URL scheme",
                ):
                    handler.redirect_request(
                        None,
                        None,
                        302,
                        "Found",
                        {},
                        "http://127.0.0.1/client-analyzer.zip",
                    )

    def test_download_rejects_non_https_final_url(self):
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
                if timeout != 120:
                    raise AssertionError(f"Unexpected timeout: {timeout}")
                return FakeResponse()

        for script_name in (BINARY_INSTALLER, PYTHON_INSTALLER):
            with self.subTest(script=script_name), tempfile.TemporaryDirectory() as directory:
                namespace = embedded_installer_library(script_name)
                original_build_opener = namespace["urllib"].request.build_opener
                namespace["urllib"].request.build_opener = lambda *_handlers: FakeOpener()
                try:
                    with self.assertRaisesRegex(
                        namespace["InstallError"],
                        "resolved to a disallowed URL scheme",
                    ):
                        namespace["download_file"](
                            Path(directory) / "client-analyzer.zip"
                        )
                finally:
                    namespace["urllib"].request.build_opener = original_build_opener


class TestClientAnalyzerInstallers(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.state_parent = self.root / "state"
        self.state_parent.mkdir(mode=0o700)
        self.scripts = self.root / "scripts"
        self.scripts.mkdir(mode=0o700)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_binary_installer_creates_private_verified_workspace(self):
        for architecture in ("amd64", "arm64"):
            with self.subTest(architecture=architecture):
                archive = self.root / f"binary-{architecture}.zip"
                hashes = create_binary_archive(
                    archive,
                    architecture=architecture,
                )
                installer = write_patched_script(
                    self.scripts,
                    BINARY_INSTALLER,
                    binary_installer_replacements(
                        self.state_parent,
                        archive,
                        hashes,
                    ),
                )

                result = run_script(installer)

                self.assertEqual(result.returncode, 0, result.stderr)
                identifier = workspace_id(
                    result.stdout,
                    "mde-client-analyzer-binary-",
                )
                workspace = self.state_parent / identifier
                manifest = json.loads(
                    (workspace / "manifest.json").read_text(encoding="utf-8")
                )
                self.assertEqual(manifest["architecture"], architecture)
                self.assertEqual(stat.S_IMODE(workspace.stat().st_mode), 0o700)
                self.assertEqual(
                    stat.S_IMODE((workspace / "manifest.json").stat().st_mode),
                    0o600,
                )
                self.assertEqual(
                    stat.S_IMODE(
                        (workspace / "payload/MDESupportTool").stat().st_mode
                    ),
                    0o700,
                )
                self.assertFalse((workspace / "client-analyzer.zip").exists())

    def test_python_installer_prepares_dependencies_before_publishing_workspace(self):
        archive = self.root / "python.zip"
        hashes = create_python_archive(archive)
        installer = write_patched_script(
            self.scripts,
            PYTHON_INSTALLER,
            python_installer_replacements(self.state_parent, archive, hashes),
        )
        setup_capture = self.root / "setup.txt"

        result = run_script(
            installer,
            environment={"SETUP_CAPTURE_FILE": str(setup_capture)},
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        identifier = workspace_id(
            result.stdout,
            "mde-client-analyzer-python-",
        )
        workspace = self.state_parent / identifier
        self.assertEqual(setup_capture.read_text(encoding="utf-8"), "setup\n")
        self.assertTrue((workspace / "manifest.json").is_file())
        self.assertFalse((workspace / "setup").exists())

    def test_python_installer_clears_python_no_user_site_for_workspace_dependencies(self):
        archive = self.root / "python-user-site.zip"
        hashes = create_python_archive(
            archive,
            entrypoint=python_user_site_entrypoint(),
        )
        installer = write_patched_script(
            self.scripts,
            PYTHON_INSTALLER,
            python_installer_replacements(self.state_parent, archive, hashes),
        )

        result = run_script(
            installer,
            environment={"PYTHONNOUSERSITE": "1"},
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_binary_installer_removes_workspace_after_digest_failure(self):
        archive = self.root / "binary.zip"
        hashes = create_binary_archive(archive)
        hashes["outer_sha256"] = "0" * 64
        installer = write_patched_script(
            self.scripts,
            BINARY_INSTALLER,
            binary_installer_replacements(self.state_parent, archive, hashes),
        )

        result = run_script(installer)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("failed integrity verification", result.stderr)
        self.assertEqual(list(self.state_parent.iterdir()), [])

    def test_python_installer_removes_workspace_after_setup_failure(self):
        archive = self.root / "python.zip"
        hashes = create_python_archive(
            archive,
            entrypoint=python_entrypoint(setup_exit_code=7),
        )
        installer = write_patched_script(
            self.scripts,
            PYTHON_INSTALLER,
            python_installer_replacements(self.state_parent, archive, hashes),
        )
        setup_capture = self.root / "setup.txt"

        result = run_script(
            installer,
            environment={"SETUP_CAPTURE_FILE": str(setup_capture)},
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dependency preparation failed with exit code 7", result.stderr)
        self.assertEqual(list(self.state_parent.iterdir()), [])

    def test_binary_installer_rejects_traversal_before_writing_outside_workspace(self):
        traversal = zipfile.ZipInfo("../escaped")
        traversal.create_system = 3
        traversal.external_attr = (stat.S_IFREG | 0o600) << 16
        archive = self.root / "binary.zip"
        hashes = create_binary_archive(
            archive,
            extra_inner_entries=[(traversal, b"blocked")],
        )
        installer = write_patched_script(
            self.scripts,
            BINARY_INSTALLER,
            binary_installer_replacements(self.state_parent, archive, hashes),
        )

        result = run_script(installer)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsafe path", result.stderr)
        self.assertFalse((self.state_parent / "escaped").exists())
        self.assertEqual(list(self.state_parent.iterdir()), [])

    def test_python_installer_rejects_symlink_archive_entry(self):
        symlink = zipfile.ZipInfo("payload-link")
        symlink.create_system = 3
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive = self.root / "python.zip"
        hashes = create_python_archive(
            archive,
            extra_entries=[(symlink, b"/etc/passwd")],
        )
        installer = write_patched_script(
            self.scripts,
            PYTHON_INSTALLER,
            python_installer_replacements(self.state_parent, archive, hashes),
        )

        result = run_script(installer)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("link or special file", result.stderr)
        self.assertEqual(list(self.state_parent.iterdir()), [])

    def test_binary_installer_rejects_unsupported_architecture_without_state(self):
        archive = self.root / "binary.zip"
        hashes = create_binary_archive(archive)
        replacements = binary_installer_replacements(
            self.state_parent,
            archive,
            hashes,
        )
        replacements.append(
            (
                'machine = "x86_64"',
                'machine = "unsupported"',
            )
        )
        installer = write_patched_script(
            self.scripts,
            BINARY_INSTALLER,
            replacements,
        )

        result = run_script(installer)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unsupported architecture", result.stderr)
        self.assertEqual(list(self.state_parent.iterdir()), [])

    def test_installers_remove_private_workspace_after_termination(self):
        cases = []

        binary_archive = self.root / "binary-termination.zip"
        binary_hashes = create_binary_archive(binary_archive)
        binary_replacements = binary_installer_replacements(
            self.state_parent,
            binary_archive,
            binary_hashes,
        )
        binary_replacements.append(
            (
                'workspace = create_workspace()\n        outer_archive = workspace / "client-analyzer.zip"',
                'workspace = create_workspace()\n        import time\n        time.sleep(60)\n        outer_archive = workspace / "client-analyzer.zip"',
            )
        )
        cases.append((BINARY_INSTALLER, binary_replacements))

        python_archive = self.root / "python-termination.zip"
        python_hashes = create_python_archive(python_archive)
        python_replacements = python_installer_replacements(
            self.state_parent,
            python_archive,
            python_hashes,
        )
        python_replacements.append(
            (
                'workspace = create_workspace()\n        archive_path = workspace / "client-analyzer.zip"',
                'workspace = create_workspace()\n        import time\n        time.sleep(60)\n        archive_path = workspace / "client-analyzer.zip"',
            )
        )
        cases.append((PYTHON_INSTALLER, python_replacements))

        for script_name, replacements in cases:
            with self.subTest(script=script_name):
                installer = write_patched_script(
                    self.scripts,
                    script_name,
                    replacements,
                )
                process = subprocess.Popen(
                    ["/bin/sh", str(installer)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    if list(self.state_parent.iterdir()):
                        break
                    time.sleep(0.05)
                else:
                    process.kill()
                    process.wait(timeout=10)
                    self.fail("Installer did not create a workspace before timeout.")

                process.send_signal(signal.SIGTERM)
                _, stderr = process.communicate(timeout=10)

                self.assertEqual(process.returncode, 1, stderr)
                self.assertIn("Installation interrupted by signal", stderr)
                self.assertEqual(list(self.state_parent.iterdir()), [])


class TestClientAnalyzerRunners(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.state_parent = self.root / "state"
        self.state_parent.mkdir(mode=0o700)
        self.scripts = self.root / "scripts"
        self.scripts.mkdir(mode=0o700)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def install_binary_fixture(self, architecture="amd64"):
        archive = self.root / f"binary-{architecture}.zip"
        hashes = create_binary_archive(
            archive,
            architecture=architecture,
        )
        installer = write_patched_script(
            self.scripts,
            BINARY_INSTALLER,
            binary_installer_replacements(self.state_parent, archive, hashes),
        )
        result = run_script(installer)
        self.assertEqual(result.returncode, 0, result.stderr)
        return (
            workspace_id(result.stdout, "mde-client-analyzer-binary-"),
            hashes,
        )

    def install_python_fixture(self):
        archive = self.root / "python.zip"
        hashes = create_python_archive(archive)
        installer = write_patched_script(
            self.scripts,
            PYTHON_INSTALLER,
            python_installer_replacements(self.state_parent, archive, hashes),
        )
        setup_capture = self.root / "setup.txt"
        result = run_script(
            installer,
            environment={"SETUP_CAPTURE_FILE": str(setup_capture)},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return (
            workspace_id(result.stdout, "mde-client-analyzer-python-"),
            hashes,
        )

    def test_binary_runner_maps_workspace_token_to_fixed_diagnostic_arguments(self):
        for architecture in ("amd64", "arm64"):
            with self.subTest(architecture=architecture):
                identifier, hashes = self.install_binary_fixture(architecture)
                runner = write_patched_script(
                    self.scripts,
                    BINARY_RUNNER,
                    binary_runner_replacements(self.state_parent, hashes),
                )
                capture = self.root / f"binary-{architecture}-arguments.txt"

                result = run_script(
                    runner,
                    identifier,
                    environment={"CAPTURE_FILE": str(capture)},
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                lines = capture.read_text(encoding="utf-8").splitlines()
                self.assertEqual(lines[:3], ["2", "<--bypass-disclaimer>", "<-d>"])
                self.assertRegex(
                    lines[3],
                    r"^TMPDIR=<.*/runs/run-[0-9a-f]{32}>$",
                )

    def test_python_runner_maps_workspace_token_to_fixed_diagnostic_arguments(self):
        identifier, hashes = self.install_python_fixture()
        runner = write_patched_script(
            self.scripts,
            PYTHON_RUNNER,
            python_runner_replacements(self.state_parent, hashes),
        )
        capture = self.root / "python-arguments.txt"

        result = run_script(
            runner,
            identifier,
            environment={"CAPTURE_FILE": str(capture)},
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        lines = capture.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[:3], ["2", "<--bypass-disclaimer>", "<-d>"])
        self.assertRegex(
            lines[3],
            r"^TMPDIR=<.*/runs/run-[0-9a-f]{32}>$",
        )

    def test_runner_rejects_tampered_entrypoint(self):
        identifier, hashes = self.install_binary_fixture()
        workspace = self.state_parent / identifier
        entrypoint = workspace / "payload/MDESupportTool"
        entrypoint.write_bytes(entrypoint.read_bytes() + b"\n")
        runner = write_patched_script(
            self.scripts,
            BINARY_RUNNER,
            binary_runner_replacements(self.state_parent, hashes),
        )
        capture = self.root / "arguments.txt"

        result = run_script(
            runner,
            identifier,
            environment={"CAPTURE_FILE": str(capture)},
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("failed integrity verification", result.stderr)
        self.assertFalse(capture.exists())

    def test_runner_rejects_invalid_workspace_identifier(self):
        hashes = {
            "outer_sha256": "1" * 64,
            "inner_sha256": "2" * 64,
            "entry_sha256": "3" * 64,
            "architecture": "amd64",
        }
        runner = write_patched_script(
            self.scripts,
            BINARY_RUNNER,
            binary_runner_replacements(self.state_parent, hashes),
        )

        result = run_script(runner, "../unexpected")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Invalid Client Analyzer workspace ID", result.stderr)

    def test_runner_rejects_extra_parameters(self):
        identifier, hashes = self.install_binary_fixture()
        runner = write_patched_script(
            self.scripts,
            BINARY_RUNNER,
            binary_runner_replacements(self.state_parent, hashes),
        )

        result = run_script(runner, identifier, "--unexpected")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Pass exactly one workspace ID", result.stderr)

    def test_runner_rejects_modified_manifest(self):
        identifier, hashes = self.install_binary_fixture()
        manifest_path = self.state_parent / identifier / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["kind"] = "python"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        manifest_path.chmod(0o600)
        runner = write_patched_script(
            self.scripts,
            BINARY_RUNNER,
            binary_runner_replacements(self.state_parent, hashes),
        )

        result = run_script(runner, identifier)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("manifest failed validation", result.stderr)


@unittest.skipUnless(
    os.environ.get("RUN_NETWORK_INTEGRITY_TESTS") == "1",
    "Set RUN_NETWORK_INTEGRITY_TESTS=1 to verify published artifacts.",
)
class TestPublishedArtifactIntegrity(unittest.TestCase):
    def download(self, url, maximum_bytes):
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "mdatp-xplat-client-analyzer-test"},
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            content = response.read(maximum_bytes + 1)
        self.assertLessEqual(len(content), maximum_bytes)
        return content

    def test_published_binary_archive_matches_pinned_digest_and_layout(self):
        content = self.download(BINARY_URL, 64 * 1024 * 1024)

        self.assertEqual(sha256_bytes(content), BINARY_SHA256)
        with zipfile.ZipFile(io.BytesIO(content), "r") as archive:
            amd64_content = archive.read("SupportToolLinuxamd64Binary.zip")
            arm64_content = archive.read("SupportToolLinuxarm64Binary.zip")
        self.assertEqual(sha256_bytes(amd64_content), BINARY_INNER_SHA256)
        self.assertEqual(sha256_bytes(arm64_content), BINARY_ARM64_INNER_SHA256)

        with zipfile.ZipFile(io.BytesIO(amd64_content), "r") as archive:
            self.assertEqual(
                sha256_bytes(archive.read("MDESupportTool")),
                BINARY_ENTRY_SHA256,
            )
        with zipfile.ZipFile(io.BytesIO(arm64_content), "r") as archive:
            self.assertEqual(
                sha256_bytes(archive.read("MDESupportTool")),
                BINARY_ARM64_ENTRY_SHA256,
            )

    def test_published_python_archive_matches_pinned_digest_and_layout(self):
        content = self.download(PYTHON_URL, 64 * 1024 * 1024)

        self.assertEqual(sha256_bytes(content), PYTHON_SHA256)
        with zipfile.ZipFile(io.BytesIO(content), "r") as archive:
            self.assertIn("mde_support_tool.sh", archive.namelist())


if __name__ == "__main__":
    unittest.main()
