"""
Preflight checks for demo prerequisites.
"""

import subprocess
import sys
import shutil
from pathlib import Path
from typing import List, Optional


class PreflightError(Exception):
    """Raised when preflight check fails."""
    pass


class Preflight:
    """Check system prerequisites before running demo."""

    DEFAULT_ANALYZER_DIR = Path.home() / "demo" / "analyzer" / "XMDEClientAnalyzerBinary"
    DEFAULT_ANALYZER_BIN = DEFAULT_ANALYZER_DIR / "mde_support_tool.sh"

    @staticmethod
    def check_command_exists(cmd: str) -> bool:
        """Check if a command is available in PATH."""
        result = subprocess.run(
            ["which", cmd],
            capture_output=True
        )
        return result.returncode == 0

    @staticmethod
    def get_version(cmd: str) -> str:
        """Get version of a command."""
        try:
            result = subprocess.run(
                [cmd, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.stdout.strip() or result.stderr.strip()
        except:
            return "unknown"

    @staticmethod
    def check_mdatp() -> bool:
        """Check if MDE is installed."""
        return Preflight.check_command_exists("mdatp")

    @staticmethod
    def check_mdatp_rtp() -> bool:
        """Check if MDE real-time protection is enabled."""
        try:
            result = subprocess.run(
                ["mdatp", "health", "--field", "real_time_protection_enabled"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0 and "true" in result.stdout.lower()
        except:
            return False

    @staticmethod
    def check_mdatp_profiles() -> int:
        """Get count of available MDE profiles."""
        try:
            result = subprocess.run(
                ["mdatp", "performance-profiles", "list-available"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                lines = [line.strip() for line in result.stdout.split("\n") if line.strip()]
                # Output shape is profile names separated by --- lines.
                profiles = [line for line in lines if line != "---" and line != "====================================="]
                return len(profiles)
            return 0
        except:
            return 0

    @staticmethod
    def check_xcode_clt() -> bool:
        """Check if Xcode Command Line Tools are installed."""
        result = subprocess.run(
            ["xcode-select", "-p"],
            capture_output=True
        )
        return result.returncode == 0

    @staticmethod
    def check_full_xcode() -> bool:
        """Return True only when a full Xcode.app installation is active.

        Command Line Tools alone are insufficient for Swift macro plugins
        (e.g. #Preview) used by projects like FluentUI Apple.
        """
        result = subprocess.run(
            ["xcode-select", "-p"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False
        dev_dir = result.stdout.strip()
        # CLT path is /Library/Developer/CommandLineTools; full Xcode is under
        # /Applications/Xcode*.app or wherever it was placed.
        return "CommandLineTools" not in dev_dir

    @staticmethod
    def check_node_version(required_major: int = 24) -> Optional[str]:
        """Check Node.js version. Returns version string if OK, None if too old."""
        try:
            result = subprocess.run(
                ["node", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                version_str = result.stdout.strip()  # e.g., "v24.16.0"
                major = int(version_str.split(".")[0].lstrip("v"))
                if major >= required_major:
                    return version_str
            return None
        except:
            return None

    @staticmethod
    def install_node_homebrew() -> bool:
        """Install Node.js v24 via Homebrew."""
        print("   ⬇️  Installing Node.js v24 via Homebrew...")
        try:
            # Try install first
            result = subprocess.run(
                ["brew", "install", "node@24"],
                capture_output=False,
                timeout=300
            )
            if result.returncode != 0:
                # Try upgrade if already installed
                result = subprocess.run(
                    ["brew", "upgrade", "node@24"],
                    capture_output=False,
                    timeout=300
                )
            
            # Link it
            subprocess.run(
                ["brew", "link", "node@24", "--force", "--overwrite"],
                capture_output=True,
                timeout=60
            )
            
            return True
        except Exception as e:
            print(f"   ⚠️  Installation failed: {e}")
            return False

    @staticmethod
    def install_missing_tools(tools: List[str]) -> bool:
        """Install missing tools via Homebrew."""
        if not tools:
            return True

        print(f"   ⚠️  Missing tools: {', '.join(tools)}")
        answer = input("   Install via Homebrew? [Y/n] ").strip().lower()
        
        if answer in ("n", "no"):
            print("   Please install the missing tools and re-run the script.")
            return False

        for tool in tools:
            print(f"   ⬇️  Installing {tool}...")
            result = subprocess.run(["brew", "install", tool], capture_output=False)
            if result.returncode != 0:
                print(f"   ⚠️  Failed to install {tool}")
                return False

        return True

    @staticmethod
    def find_client_analyzer_binary(install_dir: Optional[Path] = None) -> Optional[Path]:
        """Find Client Analyzer entrypoint in expected install locations."""
        target = (install_dir or Preflight.DEFAULT_ANALYZER_DIR).expanduser()

        candidates = [
            target / "mde_support_tool.sh",
            target / "MDESupportTool",
            target / "ClientAnalyzer" / "mde_support_tool.sh",
            target / "ClientAnalyzer" / "MDESupportTool",
        ]

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate

        if target.exists():
            for name in ("mde_support_tool.sh", "MDESupportTool"):
                for found in target.rglob(name):
                    if found.is_file():
                        return found

        return None

    @staticmethod
    def install_client_analyzer(install_dir: Optional[Path] = None) -> bool:
        """Download and install XMDE Client Analyzer into install_dir."""
        target = (install_dir or Preflight.DEFAULT_ANALYZER_DIR).expanduser()
        parent = target.parent
        parent.mkdir(parents=True, exist_ok=True)

        if not Preflight.check_command_exists("curl"):
            print("   ⚠️  curl is required to download Client Analyzer")
            if not Preflight.install_missing_tools(["curl"]):
                return False

        if not Preflight.check_command_exists("unzip"):
            print("   ⚠️  unzip is required to extract Client Analyzer")
            if not Preflight.install_missing_tools(["unzip"]):
                return False

        zip_path = parent / "XMDEClientAnalyzer.zip"
        extract_dir = parent / "_analyzer_extract"

        print("   ⬇️  Downloading XMDE Client Analyzer...")
        try:
            dl = subprocess.run(
                ["curl", "-L", "-o", str(zip_path), "https://aka.ms/XMDEClientAnalyzerBinary"],
                timeout=300,
                capture_output=False,
            )
            if dl.returncode != 0:
                print("   ⚠️  Download failed")
                return False

            if extract_dir.exists():
                subprocess.run(["rm", "-rf", str(extract_dir)], check=False)
            extract_dir.mkdir(parents=True, exist_ok=True)

            uz = subprocess.run(
                ["unzip", "-o", str(zip_path), "-d", str(extract_dir)],
                timeout=120,
                capture_output=False,
            )
            if uz.returncode != 0:
                print("   ⚠️  Extraction failed")
                return False

            # Current package format ships a nested SupportToolMacOSBinary.zip
            # under XMDEClientAnalyzer/. Extract it in place so the rest of the
            # detection logic below can find the entrypoint regardless of which
            # package layout we received.
            for nested_zip in extract_dir.rglob("SupportToolMacOSBinary.zip"):
                nested_out = nested_zip.parent / "macos_bin"
                if nested_out.exists():
                    shutil.rmtree(nested_out, ignore_errors=True)
                nested_out.mkdir(parents=True, exist_ok=True)
                nz = subprocess.run(
                    ["unzip", "-o", str(nested_zip), "-d", str(nested_out)],
                    timeout=120,
                    capture_output=False,
                )
                if nz.returncode != 0:
                    print("   ⚠️  Failed to extract SupportToolMacOSBinary.zip")
                    return False

            # New package format: mde_support_tool.sh + mde_tools directory.
            wrapper = next(iter(extract_dir.rglob("mde_support_tool.sh")), None)
            mde_tools_dir = next(iter(extract_dir.rglob("mde_tools")), None)
            if wrapper and wrapper.is_file() and mde_tools_dir and mde_tools_dir.is_dir():
                wrapper_root = wrapper.parent
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)
                shutil.copytree(wrapper_root, target)

                final_bin = target / "mde_support_tool.sh"
                subprocess.run(["chmod", "+x", str(final_bin)], timeout=10, check=False)
                if Preflight.check_command_exists("xattr"):
                    subprocess.run(["xattr", "-cr", str(target)], timeout=15, check=False)

                print(f"   ✅ Client Analyzer installed: {final_bin}")
                return True

            # Legacy package format: standalone MDESupportTool binary.
            found = None
            for candidate in extract_dir.rglob("MDESupportTool"):
                if candidate.is_file():
                    found = candidate
                    break

            if not found:
                print("   ⚠️  Client Analyzer entrypoint not found after extraction")
                return False

            target.mkdir(parents=True, exist_ok=True)
            final_bin = target / "MDESupportTool"
            cp = subprocess.run(["cp", str(found), str(final_bin)], timeout=30, capture_output=False)
            if cp.returncode != 0:
                print("   ⚠️  Failed to place MDESupportTool in install path")
                return False

            subprocess.run(["chmod", "+x", str(final_bin)], timeout=10, check=False)
            if Preflight.check_command_exists("xattr"):
                subprocess.run(["xattr", "-cr", str(final_bin)], timeout=15, check=False)

            print(f"   ✅ Client Analyzer installed: {final_bin}")
            return True
        except Exception as e:
            print(f"   ⚠️  Client Analyzer install failed: {e}")
            return False
        finally:
            try:
                if zip_path.exists():
                    zip_path.unlink()
            except Exception:
                pass
            try:
                if extract_dir.exists():
                    subprocess.run(["rm", "-rf", str(extract_dir)], check=False)
            except Exception:
                pass

    def run_all(
        self,
        required_major_node: int = 24,
        require_node: bool = True,
        require_xcode: bool = False,
        require_client_analyzer: bool = False,
        require_ghcp_cli: bool = False,
        client_analyzer_dir: Optional[Path] = None,
    ) -> bool:
        """Run all preflight checks. Returns True if all pass."""
        print("🔍 Preflight checks...\n")

        # Check MDE
        if not self.check_mdatp():
            print("❌ mdatp not found. Install MDE first.")
            return False

        print("   ✅ MDE installed")

        # Check RTP
        if not self.check_mdatp_rtp():
            print("❌ MDE real-time protection is not enabled.")
            return False

        print("   ✅ Real-time protection: ON")

        # Check profiles
        profile_count = self.check_mdatp_profiles()
        if profile_count == 0:
            print("❌ No performance profiles available.")
            return False

        print(f"   ✅ Profiles available: {profile_count}")

        # Check Xcode CLT
        if not self.check_xcode_clt():
            print("   ⚠️  Xcode Command Line Tools not found.")
            print("   Installing (this may take a few minutes)...")
            try:
                subprocess.run(["xcode-select", "--install"], capture_output=True, timeout=300)
                print("   After installation completes, re-run this script.")
            except:
                pass
            return False

        print("   ✅ Xcode Command Line Tools: OK")

        # Full Xcode.app required for Swift macro plugins (#Preview etc.)
        if require_xcode and not self.check_full_xcode():
            print("❌ Full Xcode.app is required for this scenario but the active")
            print("   developer directory is Command Line Tools only.")
            print("   Fix: install Xcode from the App Store, then run:")
            print("     sudo xcode-select -s /Applications/Xcode.app/Contents/Developer")
            return False

        if require_xcode:
            print("   ✅ Full Xcode.app: OK")

        # Check Homebrew
        if not self.check_command_exists("brew"):
            print("❌ Homebrew not found. Install it: https://brew.sh")
            return False

        print("   ✅ Homebrew: OK")

        # Check build tools
        missing_tools = []
        required_tools = ["git", "jq", "python3"]
        if require_node:
            required_tools.append("node")

        for cmd in required_tools:
            if not self.check_command_exists(cmd):
                missing_tools.append(cmd)

        if missing_tools and not self.install_missing_tools(missing_tools):
            return False

        print(f"   ✅ Build tools: {', '.join(required_tools)}")

        # Check Node.js version for Node-based scenarios only
        if require_node:
            node_version = self.check_node_version(required_major_node)
            if node_version is None:
                current = self.get_version("node")
                print(f"   ⚠️  Node.js v{required_major_node}+ required, but found {current}")
                answer = input("   Install Node.js v24 via Homebrew? [Y/n] ").strip().lower()

                if answer in ("n", "no"):
                    print(f"   Please install Node.js v{required_major_node}+ and re-run the script.")
                    print("   Options:")
                    print("     - nvm install 24 && nvm use 24")
                    print("     - Or download from: https://nodejs.org")
                    return False

                if not self.install_node_homebrew():
                    return False

                # Re-check
                node_version = self.check_node_version(required_major_node)
                if node_version is None:
                    print("   ⚠️  Installation complete, but Node.js v24 not yet active.")
                    print("   Please re-run this script.")
                    return False

            print(f"   ✅ Node.js: {node_version}")

        # Optional required prerequisite for richer diagnostics.
        analyzer = self.find_client_analyzer_binary(client_analyzer_dir)
        if analyzer:
            print(f"   ✅ Client Analyzer: {analyzer}")
        elif require_client_analyzer:
            print("   ⚠️  Client Analyzer required but not found.")
            answer = input("   Download and install Client Analyzer now? [Y/n] ").strip().lower()
            if answer in ("n", "no"):
                print("   Please install Client Analyzer and re-run.")
                print("   Note: this integration is validated with the latest package from")
                print("   https://aka.ms/XMDEClientAnalyzerBinary; older package layouts may differ.")
                return False
            if not self.install_client_analyzer(client_analyzer_dir):
                print("   Note: this integration is validated with the latest package from")
                print("   https://aka.ms/XMDEClientAnalyzerBinary; older package layouts may differ.")
                return False
            analyzer = self.find_client_analyzer_binary(client_analyzer_dir)
            if not analyzer:
                print("   ⚠️  Client Analyzer install completed, but binary was not found.")
                print("   Note: this integration is validated with the latest package from")
                print("   https://aka.ms/XMDEClientAnalyzerBinary; older package layouts may differ.")
                return False
            print(f"   ✅ Client Analyzer: {analyzer}")
        else:
            print("   ℹ️  Client Analyzer: not found (optional)")

        # Optional required prerequisite for GHCP-assisted recommendations/analysis.
        ghcp_ok = self.check_ghcp_cli()
        if ghcp_ok:
            print("   ✅ GitHub Copilot CLI: available")
        elif require_ghcp_cli:
            print("   ⚠️  GitHub Copilot CLI required but not found.")
            answer = input("   Install GitHub Copilot CLI now? [Y/n] ").strip().lower()
            if answer in ("n", "no"):
                print("   Please install GitHub Copilot CLI and re-run.")
                return False
            if not self.install_ghcp_cli():
                return False
            if not self.check_ghcp_cli():
                print("   ⚠️  GitHub Copilot CLI install completed, but command is still unavailable.")
                return False
            print("   ✅ GitHub Copilot CLI: available")
        else:
            print("   ℹ️  GitHub Copilot CLI: not found (optional)")
        print()
        return True

    @staticmethod
    def check_ghcp_cli() -> bool:
        """Check if a working GitHub Copilot CLI binary is available."""
        copilot_bin = shutil.which("copilot")
        if not copilot_bin:
            return False

        try:
            result = subprocess.run(
                [copilot_bin, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            output = ((result.stdout or "") + "\n" + (result.stderr or "")).lower()
            if result.returncode != 0:
                return False
            if "cannot find github copilot cli" in output:
                return False
            return "github copilot cli" in output
        except Exception:
            return False

    @staticmethod
    def install_ghcp_cli() -> bool:
        """Install GitHub Copilot CLI via Homebrew."""
        print("   ⬇️  Installing GitHub Copilot CLI via Homebrew...")
        try:
            result = subprocess.run(
                ["brew", "install", "copilot-cli"],
                capture_output=True,
                text=True,
                timeout=300,
            )
            combined = (result.stdout or "") + (result.stderr or "")
            if result.stdout:
                sys.stdout.write(result.stdout)
            if result.stderr:
                sys.stderr.write(result.stderr)

            if result.returncode == 0:
                return True

            # Common case: a non-Homebrew `copilot` binary (e.g. from
            # `npm i -g @github/copilot`) already occupies the link target.
            # If that binary already satisfies our check, accept it instead
            # of forcing the cask install.
            if "already a Binary at" in combined or "already an App at" in combined:
                if Preflight.check_ghcp_cli():
                    print("   ✅ Existing GitHub Copilot CLI detected; skipping Homebrew install.")
                    return True
                print("   ⚠️  A non-Homebrew `copilot` binary is blocking the install.")
                print("       Remove it (e.g. `npm uninstall -g @github/copilot` or")
                print("       `rm /opt/homebrew/bin/copilot`) and rerun, or install with")
                print("       `brew install --force copilot-cli`.")
                return False

            # Fall back to upgrade only when the cask is actually installed.
            installed = subprocess.run(
                ["brew", "list", "--cask", "copilot-cli"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if installed.returncode == 0:
                upgrade = subprocess.run(
                    ["brew", "upgrade", "--cask", "copilot-cli"],
                    capture_output=False,
                    timeout=300,
                )
                return upgrade.returncode == 0

            return False
        except Exception as e:
            print(f"   ⚠️  GHCP CLI install failed: {e}")
            return False
