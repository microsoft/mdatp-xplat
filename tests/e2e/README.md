# E2E Test Suite for MDE Linux Installer

This directory contains a complete end-to-end (e2e) testing infrastructure for the Microsoft Defender for Endpoint (MDE) Linux installer using Vagrant and KVM.

## Overview

The test suite:
- **Automatically discovers** all supported Linux distro/version combinations from `mde_installer.sh`
- **Provisions isolated VMs** for each test using Vagrant + libvirt
- **Executes full installation and onboarding** workflows
- **Validates device health** using `mdatp health --output json`
- **Collects logs** and generates detailed reports
- **Supports parallel execution** for faster testing on systems with sufficient resources

## Quick Start

### Prerequisites

- **libvirt** and **KVM** properly configured and running
- **Vagrant** installed with libvirt plugin: `vagrant plugin install vagrant-libvirt`
- **Python 3.8+**
- **PyYAML**: `pip install pyyaml`
- Proper MDE **onboarding and managed config JSON files** as secrets

### Setup

1. **Copy and configure secrets:**
   ```bash
   # Copy your MDE JSON files to the e2e directory
   cp /path/to/your/onboarding.json tests/e2e/mdatp_onboard.json
   cp /path/to/your/managed_config.json tests/e2e/mdatp_managed.json
   cp /path/to/your/offboarding.json tests/e2e/mdatp_offboard.json  # Optional
   ```

2. **Verify configuration:**
   ```bash
   # Review config.yaml - adjust CPU/memory budgets as needed
   cat config.yaml
   ```

3. **Run tests:**
   ```bash
   # Run all discovered distros
   python3 runner.py --all

   # Run single distro
   python3 runner.py --distro ubuntu:22.04

   # Run all Ubuntu versions
   python3 runner.py --family debian

   # Dry run (show what would execute)
   python3 runner.py --all --dry-run

   # With custom resource budget
   python3 runner.py --all --cpus 8 --memory 16384
   ```

## Environment Setup

### Installing libvirt and KVM

#### Fedora / RHEL / Rocky / Alma
```bash
# Install virtualization stack
sudo dnf install -y @virtualization libguestfs-tools

# Enable and start libvirtd
sudo systemctl enable --now libvirtd

# Add your user to libvirt group
sudo usermod -aG libvirt $(whoami)

# Log out and back in for group changes to take effect
```

#### Ubuntu / Debian
```bash
# Install virtualization stack
sudo apt update
sudo apt install -y qemu-kvm libvirt-daemon-system libvirt-clients \
    bridge-utils virtinst libguestfs-tools

# Enable and start libvirtd
sudo systemctl enable --now libvirtd

# Add your user to libvirt and kvm groups
sudo usermod -aG libvirt,kvm $(whoami)

# Log out and back in for group changes to take effect
```

#### Arch Linux
```bash
# Install virtualization stack
sudo pacman -S libvirt qemu-desktop virt-manager dnsmasq libguestfs

# Enable and start libvirtd
sudo systemctl enable --now libvirtd

# Add your user to libvirt group
sudo usermod -aG libvirt $(whoami)
```

### Installing Vagrant with libvirt Plugin

```bash
# Install Vagrant (download from https://www.vagrantup.com/downloads or use package manager)
# Fedora/RHEL:
sudo dnf install -y vagrant

# Ubuntu/Debian:
wget -O /tmp/vagrant.deb https://releases.hashicorp.com/vagrant/2.4.1/vagrant_2.4.1-1_amd64.deb
sudo dpkg -i /tmp/vagrant.deb

# Install the libvirt plugin
vagrant plugin install vagrant-libvirt

# Verify installation
vagrant plugin list | grep libvirt
virsh list --all
```

### Verifying Your Environment

```bash
# Check KVM is available
lsmod | grep kvm

# Check libvirtd is running
systemctl status libvirtd

# Check your user can access libvirt
virsh list --all

# Check Vagrant libvirt plugin
vagrant plugin list

# Run a quick test
vagrant init generic/ubuntu2204
vagrant up --provider=libvirt
vagrant destroy -f
```

## Architecture

### Directory Structure

