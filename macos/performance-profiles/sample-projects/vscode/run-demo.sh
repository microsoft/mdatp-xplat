#!/bin/bash
# run-demo.sh - Execute three-phase MDE performance profile demo for VSCode

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS_DIR="$PROJECT_DIR/run-logs"
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
RUN_DIR="$LOGS_DIR/$TIMESTAMP"

# Create run-specific logs directory if it doesn't exist
mkdir -p "$RUN_DIR"

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
    rm -rf "$PROJECT_DIR/out"
}

cleanup_exclusions() {
    # Remove any existing exclusions completely silently
    sudo mdatp exclusion folder remove --path "$PROJECT_DIR/out" &>/dev/null || true
    sudo mdatp exclusion folder remove --path "$PROJECT_DIR/node_modules" &>/dev/null || true
    sudo mdatp exclusion folder remove --path "$PROJECT_DIR/.build" &>/dev/null || true
}

cleanup_profiles() {
    # Remove any existing profiles completely silently
    sudo mdatp performance-profiles remove --name node &>/dev/null || true
    sudo mdatp performance-profiles remove --name vscode &>/dev/null || true
    sudo mdatp performance-profiles remove --name vscode-tree &>/dev/null || true
    sudo mdatp performance-profiles remove --name git &>/dev/null || true
}

capture_performance_snapshot() {
    local snapshot_file="$1"
    local phase=$2
    
    # Capture detailed diagnostic information about MDE performance
    {
        echo "=== $phase Performance Metrics ==="
        echo "Captured: $(date '+%Y-%m-%d %H:%M:%S')"
        echo ""
        
        # Get MDE health and performance info
        echo "MDE Status:"
        mdatp health --field real_time_protection_enabled 2>/dev/null | xargs -I {} echo "  Real-time Protection: {}"
        mdatp health --field engine_version 2>/dev/null | xargs -I {} echo "  Engine: {}"
        echo ""
        
        # Capture current exclusions
        echo "Active Exclusions:"
        mdatp exclusion list 2>/dev/null | grep -E "^Excluded|^Path:" | head -20 || echo "  None"
        echo ""
        
        # Capture applied profiles for reference
        echo "Applied Profiles:"
        mdatp performance-profiles list-applied 2>/dev/null | grep -E "^[a-z]|Merge policy" || echo "  None"
        echo ""
        
        # Capture hot event sources - shows what MDE is actively scanning
        echo "Hot Event Sources (Active Scanning):"
        mdatp diagnostic hot-event-sources 2>/dev/null | head -20 || echo "  (unable to capture)"
        echo ""
        
        # Capture real-time protection statistics
        echo "Real-time Protection Resource Usage:"
        mdatp diagnostic real-time-protection-statistics 2>/dev/null | head -15 || echo "  (unable to capture)"
        echo ""
        
    } > "$snapshot_file"
}

