#!/usr/bin/env python3
"""distro_parser.py.

Provides a curated distro matrix for e2e testing based on:
1. Official MDE Linux supported platforms
2. Available Vagrant boxes with libvirt support (generic/ boxes)

The matrix is maintained manually to ensure accuracy since parsing
the installer script's complex regex patterns is error-prone.
"""

import sys
from typing import Dict, List

# Distro family mapping (matches mde_installer.sh DISTRO_FAMILY logic)
DISTRO_FAMILIES = {
    "ubuntu": "debian",
    "debian": "debian",
    "rhel": "fedora",
    "centos": "fedora",
    "rocky": "fedora",
    "almalinux": "fedora",
    "ol": "fedora",
    "fedora": "fedora",
    "amzn": "fedora",
    "mariner": "mariner",
    "azurelinux": "azurelinux",
    "sles": "sles",
    "sle-hpc": "sles",
    "sles_sap": "sles",
    "opensuse-leap": "sles",
    "opensuse-tumbleweed": "sles",
}

# Curated distro matrix: distros and versions that:
# 1. Are officially supported by MDE for Linux
# 2. Have available generic/ Vagrant boxes with libvirt support
# Format: distro -> list of (version, scaled_version, vagrant_box)
SUPPORTED_DISTROS = {
    # Ubuntu LTS and interim releases (primary support)
    # Note: generic/ubuntu2404 doesn't exist, so we use cloud-image/ubuntu-24.04
    # Note: Ubuntu 25.x uses alvistack boxes (generic boxes not yet available)
    "ubuntu": [
        ("18.04", "18.04", "generic/ubuntu1804"),
        ("20.04", "20.04", "generic/ubuntu2004"),
        ("22.04", "22.04", "generic/ubuntu2204"),
        ("24.04", "24.04", "cloud-image/ubuntu-24.04"),
        ("25.04", "25.04", "alvistack/ubuntu-25.04"),
        ("25.10", "25.10", "alvistack/ubuntu-25.10"),
    ],
    # Debian stable releases
    # Note: Using local/ boxes converted from official Debian cloud images.
    # The generic/* boxes fail DHCP because they use eth0 in /etc/network/interfaces
    # but libvirt presents the interface as enp1s0 (predictable naming).
    # To create these boxes, run: ./scripts/convert_cloud_image.sh debian <version>
    "debian": [
        ("12", "12", "local/debian12"),  # Bookworm - converted from cloud image
        ("11", "11", "local/debian11"),  # Bullseye - converted from cloud image
        ("10", "10", "local/debian10"),  # Buster (EOL) - converted from cloud image
    ],
    # CentOS Stream (RHEL-compatible)
    # Note: CentOS 7 and 8 removed - mirrorlist.centos.org is EOL
    "centos": [
        ("9", "9", "generic/centos9s"),  # CentOS Stream 9
    ],
    # Rocky Linux (RHEL-compatible, free alternative)
    "rocky": [
        ("8", "8", "generic/rocky8"),
        ("9", "9", "generic/rocky9"),
    ],
    # AlmaLinux (RHEL-compatible, free alternative)
    "almalinux": [
        ("8", "8", "generic/alma8"),
        ("9", "9", "generic/alma9"),
    ],
    # Fedora (uses local/ boxes converted from official cloud images)
    # Note: Fedora scales to version 8 for the RHEL-compatible repo
    # Note: Fedora 40/41/43 use local/ boxes converted from official cloud images
    # because the official fedora/XX-cloud-base Vagrant boxes return 404 on download.
    # To create the boxes, run: ./scripts/convert_cloud_image.sh fedora <version>
    "fedora": [
        ("39", "8", "generic/fedora39"),
        ("40", "8", "local/fedora40"),  # Converted from cloud image (official box 404s)
        ("41", "8", "local/fedora41"),  # Converted from cloud image (official box 404s)
        ("42", "8", "alvistack/fedora-42"),  # alvistack has libvirt support
        ("43", "8", "local/fedora43"),  # Converted from cloud image
    ],
    # Oracle Linux
    "ol": [
        ("8", "8", "generic/oracle8"),
        ("9", "9", "generic/oracle9"),
    ],
    # Amazon Linux (crystax boxes - generic/amazon2 doesn't exist)
    "amzn": [
        ("2", "2", "crystax/amazon2"),
        ("2023", "2023", "crystax/amazon2023"),
    ],
    # SUSE Linux Enterprise Server
    # Note: Removed - generic/sles15 returns 404, box doesn't exist on Vagrant Cloud
    # "sles": [
    #     ("15", "15", "generic/sles15"),
    # ],
    # openSUSE Leap
    # Note: Removed - generic/opensuse15 fails to get DHCP IP with libvirt.
    # Same root cause as Debian boxes. Needs custom image with working network.
    # "opensuse-leap": [
    #     ("15", "15", "generic/opensuse15"),  # DHCP timeout issue
    # ],
    # Azure Linux / Mariner (limited box availability)
    # "mariner": [
    #     ("2", "2", "generic/azurelinux"),
    # ],
}


class DistroParser:
    """Provide curated distro matrix for e2e testing."""

    def __init__(self, installer_path: str = ""):  # noqa: ARG002
        """Initialize parser.

        Args:
            installer_path: Path to mde_installer.sh (unused, kept for API compatibility)

        """
        self.distros: Dict[str, List[tuple]] = SUPPORTED_DISTROS.copy()

    def parse(self) -> Dict[str, List[str]]:
        """Return the curated distro matrix.

        Returns:
            Dictionary mapping distro names to list of versions

        """
        # Return simplified format for backward compatibility
        return {
            distro: [v[0] for v in versions]
            for distro, versions in self.distros.items()
        }

    def get_scaled_version(self, distro: str, version: str) -> str:
        """Get the scaled version for a given distro/version combination.

        Args:
            distro: Distribution name
            version: Version string

        Returns:
            Scaled version string used by MDE packages

        """
        if distro in self.distros:
            for v, scaled, _ in self.distros[distro]:
                if v == version:
                    return scaled
        return version

    def get_vagrant_box(self, distro: str, version: str) -> str:
        """Get the Vagrant box name for a given distro/version.

        Args:
            distro: Distribution name
            version: Version string

        Returns:
            Vagrant box name (e.g., 'generic/ubuntu2204')

        """
        if distro in self.distros:
            for v, _, box in self.distros[distro]:
                if v == version:
                    return box
        return f"generic/{distro}{version}"

    def get_test_matrix(self, exclude_paid: bool = True) -> List[Dict[str, str]]:
        """Get a test matrix of distro/version combinations.

        Args:
            exclude_paid: If True, exclude paid distros (RHEL)

        Returns:
            List of dicts with: {distro, version, scaled_version, family, vagrant_box}

        """
        matrix = []

        for distro, versions in self.distros.items():
            # Skip RHEL (paid) - use Rocky/Alma instead
            if exclude_paid and distro == "rhel":
                continue

            family = DISTRO_FAMILIES.get(distro, distro)

            for version, scaled, box in versions:
                matrix.append({
                    "distro": distro,
                    "version": version,
                    "scaled_version": scaled,
                    "family": family,
                    "vagrant_box": box,
                })

        return sorted(matrix, key=lambda x: (x["distro"], x["version"]))


def main():
    """CLI interface."""
    parser = DistroParser()
    matrix = parser.get_test_matrix()

    if not matrix:
        sys.exit(1)



if __name__ == "__main__":
    main()