```
tests/e2e/
├── runner.py                    # Main test orchestrator (entry point)
├── distro_parser.py             # Parses mde_installer.sh for supported distros
├── health_checker.py            # Parses mdatp health JSON output
├── results_formatter.py         # Generates markdown summaries and failure logs
├── config.yaml                  # Test configuration (CPU/memory, timeouts, etc.)
├── mdatp_onboard.json           # MDE onboarding config (git-ignored)
├── mdatp_managed.json           # MDE managed config (git-ignored)
├── mdatp_offboard.json          # MDE offboarding config (git-ignored, optional)
├── scripts/
│   └── convert_cloud_image.sh   # Convert cloud qcow2 images to Vagrant boxes
├── vagrant/
│   ├── Vagrantfile              # Vagrant configuration (VM creation, provider setup)
│   └── templates/
│       ├── provision_debian.sh  # Ubuntu/Debian provisioning
│       ├── provision_rhel.sh    # RHEL/CentOS/Rocky/Fedora/AlmaLinux/OL provisioning
│       ├── provision_sles.sh    # SLES/openSUSE provisioning
│       ├── provision_mariner.sh # Azure Linux (Mariner) provisioning
│       └── provision_azurelinux.sh  # Azure Linux 3.x provisioning
├── results/                     # Generated test results (git-ignored)
│   ├── summary.md               # Markdown summary table
│   ├── results.json             # Detailed JSON results
│   └── failures/                # Individual failure logs
└── README.md                    # This file
```

### Supported Distros

The test suite automatically discovers supported distros from `mde_installer.sh`. Current support includes:

**Debian Family:**
- Ubuntu: 16.04, 18.04, 20.04, 22.04, 24.04, 25.04, 25.10
- Debian: 10, 11, 12, 13

**RHEL Family:**
- Rocky Linux: 8, 9
- AlmaLinux: 8, 9
- CentOS: 7, 8, 9
- Fedora: 38, 39, 40, 41, 42, 43
- Oracle Linux: 8, 9
- Amazon Linux: 2, 2023
- ~~Red Hat Enterprise Linux~~ (use Rocky instead)

**SUSE Family:**
- SLES: 12, 15
- openSUSE Leap: 15
- openSUSE Tumbleweed

**Other:**
- Azure Linux (Mariner): 2.x
- Azure Linux: 3.x

## Building Custom Vagrant Boxes

Some distros don't have pre-built Vagrant boxes with libvirt support on Vagrant Cloud. For these, we provide a conversion script that creates Vagrant boxes from official cloud images.

### Automatic Box Building

**The test runner automatically builds missing local boxes.** When you run tests, the runner:
1. Checks which `local/*` Vagrant boxes are required
2. Detects which ones are missing from your system
3. Automatically runs `convert_cloud_image.sh` to build them
4. Continues with testing once boxes are ready

This means you can run tests immediately without manually pre-building boxes:

```bash
# This will auto-build local/fedora40 if missing, then run the test
python3 runner.py --distro fedora:40
```

The following boxes are automatically built when needed:
- `local/debian10`, `local/debian11`, `local/debian12`
- `local/fedora40`, `local/fedora41`, `local/fedora43`

If a box build fails, that distro is skipped and remaining tests continue.

### Manual Box Building

You can also build boxes manually if preferred:

### When to Build Custom Boxes

You need to build a custom box when:
- No Vagrant box exists for the distro/version on Vagrant Cloud
- Existing boxes only support VirtualBox (not libvirt)
- You want to use official cloud images for security

### Using convert_cloud_image.sh

The script is located at `tests/e2e/scripts/convert_cloud_image.sh`.

#### Prerequisites

```bash
# Fedora/RHEL
sudo dnf install -y libguestfs-tools wget qemu-img

# Ubuntu/Debian
sudo apt install -y libguestfs-tools wget qemu-utils

# Arch
sudo pacman -S libguestfs wget qemu
```

#### Building a Single Image

```bash
cd tests/e2e/scripts

# Build Debian 12 box
./convert_cloud_image.sh debian 12

# Build Fedora 43 box
./convert_cloud_image.sh fedora 43

# Build Debian 11 box
./convert_cloud_image.sh debian 11
```

#### Building All Supported Images

```bash
./convert_cloud_image.sh --all
```

#### What the Script Does

