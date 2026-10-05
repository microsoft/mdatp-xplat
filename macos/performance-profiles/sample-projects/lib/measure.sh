#!/bin/bash
# lib/measure.sh - Shared MDE performance-profile demo measurement engine.
#
# This library is SOURCED by each sample's run-demo.sh. It provides the generic
# three-phase demo (Baseline / AV Exclusions / Performance Profiles) and all the
# accurate measurement machinery (MDE scan-counter deltas, per-daemon CPU/RSS,
# during-build hot-event capture, and a real EICAR probe). The per-sample script
# supplies a small set of CONFIG variables and HOOK functions, then calls
# `demo_main`.
#
# ---------------------------------------------------------------------------
# CONTRACT — the sourcing script MUST define, BEFORE calling demo_main:
#
#   Config variables:
#     PROJECT_DIR          Absolute path to the sample dir (dirname of run-demo.sh).
#     LIB_DIR              Absolute path to this lib/ directory.
#     SAMPLE_TITLE         Human title, e.g. "Xcode / Swift build".
#     WORKLOAD_DIR         Absolute path to the (gitignored) build workload.
#     DEMO_PROFILES        Space-separated profiles applied in Phase 3 (e.g. "xcode git").
#     EXCLUDE_PATHS        Bash array of folder paths excluded in Phase 2.
#     EICAR_TARGET_DIR     Directory (inside an excluded path) to drop the EICAR probe.
#     REPORT_TITLE         Title rendered at the top of REPORT.md.
#     REPORT_EXCLUDED_NOTE One-line note describing the excluded folders.
#     REPORT_ENV_INTRO     One-line intro for the Environment Diagnostics section.
#   Optional:
#     IDE_TREE_PROFILE     The in-IDE process-tree profile (e.g. "xcode-ide-tree"),
#                          or "" if the tool has none.
#     IDE_PROCESS_MATCH    Substring identifying the IDE process in the ancestry
#                          (e.g. "Xcode.app"), used to detect in-IDE builds.
#     WARMUP_BUILDS        Number of discarded warm-up builds (default 1).
#     MEASURED_BUILDS      Number of measured builds per phase (default 3).
#
#   Hook functions:
#     check_tools          Verify sample-specific build tools exist and the workload
#                          is present (fetch via setup if needed). Exit non-zero on
#                          fatal error.
#     build_once           Run exactly one clean build of the workload (output
#                          discarded; timing is done by the caller).
#     cleanup_build        Remove build artifacts so each build is a full recompile.
#     capture_toolchain_diagnostics
#                          Echo a toolchain-specific block (compiler, SDK, workload
#                          commit) to stdout; captured into diagnostics.txt.
# ---------------------------------------------------------------------------

# --- Output helpers ---------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'; NC='\033[0m'
print_phase()   { echo -e "${BLUE}=== $1 ===${NC}"; }
print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_error()   { echo -e "${RED}✗ $1${NC}"; }
print_warning() { echo -e "${RED}⚠ $1${NC}"; }
print_info()    { echo -e "${YELLOW}ℹ $1${NC}"; }

# --- Accurate measurement helpers -------------------------------------------

