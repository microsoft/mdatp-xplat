#!/bin/bash
# tests/e2e/vagrant/templates/provision_azurelinux.sh
# Provisioning script for Azure Linux systems

set -euo pipefail

DISTRO="${1:-azurelinux}"
VERSION="${2:-3}"
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

# Update system
log_info "Updating system..."
dnf update -y -q

# Install dependencies
log_info "Installing dependencies..."
dnf install -y -q \
    curl \
    wget \
    gnupg2 \
    ca-certificates

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