1. **Downloads** the official cloud qcow2 image (e.g., from cloud.debian.org or download.fedoraproject.org)
2. **Customizes** the image using `virt-customize`:
   - Creates `vagrant` user with passwordless sudo
   - Installs the Vagrant insecure SSH public key
   - Configures SSH for Vagrant compatibility
   - Installs essential packages
3. **Packages** the image as a Vagrant box with proper metadata
4. **Registers** the box with Vagrant (`local/debian12`, `local/fedora43`, etc.)

#### Supported Images

Currently supported for conversion:

| Distro | Versions | Box Name |
|--------|----------|----------|
| Debian | 10, 11, 12 | `local/debian10`, `local/debian11`, `local/debian12` |
| Fedora | 43 | `local/fedora43` |

#### Adding New Images

To add support for a new distro/version:

1. Find the official cloud image URL (must be qcow2 format)
2. Edit `convert_cloud_image.sh` and add an entry to `CLOUD_IMAGES`:
   ```bash
   ["distro_version"]="IMAGE_URL|BOX_NAME|CODENAME"
   ```
3. If the distro uses a different package manager than Debian (apt) or Fedora (dnf), create a new customization function

#### Troubleshooting Box Builds

```bash
# Check if box was registered
vagrant box list | grep local

# Remove and rebuild a box
vagrant box remove local/debian12
./convert_cloud_image.sh debian 12

# Verbose mode (see virt-customize output)
./convert_cloud_image.sh debian 12 2>&1 | tee build.log
```

## Configuration

### config.yaml

```yaml
vagrant:
  provider: libvirt                # Only libvirt is supported
  cpus_total: 8                    # Total CPU cores available
  memory_total_mb: 16384           # Total RAM available (16GB)
  concurrent_vms: 4                # Max simultaneous VMs
  per_vm:
    cpus: 1                        # Each VM gets 1 CPU
    memory_mb: 2048                # Each VM gets 2GB RAM
    disk_size_gb: 30               # Disk size per VM

distros:
  include: []                      # Empty = all; specify to test subset
  exclude: []                      # Distros to skip

test:
  preserve_on_failure: false       # Keep VM for debugging if true
  capture_logs: true               # Save installer and system logs
  health_check_interval_sec: 5     # Seconds between health checks
  max_health_check_attempts: 30    # Max retries (5s * 30 = 2.5min timeout)
  tests:
    - install                      # Installation test
    - onboarding                   # Onboarding validation
    - uninstall                    # Uninstall/offboarding (optional)

reporting:
  output_dir: results/             # Where to save results
  summary_format: markdown         # Output format
  timestamp_failures: true         # Timestamp failure logs
```

### Secrets (.env)

Create `.env` from `.env.example`:

```bash
ONBOARDING_JSON='{"onboarding": "json_content"}'
MANAGED_CONFIG_JSON='{"config": "json_content"}'
OFFBOARDING_JSON='{"offboarding": "json_content"}'  # Optional, for uninstall tests
```

**Security Notes:**
- `.env` is git-ignored; never commit it
- Offboarding JSON is the most sensitive secret
- Secrets can be base64-encoded or raw JSON

### Secrets (JSON Files) - Preferred Method

Instead of using `.env`, you can place your MDE configuration files directly in the `tests/e2e/` directory:

```bash
# Required files
tests/e2e/mdatp_onboard.json     # MDE onboarding configuration
tests/e2e/mdatp_managed.json     # MDE managed configuration

# Optional file (for offboarding tests)
tests/e2e/mdatp_offboard.json    # MDE offboarding configuration
```

These files are automatically git-ignored. Simply copy your actual MDE JSON files:

```bash
cd tests/e2e
cp /path/to/your/WindowsDefenderATPOnboardingPackage/mdatp_onboard.json .
cp /path/to/your/managed_config.json mdatp_managed.json
```

**Security Notes:**
- All `mdatp_*.json` files are git-ignored
- Offboarding JSON is the most sensitive secret (can offboard devices)
- Never commit these files to version control

## Usage Examples

### Run All Tests

```bash
python3 runner.py --all
# Output: summary.md + results.json + failure logs
```

### Test Specific Distro

```bash
# Single version
python3 runner.py --distro ubuntu:22.04

# All versions of a distro
python3 runner.py --distro ubuntu

# All distros in a family
python3 runner.py --family debian
python3 runner.py --family fedora
```

### Multiple Distros

