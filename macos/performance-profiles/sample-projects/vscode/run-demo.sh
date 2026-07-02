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

# --- Demo configuration (override via environment) --------------------------
# Profiles applied in Phase 3, space-separated. Defaults to the full scenario set.
# Narrow it to run a subset, e.g. MDE_DEMO_PROFILES="node".
DEMO_PROFILES=${MDE_DEMO_PROFILES:-"node vscode vscode-tree git"}
# Force the build onto a specific node install. Accepts a node binary OR the bin
# dir containing it. Example: MDE_FORCE_NODE=/opt/homebrew/opt/node/bin
FORCE_NODE=${MDE_FORCE_NODE:-}

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

print_warning() {
    echo -e "${RED}⚠ $1${NC}"
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

# Total cumulative CPU seconds consumed by MDE daemons, summed over every process
# whose truncated command name (ucomm) contains the given filter.
# MDE on macOS runs three cooperating daemons (per the internal macOS Performance
# TSG): "wdavdaemon" is the PRIVILEGED core daemon that receives EndpointSecurity
# events from epsext and routes them via IPC to the two backends;
# "wdavdaemon_enterprise" is the EDR backend; "wdavdaemon_unprivileged" is the
# AV / real-time-protection (RTP) backend that does file scanning (the one users
# watch spike in Activity Monitor). Filter "wdavdaemon" is a substring, so it sums
# all three; "wdavdaemon_unpri" / "wdavdaemon_enter" isolate a single backend.
# Matches on ucomm because the executable path contains a space
# ("Microsoft Defender.app") that would break path-based parsing.
mde_cpu_seconds() {
    local filter=${1:-wdavdaemon}
    ps -Ao time=,ucomm= 2>/dev/null | awk -v f="$filter" '
        index($2, f) {
            t=$1; days=0
            if (t ~ /-/) { split(t, dd, "-"); days=dd[1]; t=dd[2] }
            n=split(t, a, ":")
            if (n==3) sec=a[1]*3600 + a[2]*60 + a[3]
            else if (n==2) sec=a[1]*60 + a[2]
            else sec=a[1]
            total += sec + days*86400
        } END { printf "%.2f", total+0 }'
}

# Start a background sampler that records peak RSS (MB), sampling once per second,
# for the unprivileged AV daemon, the enterprise (EDR) daemon, and all MDE daemons
# combined. Writes three lines to $1: "unpriv <mb>", "enterprise <mb>", "all <mb>".
# Prints the sampler PID so the caller can stop it with a targeted kill.
start_mem_sampler() {
    local out=$1
    printf 'unpriv 0.0\nenterprise 0.0\nall 0.0\n' > "$out"
    (
        pu=0; pe=0; pa=0
        while :; do
            # One ps pass; sum RSS (KB) per daemon class.
            eval "$(ps -Ao rss=,ucomm= 2>/dev/null | awk '
                index($2,"wdavdaemon"){ all+=$1 }
                index($2,"wdavdaemon_unpri"){ unpr+=$1 }
                index($2,"wdavdaemon_enter"){ ent+=$1 }
                END{ printf "u=%d; e=%d; a=%d", unpr+0, ent+0, all+0 }')"
            [ "${u:-0}" -gt "$pu" ] 2>/dev/null && pu=$u
            [ "${e:-0}" -gt "$pe" ] 2>/dev/null && pe=$e
            [ "${a:-0}" -gt "$pa" ] 2>/dev/null && pa=$a
            awk -v u="$pu" -v e="$pe" -v a="$pa" \
                'BEGIN{printf "unpriv %.1f\nenterprise %.1f\nall %.1f\n", u/1024, e/1024, a/1024}' > "$out"
            sleep 1
        done
    ) >/dev/null 2>&1 &
    echo $!
}

cleanup_build() {
    rm -rf "$PROJECT_DIR/out.noindex"
}

# --- Hot-event-source capture DURING the build window -----------------------
#
# The per-phase _after.txt snapshot samples hot-event-sources for ~1s AFTER the
# builds finish, which only shows idle noise (node/tsc has already exited). To see
# which processes actually drive scan load WHILE the build runs — and whether an
# applied profile suppresses them — stream the source concurrently with the build.
#
# mdatp diagnostic hot-event-sources streams cumulative "Top N Hot Event Sources"
# tables until interrupted, so we run it in the background for the whole measured
# window, interrupt it with SIGINT, and keep the final (cumulative) table.

# Start the stream writing raw output to $1; echo the PID so the caller can stop it.
start_hot_event_capture() {
    local raw=$1
    mdatp diagnostic hot-event-sources --output json >"$raw" 2>&1 &
    echo $!
}

# Stop the stream (SIGINT lets mdatp flush a final table before exiting), then wait
# for it to exit.
stop_hot_event_capture() {
    local pid=$1
    [ -n "$pid" ] || return 0
    kill -INT "$pid" 2>/dev/null || true
    for _ in 1 2 3 4 5; do
        kill -0 "$pid" 2>/dev/null || return 0
        sleep 0.3
    done
    kill "$pid" 2>/dev/null || true
}

# Extract the final cumulative "Top N Hot Event Sources" AND "Top N Hot Event
# Targets" tables (plus the summary line) from a raw capture into a compact,
# readable per-phase file. Sources = the processes driving scans; Targets = the
# actual files/paths being scanned. Each streamed snapshot is cumulative since
# capture start, so the last complete Sources/Targets pair reflects the whole
# window. Output is normalized with stable "=== Hot Event Sources/Targets ==="
# delimiters so generate-report.js can split the two tables reliably.
summarize_hot_events() {
    local raw=$1 out=$2
    sed 's/\x1b\[[0-9;]*m//g' "$raw" 2>/dev/null | awk '
        # A new snapshot summary closes any in-progress Targets block.
        /^Total Events:/ {
            summary=$0
            if (cap=="tgt") { last_tgt=buf; cap="" }
        }
        # Start of a Sources table: closes any in-progress Targets block first.
        /Top .* Hot Event Sources ===/ {
            if (cap=="tgt") { last_tgt=buf }
            cap="src"; buf=""; cur_hdr=summary; next
        }
        # Sources table ends where the Targets table begins.
        cap=="src" && /Hot Event Targets ===/ {
            last_src=buf; last_hdr=cur_hdr
            cap="tgt"; buf=""; next
        }
        cap { buf=buf $0 "\n" }
        END {
            # Flush a trailing (final) Targets block if the stream ended inside one.
            if (cap=="tgt") { last_tgt=buf }
            if (last_src == "" && last_tgt == "") {
                print "(no hot-event sources captured during window)"; exit
            }
            print last_hdr
            print "=========== Hot Event Sources ==========="
            printf "%s", last_src
            print "=========== Hot Event Targets ==========="
            if (last_tgt == "") print "(no hot-event targets captured during window)"
            else printf "%s", last_tgt
        }
    ' > "$out"
}

cleanup_exclusions() {
    # Remove any existing exclusions completely silently
    sudo mdatp exclusion folder remove --path "$PROJECT_DIR/out.noindex" &>/dev/null || true
    sudo mdatp exclusion folder remove --path "$PROJECT_DIR/node_modules" &>/dev/null || true
    sudo mdatp exclusion folder remove --path "$PROJECT_DIR/.build" &>/dev/null || true
}

cleanup_profiles() {
    # Remove any profiles this demo may have applied, silently.
    local p
    for p in node vscode vscode-tree git $DEMO_PROFILES; do
        sudo mdatp performance-profiles remove --name "$p" &>/dev/null || true
    done
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

# Classify the node install that will run the build. Performance profiles match
# processes by their on-disk install location, and package managers can install the
# same runtime under differently-named directories (e.g. a canonical "node" install
# vs. a version-pinned formula). A version-pinned install may sit outside the layout
# a profile targets, so we prefer the canonical install. This only inspects the local
# path layout — it does not describe any profile's internal definition.
node_install_kind() {
    local real="$1"
    case "$real" in
        */node@*/*)
            echo "version-pinned install (may fall outside the profile's target layout; prefer the canonical node install)"; return 1;;
        */Cellar/node/*|*/opt/node/*)
            echo "canonical install (recommended for profile coverage)"; return 0;;
    esac
    echo "non-standard install location (verify your profile covers this path)"
    return 1
}

# Capture machine-specific facts needed to interpret a report that was produced on
# a DIFFERENT machine. The per-phase snapshots show what MDE scanned, but not WHY a
# phase behaved the way it did (which node ran the build, its install layout,
# engine/version, tamper state, installed formulas). Without this, diagnosing a
# lab-machine report is guesswork.
# Walk the parent-process chain from a PID up to launchd, echoing "pid  command"
# for each ancestor. Used to show HOW the demo (and therefore the build's node) was
# launched — which determines whether the build sits inside a process tree that a
# profile mutes.
process_ancestry() {
    local pid=$1
    while [ -n "$pid" ] && [ "$pid" -gt 1 ] 2>/dev/null; do
        local line
        line=$(ps -o ppid=,comm= -p "$pid" 2>/dev/null)
        [ -n "$line" ] || break
        local ppid=$(echo "$line" | awk '{print $1}')
        local comm=$(echo "$line" | sed -E 's/^[[:space:]]*[0-9]+[[:space:]]+//')
        echo "    $pid  $comm"
        pid=$ppid
    done
}

# Return 0 if any ancestor of $1 is a VSCode process. The build's file scans are only
# suppressed by the vscode-tree profile when the build runs inside VSCode's subtree
# (e.g. launched from VSCode's integrated terminal or task runner).
under_vscode() {
    local pid=$1
    while [ -n "$pid" ] && [ "$pid" -gt 1 ] 2>/dev/null; do
        local line
        line=$(ps -o ppid=,comm= -p "$pid" 2>/dev/null)
        [ -n "$line" ] || break
        local ppid=$(echo "$line" | awk '{print $1}')
        local comm=$(echo "$line" | sed -E 's/^[[:space:]]*[0-9]+[[:space:]]+//')
        case "$comm" in
            *Visual\ Studio\ Code.app*|*/Code\ Helper*|*/Electron*) return 0;;
        esac
        pid=$ppid
    done
    return 1
}

capture_environment_diagnostics() {
    local out="$RUN_DIR/diagnostics.txt"
    local node_bin node_real npm_bin
    node_bin=$(command -v node 2>/dev/null)
    node_real=$(readlink -f "$node_bin" 2>/dev/null || echo "$node_bin")
    npm_bin=$(command -v npm 2>/dev/null)
    {
        echo "=== Environment Diagnostics ==="
        echo "Captured: $(date '+%Y-%m-%d %H:%M:%S')"
        echo ""

        echo "Host:"
        echo "  Hostname: $(hostname 2>/dev/null)"
        echo "  macOS: $(sw_vers -productVersion 2>/dev/null) (build $(sw_vers -buildVersion 2>/dev/null))"
        echo "  Arch: $(uname -m 2>/dev/null)"
        echo "  Model/CPU: $(sysctl -n machdep.cpu.brand_string 2>/dev/null)"
        echo ""

        echo "MDE:"
        echo "  Version: $(mdatp version 2>/dev/null | tr -d '\n')"
        echo "  Engine: $(mdatp health --field engine_version 2>/dev/null | tr -d '\"')"
        echo "  App version: $(mdatp health --field app_version 2>/dev/null | tr -d '\"')"
        echo "  Real-time protection: $(mdatp health --field real_time_protection_enabled 2>/dev/null | tr -d '\"')"
        echo "  Tamper protection: $(mdatp health --field tamper_protection 2>/dev/null | tr -d '\"')"
        echo ""

        echo "Node (this is what runs the build; the profile must cover its install location):"
        echo "  node on PATH: ${node_bin:-not found}"
        echo "  node real path: ${node_real:-n/a}"
        echo "  node version: $(node --version 2>/dev/null)"
        echo "  npm: ${npm_bin:-not found} ($(npm --version 2>/dev/null))"
        if [ -n "$node_real" ]; then
            echo "  node install: $(node_install_kind "$node_real")"
            echo "  node code signature (determines executable-signature match):"
            codesign -dv --verbose=4 "$node_real" 2>&1 \
                | grep -iE '^Identifier=|^TeamIdentifier=|^Signature=' \
                | sed 's/^/    /' || echo "    (unable to read signature)"
        fi
        echo "  Installed Homebrew node formulas:"
        brew list --versions 2>/dev/null | grep -iE '^node( |@)' | sed 's/^/    /' || echo "    (brew not available)"
        echo ""

        echo "Performance profiles:"
        echo "  Applied:"
        mdatp performance-profiles list-applied 2>/dev/null | sed 's/^/    /' || echo "    (unable to capture)"
        echo "  'node' available: $(mdatp performance-profiles list-available 2>/dev/null | grep -qx node && echo yes || echo no)"
        echo ""

        echo "Launch context (does the build run inside VSCode's process tree?):"
        if under_vscode "$$"; then
            echo "  Build process tree under VSCode: yes"
            echo "  -> node runs inside VSCode's subtree, so the vscode-tree profile can mute its scans."
        else
            echo "  Build process tree under VSCode: no"
            echo "  -> node runs OUTSIDE VSCode's subtree. The vscode-tree profile (which mutes VSCode's"
            echo "     children) will NOT cover this build's node. Run the demo from VSCode's integrated"
            echo "     terminal so node becomes a child of VSCode, matching a real dev workflow."
        fi
        echo "  Process ancestry (this script -> ... -> launchd):"
        process_ancestry "$$"
        echo ""
    } > "$out"
    print_success "Environment diagnostics captured: $out"
}

run_builds() {
    local phase=$1
    local num_builds=${2:-3}
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
    rm -rf "$PROJECT_DIR/out.noindex" 2>/dev/null || true
    npm run compile > /dev/null 2>&1 || true

    # Snapshot MDE scan totals immediately before the measured loop so the delta
    # reflects only the work done by these builds.
    local scans_before=$(scan_total_files)
    local scan_ns_before=$(scan_total_time_ns)

    # Snapshot MDE CPU time and start sampling peak memory. These capture the
    # resource cost users actually complain about (wdavdaemon_unprivileged CPU
    # spikes and memory growth) over the exact same window as the builds.
    local cpu_all_before=$(mde_cpu_seconds wdavdaemon)
    local cpu_unpr_before=$(mde_cpu_seconds wdavdaemon_unpri)
    local cpu_ent_before=$(mde_cpu_seconds wdavdaemon_enter)
    local wall_start=$(date +%s.%N)
    local mem_file=$(mktemp)
    local mem_sampler_pid=$(start_mem_sampler "$mem_file")

    # Stream hot-event-sources for the whole measured window so we can see which
    # processes actually drive scan load DURING the build (and whether the applied
    # profile suppresses them), not just idle noise after it finishes.
    local hot_raw=$(mktemp)
    local hot_events_file="$RUN_DIR/${phase_name}_hot_events.txt"
    local hot_events_pid=$(start_hot_event_capture "$hot_raw")

    local build_times=()

    for i in $(seq 1 $num_builds); do
        rm -rf "$PROJECT_DIR/out.noindex" 2>/dev/null || true

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

    # Snapshot MDE CPU time after the loop and stop the memory sampler.
    local cpu_all_after=$(mde_cpu_seconds wdavdaemon)
    local cpu_unpr_after=$(mde_cpu_seconds wdavdaemon_unpri)
    local cpu_ent_after=$(mde_cpu_seconds wdavdaemon_enter)
    local wall_end=$(date +%s.%N)
    kill "$mem_sampler_pid" 2>/dev/null || true
    local peak_mem_mb=$(awk '/^unpriv/{print $2}' "$mem_file" 2>/dev/null)
    local peak_mem_ent_mb=$(awk '/^enterprise/{print $2}' "$mem_file" 2>/dev/null)
    local peak_mem_all_mb=$(awk '/^all/{print $2}' "$mem_file" 2>/dev/null)
    rm -f "$mem_file" 2>/dev/null || true

    # Stop the hot-event stream and keep the final cumulative top-sources table.
    stop_hot_event_capture "$hot_events_pid"
    summarize_hot_events "$hot_raw" "$hot_events_file"
    rm -f "$hot_raw" 2>/dev/null || true
    print_info "Top scan sources during build:"
    sed 's/^/    /' "$hot_events_file" 2>/dev/null | head -8

    # Average %CPU over the window = CPU-seconds consumed / wall-seconds * 100.
    # This is the honest "how hard did MDE work during the builds" number.
    # scale=2 so near-idle daemons show a real small value instead of rounding to 0.
    local window=$(echo "$wall_end - $wall_start" | bc 2>/dev/null)
    local cpu_all_pct=$(echo "scale=2; ($cpu_all_after - $cpu_all_before) / $window * 100" | bc 2>/dev/null)
    local cpu_unpr_pct=$(echo "scale=2; ($cpu_unpr_after - $cpu_unpr_before) / $window * 100" | bc 2>/dev/null)
    local cpu_ent_pct=$(echo "scale=2; ($cpu_ent_after - $cpu_ent_before) / $window * 100" | bc 2>/dev/null)

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
        print_info "  MDE CPU     -> unprivileged AV: ${cpu_unpr_pct}% | enterprise EDR: ${cpu_ent_pct}% | all daemons: ${cpu_all_pct}% avg (over ${window}s window)"
        print_info "  MDE memory  -> peak RSS: unprivileged AV ${peak_mem_mb} MB | enterprise EDR ${peak_mem_ent_mb} MB | all daemons ${peak_mem_all_mb} MB"
        print_info "  (MDE scan counts + CPU are the accurate signals; wall clock is secondary and noisier.)"
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
            echo "MDE unprivileged AV avg CPU (%): ${cpu_unpr_pct}"
            echo "MDE enterprise EDR avg CPU (%): ${cpu_ent_pct}"
            echo "MDE all daemons avg CPU (%): ${cpu_all_pct}"
            echo "MDE unprivileged AV peak RSS (MB): ${peak_mem_mb}"
            echo "MDE enterprise EDR peak RSS (MB): ${peak_mem_ent_mb}"
            echo "MDE all daemons peak RSS (MB): ${peak_mem_all_mb}"
            echo "Measurement window (s): ${window}"
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

# Number of entries in the MDE threat list. Each detection adds exactly one
# "Id:" line, so this is a monotonic signal the EICAR probe can watch.
threat_count() {
    mdatp threat list 2>/dev/null | grep -c '^[[:space:]]*Id:' || true
}

# Drop a real EICAR test file and determine whether real-time protection catches it,
# using the threat-count signal (rises on detection) or quarantine (file removed),
# polling up to a timeout. The ACTUAL result is written to <phase>_eicar.txt so the
# report reflects what happened instead of an assumed outcome. Ported from the pytest
# EICAR probe (mde.eicar_probe) on the perf-profiles-demo branch.
test_eicar() {
    local phase=$1
    local out="$RUN_DIR/${phase}_eicar.txt"
    local target_dir="$PROJECT_DIR/out.noindex"
    local timeout=${MDE_EICAR_TIMEOUT:-30} poll=1 elapsed=0
    print_info "Testing EICAR detection in $phase..."
    mkdir -p "$target_dir"

    local eicar_path="$target_dir/eicar_$(date +%s).txt"
    local before after detected=0 file_removed=0

    before=$(threat_count)

    # Write the EICAR string from a CHILD process. RTP reliably scans a file written
    # by a separate process; an in-process write can be missed in some build dirs.
    # Content is passed via the environment to avoid any quoting pitfalls.
    EICAR_CONTENT='X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*' \
        /bin/sh -c 'printf "%s" "$EICAR_CONTENT" > "$1"' sh "$eicar_path" 2>/dev/null || true

    # Poll: detection = threat count rises, or MDE quarantines (removes) the file.
    while [ "$elapsed" -lt "$timeout" ]; do
        after=$(threat_count)
        if [ "${after:-0}" -gt "${before:-0}" ]; then detected=1; break; fi
        if [ ! -f "$eicar_path" ]; then detected=1; file_removed=1; break; fi
        sleep "$poll"; elapsed=$((elapsed + poll))
    done
    after=$(threat_count)
    [ -f "$eicar_path" ] || file_removed=1

    # Clean up (quarantine may already have removed it).
    rm -f "$eicar_path" 2>/dev/null || true

    {
        echo "=== EICAR Detection ==="
        echo "Phase: $phase"
        echo "Target dir: $target_dir"
        echo "Result: $([ "$detected" -eq 1 ] && echo DETECTED || echo NOT_DETECTED)"
        echo "Threat count before: ${before:-0}"
        echo "Threat count after: ${after:-0}"
        echo "File removed by MDE: $([ "$file_removed" -eq 1 ] && echo yes || echo no)"
        echo "Waited (s): $elapsed"
        echo "RTP enabled: $(mdatp health --field real_time_protection_enabled 2>/dev/null | tr -d '\"')"
    } > "$out"

    if [ "$detected" -eq 1 ]; then
        print_success "EICAR detected in $phase (threat count ${before:-0}→${after:-0}) - ✅ RTP active"
    else
        print_info "EICAR NOT detected in $phase (still on disk after ${elapsed}s) - ⚠️ scanning gap"
    fi
    return 0
}

# Resolve a canonical (unversioned) Homebrew node install and echo its bin dir.
#
# WHY THIS MATTERS: performance profiles match a process by its on-disk install
# location. Homebrew's *version-pinned* formulas (node@22, node@24) install under a
# differently-named directory than the canonical "node" formula, so a profile that
# targets the canonical node install may not cover a version-pinned one. If `node` on
# PATH resolves to a version-pinned build, the node profile can end up a no-op and
# Phase 3 (profiles) looks IDENTICAL to the baseline. Pin the build to the canonical
# node install so the demo actually exercises the profile it is demonstrating.
resolve_profiled_node_bin() {
    # Explicit override wins: accept either a node binary or the bin dir holding it.
    if [ -n "$FORCE_NODE" ]; then
        if [ -d "$FORCE_NODE" ] && [ -x "$FORCE_NODE/node" ]; then echo "$FORCE_NODE"; return 0; fi
        if [ -x "$FORCE_NODE" ]; then dirname "$FORCE_NODE"; return 0; fi
        return 1
    fi
    local candidates=(
        /opt/homebrew/opt/node/bin/node
        /usr/local/opt/node/bin/node
    )
    local c real
    for c in "${candidates[@]}"; do
        [ -x "$c" ] || continue
        real=$(readlink -f "$c" 2>/dev/null || echo "$c")
        case "$real" in
            */node@*/*) continue;;                       # skip version-pinned formulas
            */Cellar/node/*|*/opt/node/*) dirname "$c"; return 0;;
        esac
    done
    # Fall back to scanning for a canonical (unversioned) "node" formula.
    local d
    for d in /opt/homebrew/Cellar/node/*/bin /usr/local/Cellar/node/*/bin; do
        [ -x "$d/node" ] && { echo "$d"; return 0; }
    done
    return 1
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

    # Pin the build to a canonical node install the profile can cover (see
    # resolve_profiled_node_bin). Without this, a version-pinned node on PATH can make
    # the profile a no-op and Phase 3 looks identical to the baseline.
    local node_bin_dir
    if node_bin_dir=$(resolve_profiled_node_bin); then
        export PATH="$node_bin_dir:$PATH"
        print_success "Using canonical node install: $node_bin_dir/node"
    else
        print_info "No canonical node install found on this machine."
        print_info "  Performance profiles match node by its install location. A version-pinned"
        print_info "  formula (node@22 / node@24) may sit outside the profile's target layout, so"
        print_info "  Phase 3 could look identical to the baseline. Fix with: brew install node"
    fi

    # Generate the compile workload fresh on every run. A single hand-written source
    # file compiles in <1s, which is too small for MDE scan overhead to be
    # measurable. The generated modules make each build take ~20-40s and produce real
    # file I/O for Defender to scan. Regenerating each run clears any stale files (and
    # their Spotlight index residue) from a previous run. Override the size with
    # MDE_DEMO_MODULES.
    print_info "Generating fresh compile workload (clears previous run's files)..."
    node "$PROJECT_DIR/generate-workload.js"

    # Enable real-time protection statistics. This is the documented, accurate way
    # to measure MDE scan overhead (per-process "Total files scanned"). Without it,
    # the diagnostic snapshots are empty and only noisy wall-clock time remains.
    # Note: this config toggle does NOT require sudo, and returns a non-zero exit
    # code when the value is already set to the requested value ("same as current").
    print_info "Enabling real-time protection statistics..."
    local rtp_stats_out=$(mdatp config real-time-protection-statistics --value enabled 2>&1)
    if echo "$rtp_stats_out" | grep -qiE "updated|same as the current value"; then
        print_success "Real-time protection statistics enabled"
    else
        print_error "Could not enable real-time-protection-statistics: $rtp_stats_out"
        print_info "  Scan counts may be unavailable. If Tamper Protection is on, use troubleshooting mode."
    fi

    # Tamper Protection in block mode causes real-time-protection-statistics to
    # return null. Warn the user so they can use troubleshooting mode if needed.
    local tp_status=$(mdatp health --field tamper_protection 2>/dev/null | tr -d '"')
    if [ "$tp_status" = "block" ]; then
        print_info "Tamper Protection is in 'block' mode."
        print_info "  If MDE scan counts come back as 0, enable troubleshooting mode so"
        print_info "  real-time-protection-statistics can be captured (see the macOS perf TSG)."
    fi
    
    print_success "All prerequisites met"

    # The whole point of the demo is to show performance profiles reducing scan load
    # during a build. The vscode-tree profile only mutes node when node runs inside
    # VSCode's process tree. If the demo is launched from a plain terminal, node is a
    # child of bash (not VSCode) and profiles won't appear to help. Warn loudly.
    if ! under_vscode "$$"; then
        echo ""
        print_warning "This demo is NOT running inside VSCode's process tree."
        print_info "  The build's node will run as a child of this shell, outside VSCode."
        print_info "  The vscode-tree profile mutes VSCode's children, so it will NOT cover"
        print_info "  this build and Phase 3 (profiles) may look identical to the baseline."
        print_info "  For a representative result, run the demo from VSCode: open this folder"
        print_info "  in VSCode and run the \"MDE Demo: Run All Phases\" task (Terminal > Run Task),"
        print_info "  or launch ./run-demo.sh from VSCode's integrated terminal."
        if [ "${MDE_ALLOW_NON_VSCODE:-0}" != "1" ]; then
            print_info "  Set MDE_ALLOW_NON_VSCODE=1 to run anyway (results reflect terminal builds only)."
            exit 1
        fi
        print_warning "  MDE_ALLOW_NON_VSCODE=1 set — continuing outside VSCode."
    fi

    # Capture machine-specific facts so a report produced on a lab machine is
    # self-explaining (which node ran the build, its install layout, engine/tamper
    # state, installed formulas).
    capture_environment_diagnostics
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
    sudo mdatp exclusion folder add --path "$PROJECT_DIR/out.noindex"
    sudo mdatp exclusion folder add --path "$PROJECT_DIR/node_modules"
    sudo mdatp exclusion folder add --path "$PROJECT_DIR/.build"
    print_success "Exclusions added"
    
    # Run multiple builds to capture performance metrics
    echo ""
    run_builds "With Exclusions"
    
    test_eicar "exclusions"
    
    # Remove exclusions
    print_info "Removing exclusion paths..."
    sudo mdatp exclusion folder remove --path "$PROJECT_DIR/out.noindex"
    sudo mdatp exclusion folder remove --path "$PROJECT_DIR/node_modules"
    sudo mdatp exclusion folder remove --path "$PROJECT_DIR/.build"
    print_success "Exclusions removed"
}

# Phase 3: Performance Profiles
phase_profiles() {
    print_phase "Phase 3: Performance Profiles (protected build)"
    
    cleanup_profiles
    print_info "Applying profiles: $DEMO_PROFILES"
    
    cleanup_build
    
    local p
    for p in $DEMO_PROFILES; do
        sudo mdatp performance-profiles apply --name "$p"
    done
    print_success "Profiles applied: $DEMO_PROFILES"
    
    # Run multiple builds to capture performance metrics
    echo ""
    run_builds "With Performance Profiles"
    
    test_eicar "profiles"
    
    # Remove profiles
    print_info "Removing profiles..."
    for p in $DEMO_PROFILES; do
        sudo mdatp performance-profiles remove --name "$p"
    done
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
    # This config toggle does not require sudo.
    mdatp config real-time-protection-statistics --value disabled &>/dev/null || true
}

# Run
main