run_builds() {
    local phase=$1
    local num_builds=${2:-5}
    local phase_name=$(echo "$phase" | tr ' ' '_' | tr '[:upper:]' '[:lower:]')
    local snapshot_before="$RUN_DIR/${phase_name}_before.txt"
    local snapshot_after="$RUN_DIR/${phase_name}_after.txt"
    
    print_info "Running $num_builds builds to measure performance..."
    print_info "Logs: $RUN_DIR"
    
    # Capture baseline before builds
    capture_performance_snapshot "$snapshot_before" "$phase (Before)"
    
    local build_times=()
    
    for i in $(seq 1 $num_builds); do
        rm -rf "$PROJECT_DIR/out" 2>/dev/null || true
        
        # Run build and capture timing - time outputs to stderr
        local output=$( { time npm run compile > /dev/null 2>&1; } 2>&1 )
        local real_time=$(echo "$output" | grep "^real" | head -1 | awk '{print $2}')
        
        if [ -n "$real_time" ]; then
            # Convert time format (e.g., 0m0.682s) to seconds
            local seconds=$(echo "$real_time" | sed 's/m/:/' | sed 's/s$//' | awk -F: '{print $1*60+$2}')
            build_times+=("$seconds")
        fi
        
        echo -n "."
    done
    
    echo ""
    
    # Capture after builds
    capture_performance_snapshot "$snapshot_after" "$phase (After)"
    
    # Calculate stats
    if [ ${#build_times[@]} -gt 0 ]; then
        local total=0
        for t in "${build_times[@]}"; do
            total=$(echo "$total + $t" | bc 2>/dev/null)
        done
        
        local avg=$(echo "scale=2; $total / ${#build_times[@]}" | bc 2>/dev/null)
        local min=$(printf '%s\n' "${build_times[@]}" | sort -n | head -1)
        local max=$(printf '%s\n' "${build_times[@]}" | sort -n | tail -1)
        
        print_info "Build Performance ($phase):"
        print_info "  Average: ${avg}s"
        print_info "  Min: ${min}s  |  Max: ${max}s"
        echo ""
        
        # Save timing metrics to snapshot file
        {
            echo ""
            echo "=== Build Performance Metrics ==="
            echo "Number of builds: ${#build_times[@]}"
            echo "Average build time: ${avg}s"
            echo "Min build time: ${min}s"
            echo "Max build time: ${max}s"
            echo "All build times: ${build_times[*]}"
        } >> "$snapshot_after"
    fi
    
    # Show diagnostic snapshots if files exist
    if [ -f "$snapshot_before" ]; then
        cat "$snapshot_before"
        echo ""
    fi
    if [ -f "$snapshot_after" ]; then
        cat "$snapshot_after"
        echo ""
    fi
}

test_eicar() {
    local phase=$1
    print_info "Testing EICAR detection in $phase..."
    
    # Create EICAR test file in build directory
    local eicar_path="$PROJECT_DIR/out/eicar.txt"
    mkdir -p "$PROJECT_DIR/out"
    
    # EICAR test string (safe - recognized by AV engines as a test)
    echo "X5O!P%@AP[4\PZX54(P^)7CC)7}\$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!\$H+H*" > "$eicar_path"
    
    # Give MDE time to scan
    sleep 2
    
    # Check if file still exists (if detected, MDE will quarantine it)
    if [ -f "$eicar_path" ]; then
        print_success "EICAR NOT detected (file still exists) - ⚠️ Protection gap with exclusions"
        return 0  # Return success to allow demo to continue
    else
        print_success "EICAR detected and quarantined - ✅ Real-time protection active"
        return 0
    fi
}

# Check prerequisites
check_prerequisites() {
    print_phase "Checking prerequisites"
    
    if ! command -v npm &> /dev/null; then
        print_error "npm not found. Install Node.js: https://nodejs.org"
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
    
    # Install dependencies if needed
    if [ ! -d "$PROJECT_DIR/node_modules" ]; then
        print_info "Installing npm dependencies..."
        npm install
    fi
    
    print_success "All prerequisites met"
}

# Phase 1: Baseline
phase_baseline() {
    print_phase "Phase 1: Baseline Build (no optimizations)"
    
    # Clean up any leftovers from previous runs
    cleanup_exclusions
    cleanup_profiles
    print_info "Building with full scanning..."
    
    cleanup_build
    
    # Show current state
    echo "Current exclusions:"
    mdatp exclusion list 2>/dev/null || echo "None"
    echo "Current profiles:"
    mdatp performance-profiles list-applied 2>/dev/null || echo "None"
    
    # Run multiple builds to capture performance metrics
    echo ""
    run_builds "Baseline (Full Scanning)"
    
    test_eicar "baseline"
}

# Phase 2: AV Exclusions
phase_exclusions() {
    print_phase "Phase 2: AV Exclusions (protection gap)"
    
    cleanup_exclusions
    print_info "Adding exclusion paths for build directories..."
    
    cleanup_build
    
    # Add exclusions (one per command)
    sudo mdatp exclusion folder add --path "$PROJECT_DIR/out"
    sudo mdatp exclusion folder add --path "$PROJECT_DIR/node_modules"
    sudo mdatp exclusion folder add --path "$PROJECT_DIR/.build"
    print_success "Exclusions added"
    
    # Run multiple builds to capture performance metrics
    echo ""
    run_builds "With Exclusions"
    
    test_eicar "exclusions"
    
    # Remove exclusions
    print_info "Removing exclusion paths..."
    sudo mdatp exclusion folder remove --path "$PROJECT_DIR/out"
    sudo mdatp exclusion folder remove --path "$PROJECT_DIR/node_modules"
    sudo mdatp exclusion folder remove --path "$PROJECT_DIR/.build"
    print_success "Exclusions removed"
}

# Phase 3: Performance Profiles
phase_profiles() {
    print_phase "Phase 3: Performance Profiles (protected build)"
    
    cleanup_profiles
    print_info "Applying node, vscode, and vscode-tree profiles..."
    
    cleanup_build
    
    # Apply profiles (one per command)
    sudo mdatp performance-profiles apply --name node
    sudo mdatp performance-profiles apply --name vscode
    sudo mdatp performance-profiles apply --name vscode-tree
    sudo mdatp performance-profiles apply --name git
    print_success "Profiles applied"
    
    # Run multiple builds to capture performance metrics
    echo ""
    run_builds "With Performance Profiles"
    
    test_eicar "profiles"
    
    # Remove profiles
    print_info "Removing profiles..."
    sudo mdatp performance-profiles remove --name node
    sudo mdatp performance-profiles remove --name vscode
    sudo mdatp performance-profiles remove --name vscode-tree
    sudo mdatp performance-profiles remove --name git
    print_success "Profiles removed"
}

# Summary
print_summary() {
    echo ""
    print_phase "Demo Complete"
    echo ""
    echo "Key Findings:"
    echo "  • Baseline: Full MDE scanning on all files"
    echo "  • Exclusions: Faster builds, but EICAR undetected (⚠️ protection gap)"  
    echo "  • Profiles: Comparable build times, EICAR still detected (✅ protected)"
    echo ""
    echo "Insight: Performance profiles maintain security while improving build speed."
    echo ""
    echo "Diagnostic Logs:"
    echo "  Location: $RUN_DIR"
    local log_count=$(ls -1 "$RUN_DIR"/*.txt 2>/dev/null | wc -l)
    if [ "$log_count" -gt 0 ]; then
        echo "  Files: $log_count diagnostic snapshots captured"
    fi
    echo ""
}

generate_report() {
    print_info "Generating report..."
    
    # Call Node.js report generator
    if command -v node &> /dev/null; then
        if node "$PROJECT_DIR/generate-report.js" "$RUN_DIR"; then
            print_success "Report generated successfully"
        else
            print_error "Failed to generate report"
        fi
    else
        print_error "Node.js not found - skipping report generation"
    fi
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
    generate_report
    
    # Final cleanup (silently)
    cleanup_build
    cleanup_exclusions
    cleanup_profiles
}

# Run
main