```bash
python3 runner.py --distros ubuntu:22.04,debian:12,rocky:9
```

### Resource Configuration

```bash
# Use custom CPU/memory budget
python3 runner.py --all --cpus 4 --memory 8192

# Sequential testing (one VM at a time)
python3 runner.py --all --cpus 1 --memory 2048
```

### Dry Run

```bash
# Show what would run without executing
python3 runner.py --all --dry-run
```

### Debugging

```bash
# Keep failed VMs for manual inspection
# Edit config.yaml: preserve_on_failure: true
# Then run tests and inspect VM:
vagrant ssh

# View failure logs
cat results/failures/*.log
```

## Test Execution Flow

For each test:

1. **VM Provisioning**
   - Create Vagrant VM with specified distro/version
   - Configure libvirt provider (1 CPU, 2GB RAM, 30GB disk)
   - Sync repo via rsync

2. **System Setup**
   - Update OS packages
   - Install dependencies (curl, wget, gpg, ca-certificates, etc.)
   - Copy MDE installer script and secrets into VM

3. **Installation**
   - Run `mde_installer.sh --install` with onboarding JSON
   - Apply managed configuration via `mdatp config merge`
   - Capture installer and system logs

4. **Health Validation**
   - Poll `mdatp health --output json` (up to 30 attempts, 5s intervals)
   - Verify daemon is running
   - Verify device is onboarded
   - Verify threat definitions are updated

5. **Results Collection**
   - Record pass/fail status
   - Collect system logs on failure
   - Clean up VM (unless `preserve_on_failure: true`)

6. **Reporting**
   - Generate markdown summary with status table
   - Save JSON results with details
   - Archive failure logs with timestamps

## Output

### Summary Table (results/summary.md)

```markdown
| Distro  | Version | Install | Onboard | Uninstall | Duration | Status   |
|---------|---------|---------|---------|-----------|----------|----------|
| ubuntu  | 22.04   | ✅      | ✅      | ✅        | 145.2s   | PASSED   |
| rocky   | 9       | ❌      | ❌      | -         | 89.5s    | FAILED   |
```

### Failure Logs (results/failures/)

Each failure is logged with:
- Test metadata (distro, version, timestamp)
- Failure reason
- Captured installer output
- System logs

### JSON Results (results/results.json)

```json
{
  "generated": "2025-01-26T10:30:00",
  "summary": {"total": 15, "passed": 14, "failed": 1},
  "results": [
    {
      "distro": "ubuntu",
      "version": "22.04",
      "install_passed": true,
      "onboarding_passed": true,
      "duration_seconds": 145.2
    }
  ]
}
```

## Viewing Results

Test results are saved to the `results/` directory after each test run.

### Quick Summary

```bash
# View the summary table
cat results/summary.md

# Example output:
# | Distro  | Version | Install | Onboard | Uninstall | Duration | Status |
# |---------|---------|---------|---------|-----------|----------|--------|
# | ubuntu  | 22.04   | ✅      | ✅      | ✅        | 145.2s   | PASSED |
# | rocky   | 9       | ❌      | ❌      | -         | 89.5s    | FAILED |
```

### Using results_formatter.py

The `results_formatter.py` module provides utilities for generating and parsing test results:

```bash
# Regenerate summary from existing results.json
python3 results_formatter.py

# View detailed JSON results
python3 -c "import json; print(json.dumps(json.load(open('results/results.json')), indent=2))"
```

### Understanding Result Files

| File | Description |
|------|-------------|
| `results/summary.md` | Markdown table with pass/fail status for each distro |
| `results/results.json` | Detailed JSON with timing, health data, and errors |
| `results/failures/*.log` | Individual failure logs with full output |

### Filtering Results

```bash
# Show only failed tests
grep "❌\|FAILED" results/summary.md

# Count passed/failed
grep -c "PASSED" results/summary.md
grep -c "FAILED" results/summary.md

# View a specific failure log
ls results/failures/
cat results/failures/ubuntu-22.04-*.log
```

## Troubleshooting

### Vagrant/libvirt Issues

```bash
# Verify libvirt is running
virsh list --all

# Check Vagrant logs
export VAGRANT_LOG=debug
python3 runner.py --distro ubuntu:22.04

# Clean up stale VMs (simple)
vagrant global-status --prune
vagrant destroy -f
```

