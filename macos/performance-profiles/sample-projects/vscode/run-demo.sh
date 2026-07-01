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

# --- Accurate measurement helpers -------------------------------------------

# Sum of "totalFilesScanned" across every process, from MDE real-time protection
# statistics. This is the accurate, documented signal for MDE scan overhead
# (see the macOS performance TSG). Counts are cumulative since RTP started, so we
# snapshot before/after each phase and report the delta.
scan_total_files() {
    mdatp diagnostic real-time-protection-statistics --output json 2>/dev/null \
      | python3 -c 'import json,sys
try:
    d=json.load(sys.stdin)
    print(sum(int(c.get("totalFilesScanned",0) or 0) for c in d.get("counters",[])))
except Exception:
    print(0)' 2>/dev/null || echo 0
}

# Sum of "totalScanTime" (nanoseconds) across every process.
scan_total_time_ns() {
    mdatp diagnostic real-time-protection-statistics --output json 2>/dev/null \
      | python3 -c 'import json,sys
try:
    d=json.load(sys.stdin)
    print(sum(int(c.get("totalScanTime",0) or 0) for c in d.get("counters",[])))
except Exception:
    print(0)' 2>/dev/null || echo 0
}

# Median of a list of numbers passed as arguments.
median() {
    printf '%s\n' "$@" | sort -n | awk '{a[NR]=$1} END{ if(NR==0){print 0; exit} m=int((NR+1)/2); if(NR%2){print a[m]} else {printf "%.2f\n",(a[m]+a[m+1])/2} }'
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

    # Warm-up build (discarded): the first build pays cold-cache / JIT costs that
    # would otherwise skew the numbers. It is not counted in any statistic.
    print_info "Warm-up build (discarded)..."
    rm -rf "$PROJECT_DIR/out" 2>/dev/null || true
    npm run compile > /dev/null 2>&1 || true

    # Snapshot MDE scan totals immediately before the measured loop so the delta
    # reflects only the work done by these builds.
    local scans_before=$(scan_total_files)
    local scan_ns_before=$(scan_total_time_ns)

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

    # Snapshot MDE scan totals after the measured loop.
    local scans_after=$(scan_total_files)
    local scan_ns_after=$(scan_total_time_ns)
    local scans_delta=$(( scans_after - scans_before ))
    local scan_ms_delta=$(echo "scale=1; ($scan_ns_after - $scan_ns_before) / 1000000" | bc 2>/dev/null)

    # Capture after builds
    capture_performance_snapshot "$snapshot_after" "$phase (After)"

    # Calculate stats
    if [ ${#build_times[@]} -gt 0 ]; then
        local total=0
        for t in "${build_times[@]}"; do
            total=$(echo "$total + $t" | bc 2>/dev/null)
        done

        local avg=$(echo "scale=2; $total / ${#build_times[@]}" | bc 2>/dev/null)
        local med=$(median "${build_times[@]}")
        local min=$(printf '%s\n' "${build_times[@]}" | sort -n | head -1)
        local max=$(printf '%s\n' "${build_times[@]}" | sort -n | tail -1)

        print_info "Build Performance ($phase):"
        print_info "  Wall clock  -> median: ${med}s | avg: ${avg}s | min: ${min}s | max: ${max}s"
        print_info "  MDE scans   -> files scanned during builds: ${scans_delta} | scan time: ${scan_ms_delta}ms"
        print_info "  (MDE scan counts are the accurate signal; wall clock is secondary and noisier.)"
        echo ""

        # Save timing metrics to snapshot file
        {
            echo ""
            echo "=== Build Performance Metrics ==="
            echo "Number of builds: ${#build_times[@]}"
            echo "Median build time: ${med}s"
            echo "Average build time: ${avg}s"
            echo "Min build time: ${min}s"
            echo "Max build time: ${max}s"
            echo "All build times: ${build_times[*]}"
            echo "MDE files scanned during builds: ${scans_delta}"
            echo "MDE scan time during builds (ms): ${scan_ms_delta}"
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

    # Generate the compile workload if missing. A single hand-written source file
    # compiles in well under a second, which is too small for MDE scan overhead to
    # be measurable. The generated modules make each build take ~20-40s and produce
    # real file I/O for Defender to scan. Override the size with MDE_DEMO_MODULES.
    if [ ! -d "$PROJECT_DIR/src/generated" ]; then
        print_info "Generating compile workload (this makes build times measurable)..."
        node "$PROJECT_DIR/generate-workload.js"
    else
        print_info "Compile workload already generated ($(find "$PROJECT_DIR/src/generated" -name '*.ts' | wc -l | tr -d ' ') modules)"
    fi

    # Enable real-time protection statistics. This is the documented, accurate way
    # to measure MDE scan overhead (per-process "Total files scanned"). Without it,
    # the diagnostic snapshots are empty and only noisy wall-clock time remains.
    print_info "Enabling real-time protection statistics..."
    sudo mdatp config real-time-protection-statistics --value enabled &>/dev/null || \
        print_error "Could not enable real-time-protection-statistics (scan counts may be unavailable)."

    # Tamper Protection in block mode causes real-time-protection-statistics to
    # return null. Warn the user so they can use troubleshooting mode if needed.
    local tp_status=$(mdatp health --field tamper_protection 2>/dev/null | tr -d '"')
    if [ "$tp_status" = "block" ]; then
        print_info "Tamper Protection is in 'block' mode."
        print_info "  If MDE scan counts come back as 0, enable troubleshooting mode so"
        print_info "  real-time-protection-statistics can be captured (see the macOS perf TSG)."
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
    echo "  • Baseline: Full MDE scanning on all files (highest scan count)"
    echo "  • Exclusions: Fewer files scanned + EICAR undetected (⚠️ protection gap)"
    echo "  • Profiles: Fewer files scanned, EICAR still detected (✅ protected)"
    echo ""
    echo "Compare the 'MDE files scanned during builds' number across phases —"
    echo "that scan-count delta is the accurate signal. Wall-clock time is secondary."
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

    # Restore real-time protection statistics to its default (disabled) state.
    sudo mdatp config real-time-protection-statistics --value disabled &>/dev/null || true
}

# Run
main
