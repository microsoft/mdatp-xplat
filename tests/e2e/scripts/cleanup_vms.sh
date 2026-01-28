#!/bin/bash
# cleanup_vms.sh - Comprehensive cleanup of all MDE test VMs
#
# This script cleans up dangling VMs from interrupted e2e tests.
# It checks all locations where VM state can persist:
#   1. Libvirt domains (qemu:///system)
#   2. Libvirt domain configs (/etc/libvirt/qemu/)
#   3. Libvirt disk images (/var/lib/libvirt/images/)
#   4. Vagrant .vagrant directory state
#   5. Vagrant global status
#
# Usage:
#   ./cleanup_vms.sh           # Interactive mode (prompts before destructive actions)
#   ./cleanup_vms.sh --force   # Non-interactive mode (no prompts)
#   ./cleanup_vms.sh --dry-run # Show what would be cleaned without doing it

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
E2E_DIR="$(dirname "$SCRIPT_DIR")"
VAGRANT_DIR="$E2E_DIR/vagrant"

# VM name prefix used by the test suite
VM_PREFIX="mde-"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Flags
FORCE=false
DRY_RUN=false

log_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
log_action() { echo -e "${BLUE}[ACTION]${NC} $*"; }
log_dry() { echo -e "${YELLOW}[DRY-RUN]${NC} Would: $*"; }

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --force|-f)
            FORCE=true
            shift
            ;;
        --dry-run|-n)
            DRY_RUN=true
            shift
            ;;
        --help|-h)
            echo "Usage: $(basename "$0") [OPTIONS]"
            echo ""
            echo "Cleanup dangling MDE test VMs from interrupted e2e tests."
            echo ""
            echo "Options:"
            echo "  --force, -f     Non-interactive mode (no prompts)"
            echo "  --dry-run, -n   Show what would be cleaned without doing it"
            echo "  --help, -h      Show this help"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

confirm() {
    if [[ "$FORCE" == "true" ]] || [[ "$DRY_RUN" == "true" ]]; then
        return 0
    fi
    read -p "$1 [y/N] " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]]
}

run_cmd() {
    if [[ "$DRY_RUN" == "true" ]]; then
        log_dry "$*"
        return 0
    fi
    "$@"
}

# Track what we found
FOUND_DOMAINS=()
FOUND_CONFIGS=()
FOUND_IMAGES=()
FOUND_VAGRANT_STATE=false

echo "=============================================="
echo "  MDE E2E Test VM Cleanup Script"
echo "=============================================="
echo ""

# 1. Check libvirt domains on qemu:///system
log_info "Checking libvirt domains (qemu:///system)..."
while IFS= read -r line; do
    if [[ -n "$line" ]]; then
        FOUND_DOMAINS+=("$line")
    fi