### Cleaning Up After Interrupted Tests

If a test is interrupted (Ctrl+C, system crash, etc.), VMs and state can be left behind in multiple locations. Use the cleanup script to remove all dangling resources:

```bash
# Preview what will be cleaned (dry run)
./scripts/cleanup_vms.sh --dry-run

# Interactive cleanup (prompts before each action)
./scripts/cleanup_vms.sh

# Force cleanup without prompts
./scripts/cleanup_vms.sh --force
```

The cleanup script checks and cleans:
- **Libvirt domains** (`qemu:///system`) - running or stopped VMs
- **Libvirt domain configs** (`/etc/libvirt/qemu/mde-*.xml`) - orphaned XML definitions
- **Libvirt disk images** (`/var/lib/libvirt/images/mde-*.img`) - orphaned disk files
- **Vagrant state** (`.vagrant/machines/`) - stale machine state

**Note:** The script requires `sudo` for some operations (removing libvirt configs and images).

### Health Check Failures

```bash
# Increase health check attempts in config.yaml
max_health_check_attempts: 60  # Was 30

# Keep VM for manual debugging
# In config.yaml: preserve_on_failure: true
# SSH into VM and check:
cd vagrant && vagrant ssh
mdatp health --output json
tail -f /var/log/mdatp_installer.log
```

### Secrets Not Found

```bash
# Verify JSON files exist
ls -la tests/e2e/mdatp_*.json

# Verify they contain valid JSON
python3 -c "import json; json.load(open('mdatp_onboard.json'))"
python3 -c "import json; json.load(open('mdatp_managed.json'))"

# Check files are in gitignore
grep "mdatp_" ../../.gitignore
```

### Box Not Found Errors

```bash
# List available boxes
vagrant box list

# Check if you need to build a custom box
./scripts/convert_cloud_image.sh --list

# Build missing custom box (e.g., Fedora 43)
./scripts/convert_cloud_image.sh fedora 43
```

## Development

### Adding Support for New Distro

1. **Check Vagrant Cloud** for an existing box with libvirt support:
   ```bash
   # Search on https://app.vagrantup.com/boxes/search
   # Or check API:
   curl -s "https://app.vagrantup.com/api/v2/box/OWNER%2FBOX" | jq '.versions[0].providers[].name'
   ```

2. **Update distro_parser.py** with the Vagrant box mapping:
   ```python
   "distro": [
       ("version", "scaled_version", "box/name"),
   ],
   ```

3. **If no libvirt box exists**, add to `convert_cloud_image.sh`:
   - Find the cloud image URL (must be qcow2)
   - Add entry to `CLOUD_IMAGES` array
   - Build the box: `./convert_cloud_image.sh distro version`

4. **Create/update provisioning template** if needed at `vagrant/templates/provision_FAMILY.sh`

5. **Test the new distro**:
   ```bash
   python3 runner.py --distro newdistro:version
   ```

### Running Individual Modules

```bash
# Test distro parser - see all discovered distros
python3 distro_parser.py | jq .

# Test health checker (requires mdatp installed on local system)
python3 health_checker.py

# Test results formatter - regenerate summary
python3 results_formatter.py

# View runner help
python3 runner.py --help
```

## CI/CD Integration (Future)

This test suite is designed for **local execution only**. For cloud-based CI/CD, a separate solution will be needed due to licensing and infrastructure constraints.

## Performance Notes

- **Sequential testing** (1 VM): ~2.5-3 minutes per distro
- **Parallel testing** (4 VMs): ~30-40 minutes for full matrix
- **Resource requirements**: 8 CPU cores, 16GB RAM minimum for 4 concurrent VMs

## Security Considerations

- Secrets are never logged or printed
- Failed VMs are destroyed by default (use `preserve_on_failure: true` for debugging only)
- Test VMs are isolated via libvirt
- Logs containing sensitive data are only stored locally

## Related Documentation

- [mde_installer.sh Usage](../../linux/installation/README.md)
- [MDE Health Command](https://learn.microsoft.com/en-us/defender-endpoint/linux-resources-linux-mdatp-data-storage)
- [Vagrant Documentation](https://www.vagrantup.com/docs)
- [libvirt Provider](https://github.com/vagrant-libvirt/vagrant-libvirt)
