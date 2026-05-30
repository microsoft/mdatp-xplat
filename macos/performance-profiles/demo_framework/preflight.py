"""
Preflight checks for demo prerequisites.
"""

import subprocess
import sys
from pathlib import Path
from typing import List, Optional


class PreflightError(Exception):
    """Raised when preflight check fails."""
    pass


class Preflight:
    """Check system prerequisites before running demo."""

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
                ["mdatp", "performance-profiles", "list"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return len([line for line in result.stdout.split("\n") if line.strip()])
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

    def run_all(self, required_major_node: int = 24) -> bool:
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

        # Check Homebrew
        if not self.check_command_exists("brew"):
            print("❌ Homebrew not found. Install it: https://brew.sh")
            return False

        print("   ✅ Homebrew: OK")

        # Check build tools
        missing_tools = []
        for cmd in ["git", "jq", "python3"]:
            if not self.check_command_exists(cmd):
                missing_tools.append(cmd)

        if missing_tools and not self.install_missing_tools(missing_tools):
            return False

        print("   ✅ Build tools: git, jq, python3")

        # Check Node.js version
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
        print()
        return True