done < <(virsh --connect qemu:///system list --all --name 2>/dev/null | grep "^${VM_PREFIX}" || true)

if [[ ${#FOUND_DOMAINS[@]} -gt 0 ]]; then
    log_warn "Found ${#FOUND_DOMAINS[@]} libvirt domain(s):"
    for domain in "${FOUND_DOMAINS[@]}"; do
        echo "    - $domain"
    done
else
    log_info "No libvirt domains found with prefix '$VM_PREFIX'"
fi

# 2. Check libvirt domain configs in /etc/libvirt/qemu/
log_info "Checking libvirt domain configs (/etc/libvirt/qemu/)..."
while IFS= read -r line; do
    if [[ -n "$line" ]]; then
        FOUND_CONFIGS+=("$line")
    fi
done < <(ls /etc/libvirt/qemu/${VM_PREFIX}*.xml 2>/dev/null || true)

if [[ ${#FOUND_CONFIGS[@]} -gt 0 ]]; then
    log_warn "Found ${#FOUND_CONFIGS[@]} orphaned domain config(s):"
    for config in "${FOUND_CONFIGS[@]}"; do
        echo "    - $config"
    done
else
    log_info "No orphaned domain configs found"
fi

# 3. Check libvirt disk images in /var/lib/libvirt/images/
log_info "Checking libvirt disk images (/var/lib/libvirt/images/)..."
for img in /var/lib/libvirt/images/${VM_PREFIX}*; do
    if [[ -f "$img" ]]; then
        FOUND_IMAGES+=("$img")
    fi
done

if [[ ${#FOUND_IMAGES[@]} -gt 0 ]]; then
    log_warn "Found ${#FOUND_IMAGES[@]} disk image(s):"
    for image in "${FOUND_IMAGES[@]}"; do
        echo "    - $image"
    done
else
    log_info "No disk images found with prefix '$VM_PREFIX'"
fi

# 4. Check Vagrant .vagrant directory
log_info "Checking Vagrant state directory..."
if [[ -d "$VAGRANT_DIR/.vagrant/machines" ]]; then
    MACHINE_COUNT=$(ls -1 "$VAGRANT_DIR/.vagrant/machines" 2>/dev/null | wc -l)
    if [[ "$MACHINE_COUNT" -gt 0 ]]; then
        FOUND_VAGRANT_STATE=true
        log_warn "Found Vagrant state for $MACHINE_COUNT machine(s) in $VAGRANT_DIR/.vagrant/machines/"
        ls -1 "$VAGRANT_DIR/.vagrant/machines" | while read -r m; do
            echo "    - $m"
        done
    fi
else
    log_info "No Vagrant state directory found"
fi

# Summary
echo ""
echo "=============================================="
echo "  Summary"
echo "=============================================="
TOTAL=$((${#FOUND_DOMAINS[@]} + ${#FOUND_CONFIGS[@]} + ${#FOUND_IMAGES[@]}))
if [[ "$FOUND_VAGRANT_STATE" == "true" ]]; then
    ((TOTAL++))
fi

if [[ "$TOTAL" -eq 0 ]]; then
    log_info "✅ No dangling VMs or state found. System is clean."
    exit 0
fi

echo "Found:"
echo "  - ${#FOUND_DOMAINS[@]} libvirt domain(s)"
echo "  - ${#FOUND_CONFIGS[@]} orphaned domain config(s)"
echo "  - ${#FOUND_IMAGES[@]} disk image(s)"
if [[ "$FOUND_VAGRANT_STATE" == "true" ]]; then
    echo "  - Vagrant .vagrant state directory"
fi
echo ""

if ! confirm "Proceed with cleanup?"; then
    log_info "Cleanup cancelled."
    exit 0
fi

# Perform cleanup
echo ""
log_info "Starting cleanup..."

# 1. Destroy and undefine libvirt domains
if [[ ${#FOUND_DOMAINS[@]} -gt 0 ]]; then
    log_action "Destroying libvirt domains..."
    for domain in "${FOUND_DOMAINS[@]}"; do
        # Try to destroy (stop) the domain first
        run_cmd virsh --connect qemu:///system destroy "$domain" 2>/dev/null || true
        # Undefine and remove storage
        run_cmd virsh --connect qemu:///system undefine "$domain" --remove-all-storage 2>/dev/null || true
        log_info "  Removed domain: $domain"
    done
fi

# 2. Remove orphaned domain configs (requires sudo)
if [[ ${#FOUND_CONFIGS[@]} -gt 0 ]]; then
    log_action "Removing orphaned domain configs..."
    for config in "${FOUND_CONFIGS[@]}"; do
        if [[ "$DRY_RUN" == "true" ]]; then
            log_dry "sudo rm -f $config"
        else
            sudo rm -f "$config"
            log_info "  Removed config: $config"
        fi
    done
    # Restart libvirtd to reload configs
    if [[ "$DRY_RUN" != "true" ]]; then
        log_action "Restarting libvirtd..."
        sudo systemctl restart libvirtd
    fi
fi

# 3. Remove disk images (requires sudo)
if [[ ${#FOUND_IMAGES[@]} -gt 0 ]]; then
    log_action "Removing disk images..."
    for image in "${FOUND_IMAGES[@]}"; do
        if [[ "$DRY_RUN" == "true" ]]; then
            log_dry "sudo rm -f $image"
        else
            sudo rm -f "$image"
            log_info "  Removed image: $image"
        fi
    done
fi

# 4. Remove Vagrant state directory
if [[ "$FOUND_VAGRANT_STATE" == "true" ]]; then
    log_action "Removing Vagrant state directory..."
    run_cmd rm -rf "$VAGRANT_DIR/.vagrant"
    log_info "  Removed: $VAGRANT_DIR/.vagrant"
fi

# 5. Prune Vagrant global status
log_action "Pruning Vagrant global status..."
run_cmd vagrant global-status --prune >/dev/null 2>&1 || true

echo ""
log_info "=============================================="
log_info "✅ Cleanup complete!"
log_info "=============================================="

# Verify
echo ""
log_info "Verification:"
REMAINING=$(virsh --connect qemu:///system list --all --name 2>/dev/null | grep "^${VM_PREFIX}" | wc -l || echo "0")
if [[ "$REMAINING" -eq 0 ]]; then
    log_info "  ✅ No libvirt domains with prefix '$VM_PREFIX'"
else
    log_warn "  ⚠️  $REMAINING domain(s) still present"
fi

if [[ ! -d "$VAGRANT_DIR/.vagrant" ]]; then
    log_info "  ✅ Vagrant state directory removed"
else
    log_warn "  ⚠️  Vagrant state directory still exists"
fi
