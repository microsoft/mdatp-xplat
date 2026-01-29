#!/usr/bin/env python3
"""runner.py.

Main orchestrator for E2E testing using Vagrant and KVM.
Manages VM lifecycle, test execution, result collection, and reporting.
"""

import argparse
import contextlib
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

import yaml
from distro_parser import DistroParser
from health_checker import HealthChecker
from results_formatter import ResultsFormatter, TestResult

# Maximum time allowed for a single VM test (15 minutes)
VM_TIMEOUT_SECONDS = 15 * 60


@dataclass
class TestConfig:
    """Test configuration."""

    distro: str
    version: str
    scaled_version: str
    family: str
    vagrant_box: str
    cpus: int
    memory_mb: int
    disk_size_gb: int


class MissingSecretsError(Exception):
    """Raised when required secrets are missing."""

    pass


class BoxBuilder:
    """Handles building local Vagrant boxes from cloud images."""

    def __init__(self, scripts_dir: Path):
        """Initialize box builder.

        Args:
            scripts_dir: Path to tests/e2e/scripts directory

        """
        self.scripts_dir = scripts_dir
        self.convert_script = scripts_dir / "convert_cloud_image.sh"

    def get_installed_boxes(self) -> Set[str]:
        """Get set of installed Vagrant box names.

        Returns:
            Set of box names (e.g., {'local/debian12', 'generic/ubuntu2204'})

        """
        try:
            result = subprocess.run(
                ["vagrant", "box", "list"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return set()

            boxes = set()
            for line in result.stdout.strip().split("\n"):
                if line:
                    # Format: "box_name (provider, version, arch)"
                    match = re.match(r"^(\S+)\s+\(", line)
                    if match:
                        boxes.add(match.group(1))
            return boxes
        except Exception:
            return set()

    def is_local_box(self, box_name: str) -> bool:
        """Check if a box is a local/ box that we can build.

        Args:
            box_name: Vagrant box name

        Returns:
            True if this is a local/ box

        """
        return box_name.startswith("local/")

    def parse_local_box_name(self, box_name: str) -> Optional[tuple]:
        """Parse a local box name into distro and version.

        Args:
            box_name: Box name like 'local/fedora40' or 'local/debian12'

        Returns:
            Tuple of (distro, version) or None if not parseable

        """
        if not self.is_local_box(box_name):
            return None

        # Remove 'local/' prefix
        name = box_name.replace("local/", "")

        # Try to split into distro and version
        # Patterns: debian12, fedora40, fedora43
        patterns = [
            (r"^(debian)(\d+)$", lambda m: (m.group(1), m.group(2))),
            (r"^(fedora)(\d+)$", lambda m: (m.group(1), m.group(2))),
            (r"^(ubuntu)(\d+)$", lambda m: (m.group(1), m.group(2))),
        ]

        for pattern, extractor in patterns:
            match = re.match(pattern, name)
            if match:
                return extractor(match)

        return None

    def build_box(self, box_name: str) -> bool:
        """Build a local box from cloud image.

        Args:
            box_name: Box name like 'local/fedora40'

        Returns:
            True if build succeeded

        """
        parsed = self.parse_local_box_name(box_name)
        if not parsed:
            print(f"  ❌ Cannot parse box name: {box_name}")
            return False

        distro, version = parsed
        print(f"  📦 Building {box_name} from cloud image...")

        if not self.convert_script.exists():
            print(f"  ❌ Convert script not found: {self.convert_script}")
            return False

        try:
            result = subprocess.run(
                [str(self.convert_script), distro, version],
                cwd=self.scripts_dir,
                timeout=1800,  # 30 minute timeout for image conversion
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            print(f"  ❌ Build timed out for {box_name}")
            return False
        except Exception as e:
            print(f"  ❌ Build failed for {box_name}: {e}")
            return False

    def ensure_boxes_available(self, distros: List[Dict]) -> List[Dict]:
        """Ensure all required local boxes are available, building if needed.

        Args:
            distros: List of distro configs from get_test_matrix()

        Returns:
            Updated distro list (unchanged distros if all boxes available,
            or filtered list if some couldn't be built)

        """
        installed = self.get_installed_boxes()

        # Find missing local boxes
        missing_local = []
        for distro in distros:
            box_name = distro["vagrant_box"]
            if self.is_local_box(box_name) and box_name not in installed:
                missing_local.append((distro, box_name))

        if not missing_local:
            return distros

        print("\n🔧 Building missing local Vagrant boxes...")
        print(f"   (Found {len(missing_local)} local box(es) that need to be built)\n")

        failed_boxes = set()
        for distro, box_name in missing_local:
            if not self.build_box(box_name):
                failed_boxes.add(box_name)
                print(f"  ⚠️  Skipping {distro['distro']}:{distro['version']} - box build failed")
            else:
                print(f"  ✅ Built {box_name}")

        # Filter out distros whose boxes failed to build
        if failed_boxes:
            print(f"\n⚠️  {len(failed_boxes)} box(es) failed to build")
            distros = [d for d in distros if d["vagrant_box"] not in failed_boxes]

        print("")
        return distros


class VagrantRunner:
    """Manages Vagrant VM execution."""

    def __init__(self, vagrant_dir: Path):
        """Initialize Vagrant runner."""
        self.vagrant_dir = vagrant_dir
        self.vm_name = ""
        self.vagrant_env = {}  # Environment variables for vagrant commands

    def _get_vm_name(self, config: TestConfig) -> str:
        """Generate the VM name matching the Vagrantfile definition.

        Format: mde-<distro>-<version_no_dots>
        Examples: mde-ubuntu-2204, mde-debian-11, mde-rocky-9
        """
        return f"mde-{config.distro}-{config.version.replace('.', '')}"

    def setup_vm(self, config: TestConfig, secrets: Dict[str, str]) -> bool:
        """Set up and start Vagrant VM.

        Args:
            config: Test configuration
            secrets: Secret environment variables

        Returns:
            True if VM started successfully

        """
        self.vm_name = self._get_vm_name(config)
        self.config = config  # Store config for later use


        # Prepare environment - store for use by all vagrant commands
        self.vagrant_env = os.environ.copy()
        self.vagrant_env.update({
            "TEST_DISTRO": config.distro,
            "TEST_VERSION": config.version,
            "TEST_SCALED_VERSION": config.scaled_version,
            "TEST_VAGRANT_BOX": config.vagrant_box,
            "TEST_CPUS": str(config.cpus),
            "TEST_MEMORY": str(config.memory_mb),
            "TEST_DISK_SIZE": str(config.disk_size_gb),
            "VAGRANT_DEFAULT_PROVIDER": "libvirt",
        })
        self.vagrant_env.update(secrets)

        # Run vagrant up with explicit VM name
        try:
            # Stream output to stdout instead of capturing
            result = subprocess.run(
                ["vagrant", "up", self.vm_name],
                cwd=self.vagrant_dir,
                env=self.vagrant_env,
                # capture_output=True,  <-- Disabled to show progress
                text=True,
                timeout=3600,  # 1 hour timeout
            )

            if result.returncode != 0:
                # print(result.stdout) <--- stdout is not captured, so it's already printed
                # print(result.stderr, file=sys.stderr)
                self.debug_ssh_config()
                return False

            return True

        except subprocess.TimeoutExpired:
            self.debug_ssh_config()
            return False
        except Exception:
            self.debug_ssh_config()
            return False

    def offboard(self, offboard_file: str = "mdatp_offboard.json") -> bool:
        """Perform offboarding.

        Args:
            offboard_file: Name of the offboarding JSON file in tests/e2e/

        """
        try:
            # 1. Copy offboarding json to location
            # The file is synced via rsync to /mde_repo/tests/e2e/
            dest = "/etc/opt/microsoft/mdatp/mdatp_offboard.json"
            cmd = f"sudo cp /mde_repo/tests/e2e/{offboard_file} {dest}"

            result = subprocess.run(
                ["vagrant", "ssh", self.vm_name, "-c", cmd],
                cwd=self.vagrant_dir,
                env=self.vagrant_env,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return False

            # 2. Check status (wait a bit for it to process)
            time.sleep(10)

            check_cmd = "mdatp health --field onboarded"
            result = subprocess.run(
                ["vagrant", "ssh", self.vm_name, "-c", check_cmd],
                cwd=self.vagrant_dir,
                env=self.vagrant_env,
                capture_output=True,
                text=True,
                timeout=30,
            )

            output = result.stdout.strip().lower()
            # After offboarding, mdatp might return "false" or a license error
            # (e.g., "attention: no license found"). Either indicates offboarded state.
            # Only "true" means still onboarded.
            if output == "true":
                return False
            if output == "false":
                return True
            # License error or other non-true response indicates offboarded
            return True

        except Exception:
            return False

    def uninstall(self) -> bool:
        """Uninstall MDE."""
        try:
            # Use mde_installer.sh --remove
            # Script location inside VM: /var/lib/mdatp_test/mde_installer.sh
            cmd = "sudo bash /var/lib/mdatp_test/mde_installer.sh --remove"

            result = subprocess.run(
                ["vagrant", "ssh", self.vm_name, "-c", cmd],
                cwd=self.vagrant_dir,
                env=self.vagrant_env,
                capture_output=True, # Capture slightly to avoid noise but print on error?
                text=True,
                timeout=300,
            )

            if result.returncode != 0:
                # Fallback: try direct package removal if script fails?
                # But let's stick to script for consistency
                return False

            # Verify uninstallation
            check_cmd = "command -v mdatp"
            result = subprocess.run(
                ["vagrant", "ssh", self.vm_name, "-c", check_cmd],
                cwd=self.vagrant_dir,
                env=self.vagrant_env,
                capture_output=True,
                text=True,
                timeout=10,
            )

            # If command -v returns 0, mdatp is still there
            return result.returncode != 0

        except Exception:
            return False

    def restart_mdatp(self) -> bool:
        """Restart the mdatp service inside the VM."""
        try:
            result = subprocess.run(
                ["vagrant", "ssh", self.vm_name, "-c", "sudo systemctl restart mdatp"],
                cwd=self.vagrant_dir,
                env=self.vagrant_env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                # Give it a moment to come back up
                time.sleep(5)
                return True
            return False
        except Exception:
            return False

    def check_health(self):
        """Check health inside VM (single attempt)."""
        try:
            result = subprocess.run(
                [
                    "vagrant",
                    "ssh",
                    self.vm_name,
                    "-c",
                    "mdatp health --output json",
                ],
                cwd=self.vagrant_dir,
                env=self.vagrant_env,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0 and result.stdout:
                try:
                    health_json = json.loads(result.stdout)
                    health = HealthChecker.parse_health(health_json)
                    return health, health_json
                except json.JSONDecodeError:
                    return None, None
            else:
                # Debug: show what went wrong
                if result.returncode != 0 and result.stderr:
                    pass
                if not result.stdout:
                    pass

            return None, None

        except subprocess.TimeoutExpired:
            return None, None
        except Exception:
            return None, None

    def get_logs(self, log_files: List[str]) -> Dict[str, str]:
        """Retrieve log files from VM.

        Args:
            log_files: List of log file paths to retrieve

        Returns:
            Dictionary mapping filename -> content

        """
        logs = {}

        for log_file in log_files:
            try:
                result = subprocess.run(
                    [
                        "vagrant",
                        "ssh",
                        self.vm_name,
                        "-c",
                        f"cat {log_file} 2>/dev/null || echo 'Log not found'",
                    ],
                    cwd=self.vagrant_dir,
                    env=self.vagrant_env,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if result.returncode == 0:
                    logs[Path(log_file).name] = result.stdout

            except Exception as e:
                logs[Path(log_file).name] = f"Error retrieving log: {e}"

        return logs

    def destroy(self) -> bool:
        """Destroy the VM."""
        try:
            result = subprocess.run(
                ["vagrant", "destroy", "-f", self.vm_name],
                cwd=self.vagrant_dir,
                env=self.vagrant_env,
                capture_output=True,
                text=True,
                timeout=300,
            )

            return result.returncode == 0

        except Exception:
            return False

    def debug_ssh_config(self):
        """Print SSH config for debugging."""
        with contextlib.suppress(Exception):
            subprocess.run(
                ["vagrant", "ssh-config", self.vm_name],
                cwd=self.vagrant_dir,
                env=self.vagrant_env,
                capture_output=True,
                text=True,
                timeout=10,
            )


class TestRunner:
    """Main test runner."""

    def __init__(self, config_path: str, secrets_path: str):
        """Initialize test runner."""
        self.config_path = Path(config_path)
        self.secrets_path = Path(secrets_path)
        self.config = {}
        self.secrets = {}
        self.results_formatter = ResultsFormatter()
        self.vagrant_dir = Path(__file__).parent / "vagrant"

    def load_config(self) -> bool:
        """Load test configuration."""
        try:
            with open(self.config_path) as f:
                self.config = yaml.safe_load(f)
            return True
        except Exception:
            return False

    def load_secrets(self) -> bool:
        """Load secrets from .env file."""
        if not self.secrets_path.exists():
            return False

        try:
            with open(self.secrets_path) as f:
                for raw_line in f:
                    stripped = raw_line.strip()
                    if not stripped or stripped.startswith("#"):
                        continue
                    if "=" in stripped:
                        key, value = stripped.split("=", 1)
                        self.secrets[key.strip()] = value.strip().strip("'\"")
            return True
        except Exception:
            return False

    def validate_secret_files(self) -> bool:
        """Validate that required secret JSON files exist.

        The .env file should contain paths to the JSON files (relative to tests/e2e/).
        These files are synced to the VM via rsync.
        """
        e2e_dir = Path(__file__).parent

        # Map .env keys to expected filenames
        file_keys = {
            "ONBOARDING_FILE": "onboarding JSON",
            "MANAGED_CONFIG_FILE": "managed config JSON",
        }

        all_valid = True

        for key, _description in file_keys.items():
            if key not in self.secrets:
                all_valid = False
                continue

            file_path = e2e_dir / self.secrets[key]
            if not file_path.exists():
                all_valid = False
            else:
                pass

        # Check offboarding file (optional but needed for uninstall tests)
        if "OFFBOARDING_FILE" in self.secrets:
            offboard_path = e2e_dir / self.secrets["OFFBOARDING_FILE"]
            if offboard_path.exists():
                pass
            else:
                pass

        return all_valid

    def discover_distros(self) -> List[Dict]:
        """Discover distros from mde_installer.sh."""
        repo_root = Path(__file__).parent.parent.parent
        installer_path = repo_root / "linux" / "installation" / "mde_installer.sh"

        if not installer_path.exists():
            return []

        parser = DistroParser(str(installer_path))
        matrix = parser.parse()

        if not matrix:
            return []

        return parser.get_test_matrix()

    def filter_distros(
        self, distros: List[Dict], distro_filter: Optional[str] = None
    ) -> List[Dict]:
        """Filter distros based on configuration and command-line options.

        Args:
            distros: Full distro matrix
            distro_filter: Optional distro filter (distro name, family, or distro:version)

        Returns:
            Filtered distro list

        """
        filtered = distros

        # Apply config file filters
        if self.config.get("distros", {}).get("include"):
            include = self.config["distros"]["include"]
            filtered = [d for d in filtered if d["distro"] in include]

        if self.config.get("distros", {}).get("exclude"):
            exclude = self.config["distros"]["exclude"]
            filtered = [d for d in filtered if d["distro"] not in exclude]

        # Apply command-line filter
        if distro_filter:
            if ":" in distro_filter:
                # distro:version format
                distro, version = distro_filter.split(":", 1)
                filtered = [
                    d for d in filtered if d["distro"] == distro and d["version"] == version
                ]
            elif distro_filter in ["debian", "fedora", "sles", "mariner", "azurelinux"]:
                # Family filter
                filtered = [d for d in filtered if d["family"] == distro_filter]
            else:
                # Distro name filter
                filtered = [d for d in filtered if d["distro"] == distro_filter]

        return filtered

    def run_test(self, test_config: TestConfig) -> TestResult:
        """Run a single test.

        Args:
            test_config: Test configuration

        Returns:
            TestResult

        """
        start_time = time.time()
        vagrant = VagrantRunner(self.vagrant_dir)

        def check_timeout() -> bool:
            """Check if we've exceeded the VM timeout."""
            elapsed = time.time() - start_time
            return elapsed > VM_TIMEOUT_SECONDS

        try:
            # Start VM
            if not vagrant.setup_vm(test_config, self.secrets):
                return TestResult(
                    distro=test_config.distro,
                    version=test_config.version,
                    install_passed=False,
                    onboarding_passed=False,
                    uninstall_passed=False,
                    duration_seconds=time.time() - start_time,
                    failure_reason="Failed to start VM",
                    timestamp=datetime.now().isoformat(),
                )

            # Check timeout after VM startup
            if check_timeout():
                return TestResult(
                    distro=test_config.distro,
                    version=test_config.version,
                    install_passed=False,
                    onboarding_passed=False,
                    uninstall_passed=False,
                    duration_seconds=time.time() - start_time,
                    failure_reason=(
                        f"Timeout: VM setup took longer than {VM_TIMEOUT_SECONDS // 60} minutes"
                    ),
                    timestamp=datetime.now().isoformat(),
                )

            # Wait for health check - 3 attempts with service restart between retries
            max_attempts = 3
            interval = 10  # seconds between retries

            health = None
            for attempt in range(1, max_attempts + 1):
                # Check timeout before each health check attempt
                if check_timeout():
                    timeout_mins = VM_TIMEOUT_SECONDS // 60
                    return TestResult(
                        distro=test_config.distro,
                        version=test_config.version,
                        install_passed=False,
                        onboarding_passed=False,
                        uninstall_passed=False,
                        duration_seconds=time.time() - start_time,
                        failure_reason=f"Timeout: health check exceeded {timeout_mins} min limit",
                        timestamp=datetime.now().isoformat(),
                    )

                health, _health_json = vagrant.check_health()

                if health and health.is_healthy():
                    break

                if attempt < max_attempts:
                    vagrant.restart_mdatp()
                    time.sleep(interval)

            # Determine test status
            install_passed = health is not None
            onboarding_passed = health.onboarded if health else False

            # Offboard and Uninstall steps
            uninstall_passed = False
            offboard_passed = False

            if install_passed:
                # Run Offboarding (get filename from secrets)
                offboard_file = self.secrets.get("OFFBOARDING_FILE", "mdatp_offboard.json")
                offboard_passed = vagrant.offboard(offboard_file)

                # Check health again? Nah, offboard() checks it.

                # Run Uninstall
                if offboard_passed:
                    uninstall_passed = vagrant.uninstall()
                else:
                    pass

            # Collect logs
            logs = {}
            if not install_passed:
                logs_to_get = [
                    "/var/lib/mdatp_test/installer.log",
                    "/var/lib/mdatp_test/managed_apply.log",
                ]
                logs.update(vagrant.get_logs(logs_to_get))

            # Create result
            all_passed = (
                install_passed and onboarding_passed and offboard_passed and uninstall_passed
            )
            return TestResult(
                distro=test_config.distro,
                version=test_config.version,
                install_passed=install_passed,
                onboarding_passed=onboarding_passed,
                uninstall_passed=uninstall_passed,
                duration_seconds=time.time() - start_time,
                failure_reason=None if all_passed else "Test failed",
                timestamp=datetime.now().isoformat(),
                logs=logs or None,
            )


        except Exception as e:
            return TestResult(
                distro=test_config.distro,
                version=test_config.version,
                install_passed=False,
                onboarding_passed=False,
                uninstall_passed=False,
                duration_seconds=time.time() - start_time,
                failure_reason=f"Exception: {e!s}",
                timestamp=datetime.now().isoformat(),
            )

        finally:
            # Destroy VM
            preserve = self.config.get("test", {}).get("preserve_on_failure", False)
            if not preserve:
                vagrant.destroy()

    def run_tests(
        self,
        distros: List[Dict],
        max_concurrent: int = 1,
    ) -> List[TestResult]:
        """Run tests for multiple distros.

        Args:
            distros: List of distro configs
            max_concurrent: Maximum concurrent VMs

        Returns:
            List of TestResult

        """
        results = []

        # Limit concurrency based on resource config
        config_max = self.config.get("vagrant", {}).get("concurrent_vms", 1)
        max_concurrent = min(max_concurrent, config_max)


        if max_concurrent == 1:
            # Sequential execution
            for distro in distros:
                test_config = TestConfig(
                    distro=distro["distro"],
                    version=distro["version"],
                    scaled_version=distro["scaled_version"],
                    family=distro["family"],
                    vagrant_box=distro["vagrant_box"],
                    cpus=self.config["vagrant"]["per_vm"]["cpus"],
                    memory_mb=self.config["vagrant"]["per_vm"]["memory_mb"],
                    disk_size_gb=self.config["vagrant"]["per_vm"]["disk_size_gb"],
                )
                result = self.run_test(test_config)
                results.append(result)
                self.results_formatter.add_result(result)
        else:
            # Parallel execution
            with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
                futures = {}
                for distro in distros:
                    test_config = TestConfig(
                        distro=distro["distro"],
                        version=distro["version"],
                        scaled_version=distro["scaled_version"],
                        family=distro["family"],
                        vagrant_box=distro["vagrant_box"],
                        cpus=self.config["vagrant"]["per_vm"]["cpus"],
                        memory_mb=self.config["vagrant"]["per_vm"]["memory_mb"],
                        disk_size_gb=self.config["vagrant"]["per_vm"]["disk_size_gb"],
                    )
                    future = executor.submit(self.run_test, test_config)
                    futures[future] = distro

                for future in as_completed(futures):
                    result = future.result()
                    results.append(result)
                    self.results_formatter.add_result(result)

        return results

    def save_results(self) -> Dict[str, Path]:
        """Save all results."""
        output_dir = self.config.get("reporting", {}).get("output_dir", "results")
        paths = self.results_formatter.save_all(output_dir)

        if (paths['failures_dir']).exists():
            pass

        return paths

    def print_summary(self):
        """Print summary to stdout."""
        print(self.results_formatter.generate_summary_markdown())


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="E2E test runner for MDE Linux installer"
    )

    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config.yaml",
    )

    parser.add_argument(
        "--secrets",
        default=".env",
        help="Path to .env secrets file",
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all discovered distros",
    )

    parser.add_argument(
        "--distro",
        help="Run specific distro (e.g., 'ubuntu', 'ubuntu:22.04', 'debian')",
    )

    parser.add_argument(
        "--distros",
        help="Run specific distros (comma-separated list)",
    )

    parser.add_argument(
        "--family",
        help="Run all distros in a family (debian, fedora, sles, mariner, azurelinux)",
    )

    parser.add_argument(
        "--cpus",
        type=int,
        help="Override total CPU budget",
    )

    parser.add_argument(
        "--memory",
        type=int,
        help="Override total memory budget (MB)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would run without executing",
    )

    args = parser.parse_args()

    # Initialize runner
    runner = TestRunner(args.config, args.secrets)

    # Load configuration
    if not runner.load_config():
        sys.exit(1)

    # Override resource config if specified
    if args.cpus:
        runner.config["vagrant"]["cpus_total"] = args.cpus

    if args.memory:
        runner.config["vagrant"]["memory_total_mb"] = args.memory

    # Load secrets
    if not runner.load_secrets():
        sys.exit(1)

    # Validate that secret files exist
    if not runner.validate_secret_files():
        sys.exit(1)

    # Discover distros
    all_distros = runner.discover_distros()
    if not all_distros:
        sys.exit(1)


    # Filter distros
    filter_arg = None
    distros = []

    if args.distro:
        filter_arg = args.distro
    elif args.family:
        filter_arg = args.family
    elif args.distros:
        # For multiple distros, we'll filter manually
        distro_list = [d.strip() for d in args.distros.split(",")]
        distros = [d for d in all_distros if d["distro"] in distro_list]
        # Still apply exclude filter from config
        distros = runner.filter_distros(distros, None)
    elif args.all:
        # Apply include/exclude filters from config
        distros = runner.filter_distros(all_distros, None)
    else:
        parser.print_help()
        sys.exit(1)

    if filter_arg:
        distros = runner.filter_distros(all_distros, filter_arg)

    if not distros:
        sys.exit(1)

    for _d in distros:
        pass

    if args.dry_run:
        sys.exit(0)

    # Ensure local boxes are available (build from cloud images if missing)
    scripts_dir = Path(__file__).parent / "scripts"
    box_builder = BoxBuilder(scripts_dir)
    distros = box_builder.ensure_boxes_available(distros)

    if not distros:
        print("❌ No distros available to test after box building", file=sys.stderr)
        sys.exit(1)

    # Run tests

    results = runner.run_tests(distros)

    # Save and print results
    runner.save_results()
    runner.print_summary()

    # Exit with error code if any tests failed
    if any(not r.install_passed for r in results):
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
