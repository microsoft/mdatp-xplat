#!/bin/bash
# tests/e2e/vagrant/templates/provision_debian.sh
# Provisioning script for Ubuntu/Debian systems

set -euo pipefail

DISTRO="${1:-ubuntu}"
VERSION="${2:-22.04}"
SCALED_VERSION="${TEST_SCALED_VERSION:-$VERSION}"
REPO_PATH="/mde_repo"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

# Update package cache and upgrade packages for a realistic system state
log_info "Updating package cache..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq

# Check if this is a problematic older box (generic/ubuntu2004 has broken initramfs due to disk layout)
# The test is: can we successfully regenerate initramfs? If not, skip all upgrades.
SKIP_UPGRADES=false

# Check /boot space - either as separate partition or within root
if mountpoint -q /boot 2>/dev/null; then
    BOOT_AVAIL_MB=$(df -BM /boot 2>/dev/null | awk 'NR==2 {gsub(/M/, "", $4); print $4}')
    if [[ "$BOOT_AVAIL_MB" -lt 100 ]]; then
        log_warn "/boot has only ${BOOT_AVAIL_MB}MB free - skipping upgrades"
        SKIP_UPGRADES=true
    fi
else
    # /boot is not a separate partition, check root filesystem  
    # On generic/ubuntu2004, the initramfs compression still fails even with plenty of space
    # This is a known issue with older LZ4 compression settings
    ROOT_AVAIL_MB=$(df -BM / 2>/dev/null | awk 'NR==2 {gsub(/M/, "", $4); print $4}')
    if [[ "$ROOT_AVAIL_MB" -lt 500 ]]; then
        log_warn "Root filesystem has only ${ROOT_AVAIL_MB}MB free - skipping upgrades"
        SKIP_UPGRADES=true
    fi
fi

# For Ubuntu 20.04 specifically, the generic box has known initramfs issues
# Check if we're on an older kernel that's likely to have update problems
KERNEL_VERSION=$(uname -r)
if [[ "$DISTRO" == "ubuntu" && "$VERSION" == "20.04" ]] && [[ "$KERNEL_VERSION" =~ 5\.4\.0-(4[0-9]|1[0-6][0-9])-generic ]]; then
    log_warn "Detected old Ubuntu 20.04 kernel ($KERNEL_VERSION) - skipping upgrades to avoid initramfs failures"
    SKIP_UPGRADES=true
fi

if [[ "$SKIP_UPGRADES" == "true" ]]; then
    log_info "Skipping system upgrades for this box due to known issues"
    # Just install security updates for critical packages, avoiding kernel-related triggers
    apt-mark hold linux-image-* linux-headers-* linux-modules-* initramfs-tools* 2>/dev/null || true
else
    # Clean up old kernels to free /boot space
    log_info "Cleaning up old kernels to free /boot space..."
    apt-get autoremove --purge -y -qq 2>/dev/null || true
    
    # Upgrade all packages - this ensures we're testing on a realistic, up-to-date system
    log_info "Upgrading system packages (this may take a few minutes)..."
    apt-get upgrade -y -qq
fi

# Install dependencies
log_info "Installing dependencies..."
apt-get install -y -qq \
    curl \
    wget \
    gpg \
    lsb-release \
    gnupg \
    ca-certificates \
    apt-transport-https

# Set up working directory
WORK_DIR="/tmp/mde_test"
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

# Copy installer script
log_info "Setting up test environment..."
cp "$REPO_PATH/linux/installation/mde_installer.sh" .
chmod +x mde_installer.sh

# Copy secrets from synced repo (already in tests/e2e/)
E2E_DIR="$REPO_PATH/tests/e2e"

if [[ ! -f "$E2E_DIR/mdatp_onboard.json" ]]; then
    log_error "mdatp_onboard.json not found in $E2E_DIR"
    exit 1
fi

cp "$E2E_DIR/mdatp_onboard.json" onboarding.json
chmod 600 onboarding.json
log_info "Copied onboarding.json"

if [[ -f "$E2E_DIR/mdatp_managed.json" ]]; then
    cp "$E2E_DIR/mdatp_managed.json" managed.json
    chmod 600 managed.json
    log_info "Copied managed.json"
fi

# Create test directory
TEST_DIR="/var/lib/mdatp_test"
mkdir -p "$TEST_DIR"
cd "$TEST_DIR"

# Copy files
cp "$WORK_DIR/mde_installer.sh" .
cp "$WORK_DIR/onboarding.json" .
if [[ -f "$WORK_DIR/managed.json" ]]; then
    cp "$WORK_DIR/managed.json" .
fi

# Run installer
log_info "Running MDE installer for $DISTRO $VERSION (scaled: $SCALED_VERSION)..."
if ! sudo bash mde_installer.sh \
    --install \
    --channel prod \
    --onboard onboarding.json \
    2>&1 | tee installer.log; then
    log_error "Installation failed"
    cat installer.log >&2
    exit 1
fi

log_info "Installation completed successfully"

# Apply managed config if provided
if [[ -f managed.json ]]; then
    log_info "Applying managed configuration..."
    if ! mdatp config merge --input managed.json 2>&1 | tee managed_apply.log; then
        log_warn "Failed to apply managed configuration"
    fi
fi

# Health check
log_info "Checking MDE health..."
sleep 5
if ! mdatp health --output json > health_check.json 2>&1; then
    log_warn "Health check command may have failed, checking JSON..."
fi

if [[ -f health_check.json ]]; then
    cat health_check.json
fi

log_info "Provisioning completed"