# Sum of "totalFilesScanned" across every process, from MDE real-time protection
# statistics — the accurate, documented signal for MDE scan overhead (see the
# macOS performance TSG). Counts are cumulative since RTP started, so we snapshot
# before/after each phase and report the delta.
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
# whose truncated command name (ucomm) contains the given filter. MDE on macOS runs
# three cooperating daemons: "wdavdaemon" (privileged core/router),
# "wdavdaemon_enterprise" (EDR backend), and "wdavdaemon_unprivileged" (AV/RTP file
# scanner). Filter "wdavdaemon" sums all three; the longer filters isolate one.
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
# combined. Writes three lines to $1. Prints the sampler PID.
start_mem_sampler() {
    local out=$1
    printf 'unpriv 0.0\nenterprise 0.0\nall 0.0\n' > "$out"
    (
        pu=0; pe=0; pa=0
        while :; do
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

# --- Hot-event-source capture DURING the build window -----------------------
# mdatp diagnostic hot-event-sources streams cumulative "Top N Hot Event Sources"
# and "Top N Hot Event Targets" tables until interrupted. We run it in the
# background for the whole measured window, interrupt it, and keep the final tables.

start_hot_event_capture() {
    local raw=$1
    mdatp diagnostic hot-event-sources --output json >"$raw" 2>&1 &
    echo $!
}

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
# Targets" tables (plus summary) from a raw capture into a compact per-phase file.
# Sources = processes driving scans; Targets = files/paths scanned. Normalized with
# stable "=== Hot Event Sources/Targets ===" delimiters so the report can split them.
summarize_hot_events() {
    local raw=$1 out=$2
    sed 's/\x1b\[[0-9;]*m//g' "$raw" 2>/dev/null | awk '
        /^Total Events:/ {
            summary=$0
            if (cap=="tgt") { last_tgt=buf; cap="" }
        }
        /Top .* Hot Event Sources ===/ {
            if (cap=="tgt") { last_tgt=buf }
            cap="src"; buf=""; cur_hdr=summary; next
        }
        cap=="src" && /Hot Event Targets ===/ {
            last_src=buf; last_hdr=cur_hdr
            cap="tgt"; buf=""; next
        }
        cap { buf=buf $0 "\n" }
        END {
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

# --- Exclusion / profile management (generic via EXCLUDE_PATHS / DEMO_PROFILES) --

cleanup_exclusions() {
    local p
    for p in "${EXCLUDE_PATHS[@]}"; do
        sudo mdatp exclusion folder remove --path "$p" &>/dev/null || true
    done
}

cleanup_profiles() {
    local p
    for p in $DEMO_PROFILES ${IDE_TREE_PROFILE:-} git make-tree codesign; do
        sudo mdatp performance-profiles remove --name "$p" &>/dev/null || true
    done
}

capture_performance_snapshot() {
    local snapshot_file="$1" phase=$2
    {
        echo "=== $phase Performance Metrics ==="
        echo "Captured: $(date '+%Y-%m-%d %H:%M:%S')"
        echo ""
        echo "MDE Status:"
        mdatp health --field real_time_protection_enabled 2>/dev/null | xargs -I {} echo "  Real-time Protection: {}"
        mdatp health --field engine_version 2>/dev/null | xargs -I {} echo "  Engine: {}"
        echo ""
        echo "Active Exclusions:"
        mdatp exclusion list 2>/dev/null | grep -E "^Excluded|^Path:" | head -20 || echo "  None"
        echo ""
        echo "Applied Profiles:"
        mdatp performance-profiles list-applied 2>/dev/null | grep -E "^[a-z]|Merge policy" || echo "  None"
        echo ""
        echo "Hot Event Sources (Active Scanning):"
        mdatp diagnostic hot-event-sources 2>/dev/null | head -20 || echo "  (unable to capture)"
        echo ""
        echo "Real-time Protection Resource Usage:"
        mdatp diagnostic real-time-protection-statistics 2>/dev/null | head -15 || echo "  (unable to capture)"
        echo ""
    } > "$snapshot_file"
}

# --- Process-ancestry / in-IDE detection ------------------------------------

# Walk the parent-process chain from a PID up to launchd, echoing "pid command"
# for each ancestor. Shows HOW the build's toolchain was launched.
process_ancestry() {
    local pid=$1
    while [ -n "$pid" ] && [ "$pid" -gt 1 ] 2>/dev/null; do
        local line ppid comm
        line=$(ps -o ppid=,comm= -p "$pid" 2>/dev/null)
        [ -n "$line" ] || break
        ppid=$(echo "$line" | awk '{print $1}')
        comm=$(echo "$line" | sed -E 's/^[[:space:]]*[0-9]+[[:space:]]+//')
        echo "    $pid  $comm"
        pid=$ppid
    done
}

# Return 0 if any ancestor of $1 matches IDE_PROCESS_MATCH. The in-IDE `-tree`
# profile only suppresses scans for builds launched inside that IDE's process
# subtree; a terminal build is a child of the shell, not the IDE.
under_ide() {
    local pid=$1
    [ -n "${IDE_PROCESS_MATCH:-}" ] || return 1
    while [ -n "$pid" ] && [ "$pid" -gt 1 ] 2>/dev/null; do
        local line ppid comm
        line=$(ps -o ppid=,comm= -p "$pid" 2>/dev/null)
        [ -n "$line" ] || break
        ppid=$(echo "$line" | awk '{print $1}')
        comm=$(echo "$line" | sed -E 's/^[[:space:]]*[0-9]+[[:space:]]+//')
        case "$comm" in
            *"$IDE_PROCESS_MATCH"*) return 0;;
        esac
        pid=$ppid
    done
    return 1
}

# Capture machine-specific facts needed to interpret a report produced on a
# DIFFERENT machine. The generic host/MDE/profile/launch-context blocks live here;
# the toolchain-specific block is delegated to the capture_toolchain_diagnostics hook.
capture_environment_diagnostics() {
    local out="$RUN_DIR/diagnostics.txt"
    {
        echo "=== Environment Diagnostics ==="
        echo "Captured: $(date '+%Y-%m-%d %H:%M:%S')"
        echo "Sample: ${SAMPLE_TITLE:-(unnamed)}"
        [ -n "${REPORT_ENV_INTRO:-}" ] && echo "$REPORT_ENV_INTRO"
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
        # Toolchain-specific block supplied by the sample.
        capture_toolchain_diagnostics
        echo ""
        echo "Performance profiles:"
        echo "  Applied:"
        mdatp performance-profiles list-applied 2>/dev/null | sed 's/^/    /' || echo "    (unable to capture)"
        local p
        for p in $DEMO_PROFILES ${IDE_TREE_PROFILE:-}; do
            echo "  '$p' available: $(mdatp performance-profiles list-available 2>/dev/null | grep -qx "$p" && echo yes || echo no)"
        done
        echo ""
        echo "Launch context (does the build run inside the IDE's process tree?):"
        if [ -n "${IDE_TREE_PROFILE:-}" ]; then
            if under_ide "$$"; then
                echo "  Build process tree under ${IDE_PROCESS_MATCH:-IDE}: yes"
                echo "  -> the build runs inside the IDE subtree, so ${IDE_TREE_PROFILE} can also mute its scans."
            else
                echo "  Build process tree under ${IDE_PROCESS_MATCH:-IDE}: no (terminal build)"
                echo "  -> the build runs OUTSIDE the IDE subtree. ${IDE_TREE_PROFILE} would NOT cover it,"
                echo "     but the toolchain profile (matched by install location) still does."
            fi
        else
            echo "  (this tool has no in-IDE tree profile; the toolchain profile covers terminal builds)"
        fi
        echo "  Process ancestry (this script -> ... -> launchd):"
        process_ancestry "$$"
        echo ""
    } > "$out"
    print_success "Environment diagnostics captured: $out"
}

# --- The measured build loop (one phase) ------------------------------------
run_builds() {
    local phase=$1
    local num_builds=${2:-${MEASURED_BUILDS:-3}}
    local phase_name=$(echo "$phase" | tr ' ' '_' | tr '[:upper:]' '[:lower:]')
    local snapshot_before="$RUN_DIR/${phase_name}_before.txt"
    local snapshot_after="$RUN_DIR/${phase_name}_after.txt"

    print_info "Running $num_builds builds to measure performance..."
    print_info "Logs: $RUN_DIR"

    capture_performance_snapshot "$snapshot_before" "$phase (Before)"

    # Warm-up build(s) (discarded): the first build pays cold-cache costs that would
    # skew the numbers. Not counted in any statistic.
    local w
    for w in $(seq 1 ${WARMUP_BUILDS:-1}); do
        print_info "Warm-up build (discarded)..."
        build_once || true
    done

    local scans_before=$(scan_total_files)
    local scan_ns_before=$(scan_total_time_ns)
    local cpu_all_before=$(mde_cpu_seconds wdavdaemon)
    local cpu_unpr_before=$(mde_cpu_seconds wdavdaemon_unpri)
    local cpu_ent_before=$(mde_cpu_seconds wdavdaemon_enter)
    local wall_start=$(date +%s.%N)
    local mem_file=$(mktemp)
    local mem_sampler_pid=$(start_mem_sampler "$mem_file")

    local hot_raw=$(mktemp)
    local hot_events_file="$RUN_DIR/${phase_name}_hot_events.txt"
    local hot_events_pid=$(start_hot_event_capture "$hot_raw")

    local build_times=()
    local i
    for i in $(seq 1 $num_builds); do
        local output=$( { time build_once; } 2>&1 )
        local real_time=$(echo "$output" | grep "^real" | head -1 | awk '{print $2}')
        if [ -n "$real_time" ]; then
            local seconds=$(echo "$real_time" | sed 's/m/:/' | sed 's/s$//' | awk -F: '{print $1*60+$2}')
            build_times+=("$seconds")
        fi
        echo -n "."
    done
    echo ""

    local scans_after=$(scan_total_files)
    local scan_ns_after=$(scan_total_time_ns)
    local scans_delta=$(( scans_after - scans_before ))
    local scan_ms_delta=$(echo "scale=1; ($scan_ns_after - $scan_ns_before) / 1000000" | bc 2>/dev/null)

    local cpu_all_after=$(mde_cpu_seconds wdavdaemon)
    local cpu_unpr_after=$(mde_cpu_seconds wdavdaemon_unpri)
    local cpu_ent_after=$(mde_cpu_seconds wdavdaemon_enter)
    local wall_end=$(date +%s.%N)
    kill "$mem_sampler_pid" 2>/dev/null || true
    local peak_mem_mb=$(awk '/^unpriv/{print $2}' "$mem_file" 2>/dev/null)
    local peak_mem_ent_mb=$(awk '/^enterprise/{print $2}' "$mem_file" 2>/dev/null)
    local peak_mem_all_mb=$(awk '/^all/{print $2}' "$mem_file" 2>/dev/null)
    rm -f "$mem_file" 2>/dev/null || true

    stop_hot_event_capture "$hot_events_pid"
    summarize_hot_events "$hot_raw" "$hot_events_file"
    rm -f "$hot_raw" 2>/dev/null || true
    print_info "Top scan sources during build:"
    sed 's/^/    /' "$hot_events_file" 2>/dev/null | head -8

    local window=$(echo "$wall_end - $wall_start" | bc 2>/dev/null)
    local cpu_all_pct=$(echo "scale=2; ($cpu_all_after - $cpu_all_before) / $window * 100" | bc 2>/dev/null)
    local cpu_unpr_pct=$(echo "scale=2; ($cpu_unpr_after - $cpu_unpr_before) / $window * 100" | bc 2>/dev/null)
    local cpu_ent_pct=$(echo "scale=2; ($cpu_ent_after - $cpu_ent_before) / $window * 100" | bc 2>/dev/null)

    capture_performance_snapshot "$snapshot_after" "$phase (After)"

    if [ ${#build_times[@]} -gt 0 ]; then
        local total=0 t
        for t in "${build_times[@]}"; do total=$(echo "$total + $t" | bc 2>/dev/null); done
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

    [ -f "$snapshot_before" ] && { cat "$snapshot_before"; echo ""; }
    [ -f "$snapshot_after" ]  && { cat "$snapshot_after"; echo ""; }
}

# --- EICAR probe ------------------------------------------------------------

# Number of entries in the MDE threat list (one "Id:" line per detection).
threat_count() {
    mdatp threat list 2>/dev/null | grep -c '^[[:space:]]*Id:' || true
}

# Drop a real EICAR test file into EICAR_TARGET_DIR and determine whether RTP catches
# it (threat count rises, or the file is quarantined). Writes the ACTUAL result to
# <phase>_eicar.txt. In the exclusions phase this dir is excluded, so the file should
# NOT be detected — demonstrating the protection gap.
test_eicar() {
    local phase=$1
    local out="$RUN_DIR/${phase}_eicar.txt"
    local target_dir="$EICAR_TARGET_DIR"
    local timeout=${MDE_EICAR_TIMEOUT:-30} poll=1 elapsed=0
    print_info "Testing EICAR detection in $phase..."
    mkdir -p "$target_dir"

    local eicar_path="$target_dir/eicar_$(date +%s).txt"
    local before after detected=0 file_removed=0
    before=$(threat_count)

    EICAR_CONTENT='X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*' \
        /bin/sh -c 'printf "%s" "$EICAR_CONTENT" > "$1"' sh "$eicar_path" 2>/dev/null || true

    while [ "$elapsed" -lt "$timeout" ]; do
        after=$(threat_count)
        if [ "${after:-0}" -gt "${before:-0}" ]; then detected=1; break; fi
        if [ ! -f "$eicar_path" ]; then detected=1; file_removed=1; break; fi
        sleep "$poll"; elapsed=$((elapsed + poll))
    done
    after=$(threat_count)
    [ -f "$eicar_path" ] || file_removed=1
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

# --- Prerequisites ----------------------------------------------------------
check_prerequisites() {
    print_phase "Checking prerequisites"

    if ! command -v mdatp &> /dev/null; then
        print_error "mdatp CLI not found. Install Microsoft Defender for Endpoint on macOS."
        exit 1
    fi
    if ! mdatp health --field real_time_protection_enabled | grep -q "true"; then
        print_error "Real-time protection is not enabled. Enable it first."
        exit 1
    fi

    # Sample-specific tool checks + workload readiness.
    check_tools

    # Enable real-time protection statistics — the documented, accurate way to
    # measure MDE scan overhead. Does NOT require sudo.
    print_info "Enabling real-time protection statistics..."
    local rtp_stats_out=$(mdatp config real-time-protection-statistics --value enabled 2>&1)
    if echo "$rtp_stats_out" | grep -qiE "updated|same as the current value"; then
        print_success "Real-time protection statistics enabled"
    else
        print_error "Could not enable real-time-protection-statistics: $rtp_stats_out"
        print_info "  Scan counts may be unavailable. If Tamper Protection is on, use troubleshooting mode."
    fi

    local tp_status=$(mdatp health --field tamper_protection 2>/dev/null | tr -d '"')
    if [ "$tp_status" = "block" ]; then
        print_info "Tamper Protection is in 'block' mode."
        print_info "  If MDE scan counts come back as 0, enable troubleshooting mode so"
        print_info "  real-time-protection-statistics can be captured (see the macOS perf TSG)."
    fi

    print_success "All prerequisites met"

    # Warn if an in-IDE tree profile was requested for a terminal build.
    if [ -n "${IDE_TREE_PROFILE:-}" ] && ! under_ide "$$" \
        && echo " $DEMO_PROFILES " | grep -q " ${IDE_TREE_PROFILE} "; then
        echo ""
        print_warning "${IDE_TREE_PROFILE} is in DEMO_PROFILES but this build is NOT inside the IDE's process tree."
        print_info "  ${IDE_TREE_PROFILE} only mutes builds launched from the IDE, so it will not cover this"
        print_info "  terminal build. The toolchain profile still applies. To exercise ${IDE_TREE_PROFILE},"
        print_info "  build from within the IDE instead."
    fi

    capture_environment_diagnostics
}

# --- Phases -----------------------------------------------------------------
phase_baseline() {
    print_phase "Phase 1: Baseline Build (no optimizations)"
    cleanup_exclusions
    cleanup_profiles
    print_info "Building with full scanning..."
    cleanup_build
    echo "Current exclusions:"; mdatp exclusion list 2>/dev/null || echo "None"
    echo "Current profiles:"; mdatp performance-profiles list-applied 2>/dev/null || echo "None"
    echo ""
    run_builds "Baseline (Full Scanning)"
    test_eicar "baseline"
}

phase_exclusions() {
    print_phase "Phase 2: AV Exclusions (protection gap)"
    cleanup_exclusions
    print_info "Adding exclusion paths for build directories..."
    cleanup_build
    local p
    for p in "${EXCLUDE_PATHS[@]}"; do
        sudo mdatp exclusion folder add --path "$p"
    done
    print_success "Exclusions added"
    echo ""
    run_builds "With Exclusions"
    test_eicar "exclusions"
    print_info "Removing exclusion paths..."
    for p in "${EXCLUDE_PATHS[@]}"; do
        sudo mdatp exclusion folder remove --path "$p"
    done
    print_success "Exclusions removed"
}

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
    echo ""
    run_builds "With Performance Profiles"
    test_eicar "profiles"
    print_info "Removing profiles..."
    for p in $DEMO_PROFILES; do
        sudo mdatp performance-profiles remove --name "$p"
    done
    print_success "Profiles removed"
}

# --- Summary + report -------------------------------------------------------
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
    [ "$log_count" -gt 0 ] && echo "  Files: $log_count diagnostic snapshots captured"
    echo ""
}

# Minimal JSON string encoder for the small config values below.
json_str() {
    printf '%s' "$1" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'
}

# Write the per-run config the shared report generator reads, then render REPORT.md.
generate_report() {
    cat > "$RUN_DIR/report-config.json" <<EOF
{
  "title": $(json_str "${REPORT_TITLE:-MDE Performance Profile Demo Report}"),
  "excludedNote": $(json_str "${REPORT_EXCLUDED_NOTE:-}"),
  "envIntro": $(json_str "${REPORT_ENV_INTRO:-}")
}
EOF
    print_info "Generating report..."
    if command -v node &> /dev/null; then
        if node "$LIB_DIR/generate-report.js" "$RUN_DIR"; then
            print_success "Report generated successfully"
        else
            print_error "Failed to generate report"
        fi
    else
        print_error "Node.js not found - skipping report generation"
    fi
}

# --- Entry point ------------------------------------------------------------
demo_main() {
    # Per-run diagnostic logs + report.
    RUN_DIR="${RUN_DIR:-$PROJECT_DIR/run-logs/$(date +%Y%m%d_%H%M%S)}"
    mkdir -p "$RUN_DIR"

    check_prerequisites

    print_info "Caching sudo credentials..."
    sudo -v

    phase_baseline
    echo ""
    phase_exclusions
    echo ""
    phase_profiles

    print_summary
    generate_report
}
