#!/bin/bash
# run-demo.sh - Execute three-phase MDE performance profile demo

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJ_NAME="MDE-Demo"
BUILD_DIR="$PROJECT_DIR/build"
SCHEME="MDE-Demo"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
print_phase() {
    echo -e "${BLUE}=== $1 ===${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

cleanup_build() {
    rm -rf "$BUILD_DIR"
}

test_eicar() {
    local phase=$1
    print_info "Testing EICAR detection in $phase..."
    
    # Create EICAR test file in build directory
    local eicar_path="$BUILD_DIR/eicar.txt"
    mkdir -p "$BUILD_DIR"
    
    # EICAR test string (safe - recognized by AV engines as a test)
    echo "X5O!P%@AP[4\PZX54(P^)7CC)7}\$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!\$H+H*" > "$eicar_path"
    
    # Give MDE time to scan
    sleep 2
    
    # Check if file still exists (if detected, MDE will quarantine it)
    if [ -f "$eicar_path" ]; then
        print_success "EICAR NOT detected (file still exists) - ⚠️ Protection gap with exclusions"
        return 1
    else
        print_success "EICAR detected and quarantined - ✅ Real-time protection active"
        return 0
    fi
}

# Check prerequisites
check_prerequisites() {
    print_phase "Checking prerequisites"
    
    if ! command -v xcodebuild &> /dev/null; then
        print_error "xcodebuild not found. Install Xcode Command Line Tools: xcode-select --install"
        exit 1
    fi
    
    if ! command -v mdatp &> /dev/null; then
        print_error "mdatp CLI not found. Install Microsoft Defender for Endpoint on macOS."
        exit 1
    fi
    
    # Check if real-time protection is enabled
    if ! mdatp health --field real_time_protection_enabled | grep -q "true"; then
        print_error "Real-time protection is not enabled. Enable it first."
        exit 1
    fi
    
    # Check if we have the project
    if [ ! -f "$PROJECT_DIR/$PROJ_NAME.xcodeproj/project.pbxproj" ]; then
        print_error "Xcode project not found at $PROJECT_DIR/$PROJ_NAME.xcodeproj"
        print_info "Run: ./setup-project.sh"
        exit 1
    fi
    
    print_success "All prerequisites met"
}

# Phase 1: Baseline
phase_baseline() {
    print_phase "Phase 1: Baseline Build (no optimizations)"
    print_info "Building with full scanning..."
    
    cleanup_build
    
    # Show current state
    echo "Current exclusions:"
    mdatp exclusion list 2>/dev/null || echo "None"
    echo "Current profiles:"
    mdatp performance-profiles list-applied 2>/dev/null || echo "None"
    
    # Build
    echo ""
    time xcodebuild -project "$PROJECT_DIR/$PROJ_NAME.xcodeproj" \
        -scheme "$SCHEME" \
        -derivedDataPath "$BUILD_DIR" \
        clean build
    
    echo ""
    test_eicar "baseline"
    cleanup_build
}

# Phase 2: AV Exclusions
phase_exclusions() {
    print_phase "Phase 2: AV Exclusions (protection gap)"
    print_info "Adding exclusion paths for build directory..."
    
    cleanup_build
    
    # Add exclusions
    sudo mdatp exclusion folder add --path "$BUILD_DIR"
    print_success "Exclusions added"
    
    # Build
    echo ""
    time xcodebuild -project "$PROJECT_DIR/$PROJ_NAME.xcodeproj" \
        -scheme "$SCHEME" \
        -derivedDataPath "$BUILD_DIR" \
        clean build
    
    echo ""
    test_eicar "exclusions"
    
    # Remove exclusions
    print_info "Removing exclusion paths..."
    sudo mdatp exclusion folder remove --path "$BUILD_DIR"
    print_success "Exclusions removed"
    
    cleanup_build
}

# Phase 3: Performance Profiles
phase_profiles() {
    print_phase "Phase 3: Performance Profiles (protected build)"
    print_info "Applying xcode and xcode-tree profiles..."
    
    cleanup_build
    
    # Apply profiles
    sudo mdatp performance-profiles apply --name xcode
    sudo mdatp performance-profiles apply --name xcode-tree
    print_success "Profiles applied"
    
    # Build
    echo ""
    time xcodebuild -project "$PROJECT_DIR/$PROJ_NAME.xcodeproj" \
        -scheme "$SCHEME" \
        -derivedDataPath "$BUILD_DIR" \
        clean build
    
    echo ""
    test_eicar "profiles"
    
    # Remove profiles
    print_info "Removing profiles..."
    sudo mdatp performance-profiles remove --name xcode
    sudo mdatp performance-profiles remove --name xcode-tree
    print_success "Profiles removed"
    
    cleanup_build
}

# Summary
print_summary() {
    echo ""
    print_phase "Demo Complete"
    echo ""
    echo "Summary:"
    echo "  1. Baseline build: Full scanning, full protection, high MDE CPU"
    echo "  2. Exclusions: Faster build, but EICAR undetected (protection gap)"
    echo "  3. Profiles: Fast build AND EICAR detected (no protection gap)"
    echo ""
    echo "Key insight: Folder exclusions blind protection; performance profiles don't."
    echo ""
}

# Main
main() {
    check_prerequisites
    
    # Cache sudo for the duration of the demo
    print_info "Caching sudo credentials..."
    sudo -v
    
    phase_baseline
    echo ""
    read -p "Press Enter to continue to Phase 2 (Exclusions)..."
    phase_exclusions
    echo ""
    read -p "Press Enter to continue to Phase 3 (Profiles)..."
    phase_profiles
    
    print_summary
}

# Run
main
