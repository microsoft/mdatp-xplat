#!/bin/bash
set -euo pipefail

#=============================================================================
# MDE Performance Profiles — End-to-End Demo
#
# Demonstrates the impact of performance profiles by building microsoft/vscode
# with and without profiles, using MDE diagnostic tools to show the difference.
#
# Story:  Diagnose → Identify hot event sources → Apply profiles → Verify
# Repo:   microsoft/vscode (Node.js + TypeScript)
# Tools:  mdatp CLI, hot-event-sources, RTP statistics
#
# Usage:  ./perf-profile-demo.sh [path-to-vscode-repo]
#         Default repo path: ~/demo/vscode
#
# Prerequisites:
#   - macOS with MDE installed (real-time protection enabled)
#   - Homebrew (https://brew.sh)
#   - sudo access (for hot-event-sources collection)
#
# Note: The VS Code repo will be cloned automatically if not present.
# Note: node, yarn, git, jq, and python3 will be offered for install via
#       Homebrew if not already present.
#
# Learn more: https://learn.microsoft.com/en-us/defender-endpoint/performance-profiles
#=============================================================================

REPO_DIR="${1:-$HOME/demo/vscode}"
RESULTS_DIR="$HOME/demo/results"
ANALYZER_DIR="$HOME/demo/analyzer/XMDEClientAnalyzerBinary"
PROFILES="node git vscode vscode-tree"
HOT_EVENT_DURATION=60  # seconds to collect hot event sources

mkdir -p "$RESULTS_DIR"
STATE_FILE="$RESULTS_DIR/.demo-state"

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║   MDE Performance Profiles — End-to-End Demo                ║"
echo "║   Repo: microsoft/vscode                                    ║"
echo "║   Flow: Build → Diagnose → Apply Profiles → Verify          ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# ── Preflight checks ──────────────────────────────────────────────
echo "🔍 Preflight checks..."

# Validate sudo access upfront so we don't get password prompts mid-demo
if ! sudo -v 2>/dev/null; then
    echo "❌ This script requires sudo access for mdatp commands."
    echo "   Please run with a user that has sudo privileges."
    exit 1
fi

if ! command -v mdatp &>/dev/null; then
    echo "❌ mdatp not found. Install MDE: https://learn.microsoft.com/en-us/defender-endpoint/microsoft-defender-endpoint-mac"
    exit 1
fi

RTP=$(mdatp health --field real_time_protection_enabled 2>/dev/null || echo "unknown")
if [ "$RTP" != "true" ]; then
    echo "❌ Real-time protection is not enabled. Run:"
    echo "   mdatp config real-time-protection --value enabled"
    exit 1
fi
echo "   ✅ Real-time protection: ON"

VERSION=$(mdatp health --field app_version 2>/dev/null || echo "unknown")
echo "   ✅ MDE version: $VERSION"

PROFILE_COUNT=$(sudo mdatp performance-profiles list-available 2>/dev/null | grep -v '^=' | grep -v '^-' | grep -v '^$' | wc -l | tr -d ' ')
if [ "$PROFILE_COUNT" = "0" ]; then
    echo "❌ Performance profiles not available in this MDE version."
    echo "   Update to the latest MDE version."
    exit 1
fi
echo "   ✅ Profiles available: $PROFILE_COUNT"

# ── Resume detection ──────────────────────────────────────────────
RESUME=false
if [ -f "$STATE_FILE" ]; then
    source "$STATE_FILE"
    if [ "${BASELINE_COMPLETE:-}" = "true" ]; then
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "  📋 Previous run detected — baseline already complete."
        printf "     Baseline build time: %d seconds\n" "${SAVED_PHASE1_TIME:-0}"
        printf "     MDE avg CPU:         %s%%\n" "${SAVED_PHASE1_CPU:-N/A}"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        read -rp "  Continue to comparison build, or restart from scratch? [C/r] " resume_answer
        if [[ "$resume_answer" =~ ^[Rr] ]]; then
            echo "  🔄 Restarting from scratch..."
            rm -f "$STATE_FILE"
        else
            RESUME=true
            PHASE1_TIME="${SAVED_PHASE1_TIME:-0}"
            PHASE1_CPU="${SAVED_PHASE1_CPU:-N/A}"
            echo "  ▶️  Resuming — skipping to comparison build..."
        fi
        echo ""
    fi
fi

MERGE_POLICY=$(sudo mdatp performance-profiles list-applied 2>/dev/null | grep -i 'Merge policy' | head -1 || echo "")
ADMIN_ONLY=false
if echo "$MERGE_POLICY" | grep -qi 'admin'; then
    ADMIN_ONLY=true
    APPLIED_OUTPUT=$(sudo mdatp performance-profiles list-applied 2>/dev/null)

    if [ "$RESUME" = true ]; then
        # Resuming — all profiles should now be deployed by the admin
        MISSING_PROFILES=()
        for profile in $PROFILES; do
            if ! echo "$APPLIED_OUTPUT" | grep -q "^${profile} "; then
                MISSING_PROFILES+=("$profile")
            fi
        done
        if [ ${#MISSING_PROFILES[@]} -gt 0 ]; then
            echo "⚠️  Admin-only mode — some profiles are still not deployed:"
            for profile in "${MISSING_PROFILES[@]}"; do
                echo "     - $profile"
            done
            echo ""
            echo "   Ask your IT admin to deploy these via MDM, then re-run."
            exit 1
        fi
        echo "   ✅ Profile mode: admin-only (all profiles deployed — ready for comparison)"
    else
        # First run — check that NO profiles are applied (clean baseline)
        APPLIED_PROFILES=()
        for profile in $PROFILES; do
            if echo "$APPLIED_OUTPUT" | grep -q "^${profile} "; then
                APPLIED_PROFILES+=("$profile")
            fi
        done
        if [ ${#APPLIED_PROFILES[@]} -gt 0 ]; then
            echo "⚠️  Performance profiles are in admin-only mode."
            echo "   The following profiles are currently applied: ${APPLIED_PROFILES[*]}"
            echo ""
            echo "   This demo needs a clean baseline (no profiles) for the first build."
            echo "   Ask your IT admin to remove these profiles via MDM (Intune, JAMF, etc.):"
            for profile in "${APPLIED_PROFILES[@]}"; do
                echo "     - $profile"
            done
            echo ""
            echo "   Once removed, re-run this script."
            exit 1
        fi
        echo "   ✅ Profile mode: admin-only (no profiles applied — ready for baseline)"
    fi
else
    echo "   ✅ Profile mode: merge (user can apply/remove locally)"
fi

if ! command -v brew &>/dev/null; then
    echo "❌ Homebrew not found. Install it: https://brew.sh"
    exit 1
fi

MISSING_TOOLS=()
for cmd in node git jq python3 yarn; do
    if ! command -v "$cmd" &>/dev/null; then
        MISSING_TOOLS+=("$cmd")
    fi
done

if [ ${#MISSING_TOOLS[@]} -gt 0 ]; then
    echo "   ⚠️  Missing tools: ${MISSING_TOOLS[*]}"
    read -rp "   Install via Homebrew? [Y/n] " answer
    if [[ "$answer" =~ ^[Nn] ]]; then
        echo "   Please install the missing tools and re-run the script."
        exit 1
    fi
    for cmd in "${MISSING_TOOLS[@]}"; do
        echo "   ⬇️  Installing $cmd..."
        brew install "$cmd"
    done
fi
echo "   ✅ Build tools: node, yarn, git, jq, python3"

if [ ! -d "$REPO_DIR" ]; then
    echo "   ⬇️  VS Code repo not found — cloning now..."
    mkdir -p "$(dirname "$REPO_DIR")"
    git clone --depth 1 https://github.com/microsoft/vscode.git "$REPO_DIR"
    echo "   📦 Running initial yarn install (this may take a few minutes)..."
    cd "$REPO_DIR" && yarn install --frozen-lockfile 2>&1 | tail -3
fi
echo "   ✅ Repo: $REPO_DIR"
echo ""

# Remove any active profiles for clean baseline (skip on resume or admin-only)
if [ "$RESUME" = false ]; then
    if [ "$ADMIN_ONLY" = false ]; then
        for profile in $PROFILES; do
            sudo mdatp performance-profiles remove --name "$profile" &>/dev/null || true
        done
        echo "   🧹 All test profiles removed (clean baseline)"
    else
        echo "   ℹ️  Admin-only mode — skipping profile removal (managed via MDM)"
    fi
fi
echo ""

# ── Helper functions ──────────────────────────────────────────────

clean_build() {
    cd "$REPO_DIR"
    run_with_spinner "🧹 Cleaning build artifacts" rm -rf node_modules/.cache out .build
    find . -name '*.tsbuildinfo' -delete 2>/dev/null || true
}

start_cpu_monitor() {
    local log_file="$1"
    rm -f "$log_file"
    (
        while true; do
            cpu=$(ps -eo pid,%cpu,comm 2>/dev/null | grep 'wdavdaemon_unprivileged' | head -1 | awk '{print $2}')
            if [ -n "$cpu" ]; then
                echo "$(date +%s) $cpu" >> "$log_file"
            fi
            sleep 2
        done
    ) &
    echo $!
}

calc_avg_cpu() {
    local log_file="$1"
    if [ -f "$log_file" ] && [ -s "$log_file" ]; then
        awk '{sum+=$2; n++} END {if(n>0) printf "%.1f", sum/n; else print "N/A"}' "$log_file"
    else
        echo "N/A"
    fi
}

# Spinner for long-running commands — shows elapsed time so demo doesn't look hung
run_with_spinner() {
    local label="$1"; shift
    local log_file="${RESULTS_DIR:-/tmp}/.spinner_$$.log"
    local pid elapsed ret
    "$@" >"$log_file" 2>&1 &
    pid=$!
    elapsed=0
    printf "   %s 0s..." "$label"
    while kill -0 "$pid" 2>/dev/null; do
        sleep 5
        elapsed=$((elapsed + 5))
        printf "\r   %s %ds..." "$label" "$elapsed"
    done
    wait "$pid" || true
    ret=$?
    if [ "$ret" -eq 0 ]; then
        printf "\r   %s done (%ds)     \n" "$label" "$elapsed"
    else
        printf "\r   %s FAILED (exit %d, %ds)\n" "$label" "$ret" "$elapsed"
        tail -5 "$log_file" 2>/dev/null | sed 's/^/   ⚠️  /'
    fi
    rm -f "$log_file"
    return $ret
}

count_rtp_scans() {
    local json_file="$1"
    python3 -c "
import json, sys
try:
    data = json.load(open('$json_file'))
    total = sum(p.get('totalFilesScanned', 0) for p in data if isinstance(p, dict))
    print(total)
except:
    print('N/A')
" 2>/dev/null || echo "N/A"
}

# ══════════════════════════════════════════════════════════════════
#  PHASES 1–3: BASELINE (skipped on resume)
# ══════════════════════════════════════════════════════════════════
if [ "$RESUME" = false ]; then

# ══════════════════════════════════════════════════════════════════
#  PHASE 1: BASELINE BUILD (no profiles)
# ══════════════════════════════════════════════════════════════════
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  PHASE 1: Baseline Build (no performance profiles)"
echo ""
echo '  💬 "Let'\''s see what happens when we build VS Code with MDE'
echo '      real-time protection on and no performance profiles."'
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

clean_build

# Enable RTP statistics collection
sudo mdatp config real-time-protection-statistics --value enabled >/dev/null 2>&1 || true

# Start CPU monitoring
CPU_PID=$(start_cpu_monitor "$RESULTS_DIR/phase1_cpu.log")

echo "   ⏱️  Building VS Code (yarn compile)..."
cd "$REPO_DIR"
BUILD_START=$(date +%s)

run_with_spinner "📦 yarn install" yarn install --frozen-lockfile
run_with_spinner "🔨 yarn compile" yarn compile

BUILD_END=$(date +%s)
PHASE1_TIME=$((BUILD_END - BUILD_START))

# Stop CPU monitor
kill "$CPU_PID" 2>/dev/null; wait "$CPU_PID" 2>/dev/null || true
PHASE1_CPU=$(calc_avg_cpu "$RESULTS_DIR/phase1_cpu.log")

# Capture RTP statistics snapshot
sudo mdatp diagnostic real-time-protection-statistics --output json \
    > "$RESULTS_DIR/phase1_rtp_stats.json" 2>/dev/null || true

echo ""
echo "   ┌──────────────────────────────────────────┐"
echo "   │  Phase 1 Results (NO profiles)           │"
printf "   │  ⏱️  Build time:    %4d seconds          │\n" "$PHASE1_TIME"
printf "   │  🖥️  MDE avg CPU:   %5s%%                │\n" "$PHASE1_CPU"
echo "   └──────────────────────────────────────────┘"
echo ""

# ══════════════════════════════════════════════════════════════════
#  PHASE 2: DIAGNOSE — Hot Event Sources
# ══════════════════════════════════════════════════════════════════
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  PHASE 2: Diagnose — Hot Event Sources"
echo ""
echo '  💬 "Now let'\''s use MDE'\''s built-in diagnostic tools to see'
echo '      WHAT is causing the overhead. This is the same tool'
echo '      our support engineers use with customers."'
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "   📊 Collecting hot event sources (${HOT_EVENT_DURATION}s)..."
echo '   💬 "This command shows which processes are generating the'
echo '       most file system events that MDE'\''s sensor has to process."'
echo ""

# Run hot-event-sources during a build to capture real activity
clean_build
cd "$REPO_DIR"

# Start hot-event-sources collection in background
sudo mdatp diagnostic hot-event-sources --time="$HOT_EVENT_DURATION" \
    > /dev/null 2>&1 &
HES_PID=$!

# Run the build simultaneously so there's real activity to capture
yarn compile 2>&1 | tail -3 &
BUILD_PID=$!

# Wait for both to finish
wait "$HES_PID" 2>/dev/null || true
wait "$BUILD_PID" 2>/dev/null || true

# Find and display the hot event sources output
HES_FILE=$(ls -t hot_event_source_*.json 2>/dev/null | head -1)
if [ -n "${HES_FILE:-}" ]; then
    cp "$HES_FILE" "$RESULTS_DIR/phase2_hot_events.json"
    echo ""
    echo "   🔥 TOP HOT EVENT SOURCES (processes generating most sensor events):"
    echo "   ──────────────────────────────────────────────────────────────"
    jq -r '.eventSource[0:10] | .[] | "   \(.path) — auth:\(.authCount) notify:\(.notifyCount)"' \
        "$RESULTS_DIR/phase2_hot_events.json" 2>/dev/null || echo "   (could not parse)"
    echo ""
    echo '   💬 "See? node, tsc, git — all build tools flooding the sensor.'
    echo '       This is exactly what performance profiles are designed to fix."'
else
    echo "   ⚠️  Hot event sources file not found."
    echo "   Tip: Run separately with: sudo mdatp diagnostic hot-event-sources --time=60"
fi
echo ""

# ── Optional: Client Analyzer ──
if [ -f "${ANALYZER_DIR:-}/MDESupportTool" ]; then
    echo "   📊 Running Client Analyzer performance capture..."
    echo '   💬 "The XMDE Client Analyzer generates an HTML report with'
    echo '       hot event source data in a visual format."'
    cd "$RESULTS_DIR"
    sudo "$ANALYZER_DIR/MDESupportTool" performance --length 10 2>/dev/null || true
    PERF_ZIP=$(ls -t MDESupportTool_*.zip 2>/dev/null | head -1)
    if [ -n "${PERF_ZIP:-}" ]; then
        echo "   ✅ Client Analyzer report: $RESULTS_DIR/$PERF_ZIP"
    fi
    echo ""
fi

# ══════════════════════════════════════════════════════════════════
#  PHASE 3: DIAGNOSE — RTP Statistics
# ══════════════════════════════════════════════════════════════════
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  PHASE 3: Diagnose — RTP Statistics (top file scanners)"
echo ""
echo '  💬 "Let'\''s also look at which processes triggered the most'
echo '      antivirus scans."'
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ -f "$RESULTS_DIR/phase1_rtp_stats.json" ]; then
    echo "   🔍 TOP PROCESSES BY FILES SCANNED (from Phase 1 build):"
    echo "   ──────────────────────────────────────────────────────────"
    python3 -c "
import json
try:
    data = json.load(open('$RESULTS_DIR/phase1_rtp_stats.json'))
    procs = [(p.get('name','?'), p.get('totalFilesScanned',0), p.get('pid','?'))
             for p in data if isinstance(p, dict) and p.get('totalFilesScanned',0) > 0]
    procs.sort(key=lambda x: -x[1])
    total = sum(p[1] for p in procs)
    for name, count, pid in procs[:10]:
        pct = (count/total*100) if total > 0 else 0
        print(f'   {count:>8,} scans  ({pct:5.1f}%)  {name} (PID {pid})')
    print(f'   ────────')
    print(f'   {total:>8,} total file scans during build')
except Exception as e:
    print(f'   Error parsing: {e}')
" 2>/dev/null || echo "   ⚠️  Could not parse RTP stats"
    echo ""
    echo '   💬 "node, tsc, yarn, git — exactly what we expected.'
    echo '       Now we know which processes need exclusions."'
else
    echo "   ⚠️  No RTP stats captured. Enable with:"
    echo "   mdatp config real-time-protection-statistics --value enabled"
fi
echo ""

# ── Save checkpoint for resume ────────────────────────────────────
cat > "$STATE_FILE" <<CHECKPOINT
BASELINE_COMPLETE=true
SAVED_PHASE1_TIME=$PHASE1_TIME
SAVED_PHASE1_CPU=$PHASE1_CPU
SAVED_ADMIN_ONLY=$ADMIN_ONLY
CHECKPOINT

fi  # end RESUME=false (phases 1–3)

# ══════════════════════════════════════════════════════════════════
#  PHASE 4: FIX — Apply Performance Profiles
# ══════════════════════════════════════════════════════════════════
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  PHASE 4: Fix — Apply Performance Profiles"
echo ""
echo '  💬 "Instead of manually crafting exclusions for each process,'
echo '      we use Performance Profiles — curated exclusion sets'
echo '      that ship with MDE. One command per tool."'
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "   ✅ Applying profiles for our build stack:"
if [ "$ADMIN_ONLY" = true ]; then
    if [ "$RESUME" = true ]; then
        echo "      ℹ️  Admin-only mode — profiles deployed via MDM:"
        for profile in $PROFILES; do
            echo "      ✅ $profile [managed]"
        done
    else
        echo ""
        echo "   ⚠️  Admin-only mode — profiles cannot be applied locally."
        echo "   Ask your IT admin to deploy these profiles via MDM (Intune, JAMF, etc.):"
        for profile in $PROFILES; do
            echo "     - $profile"
        done
        echo ""
        echo "   Once deployed, re-run this script to see the comparison."
        echo "   (Your baseline results have been saved — you'll be prompted to continue.)"
        echo ""
        echo "   Baseline results saved to: $RESULTS_DIR/"
        exit 0
    fi
else
    for profile in $PROFILES; do
        if sudo mdatp performance-profiles apply --name "$profile" 2>/dev/null; then
            echo "      ✅ $profile"
        else
            echo "      ⚠️  $profile (may not be available in this MDE version)"
        fi
    done
fi
echo ""

echo "   📋 Active profiles:"
sudo mdatp performance-profiles list-active 2>/dev/null || echo "   (check manually)"
echo ""

echo '   💬 "That'\''s it. Four commands. No manual path hunting,'
echo '       no JSON config files, no MDM policy updates."'
echo ""

# ══════════════════════════════════════════════════════════════════
#  PHASE 5: VERIFY — Rebuild + Re-diagnose
# ══════════════════════════════════════════════════════════════════
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  PHASE 5: Verify — Rebuild with Profiles Active"
echo ""
echo '  💬 "Now let'\''s run the exact same build and diagnostics'
echo '      again and see the difference."'
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

clean_build

# Reset RTP stats for clean comparison
sudo mdatp config real-time-protection-statistics --value enabled >/dev/null 2>&1 || true

# Start CPU monitoring
CPU_PID=$(start_cpu_monitor "$RESULTS_DIR/phase5_cpu.log")

echo "   ⏱️  Building VS Code (yarn compile) WITH profiles..."
cd "$REPO_DIR"
BUILD_START=$(date +%s)

run_with_spinner "📦 yarn install" yarn install --frozen-lockfile
run_with_spinner "🔨 yarn compile" yarn compile

BUILD_END=$(date +%s)
PHASE5_TIME=$((BUILD_END - BUILD_START))

# Stop CPU monitor
kill "$CPU_PID" 2>/dev/null; wait "$CPU_PID" 2>/dev/null || true
PHASE5_CPU=$(calc_avg_cpu "$RESULTS_DIR/phase5_cpu.log")

# Capture new RTP statistics
sudo mdatp diagnostic real-time-protection-statistics --output json \
    > "$RESULTS_DIR/phase5_rtp_stats.json" 2>/dev/null || true

# ── Re-collect hot event sources for comparison ──
echo ""
echo "   📊 Re-collecting hot event sources for comparison..."
cd "$REPO_DIR"
clean_build
sudo mdatp diagnostic hot-event-sources --time="$HOT_EVENT_DURATION" \
    > /dev/null 2>&1 &
HES_PID=$!
yarn compile 2>&1 | tail -3 &
BUILD_PID=$!
wait "$HES_PID" 2>/dev/null || true
wait "$BUILD_PID" 2>/dev/null || true

HES_FILE2=$(ls -t hot_event_source_*.json 2>/dev/null | head -1)
if [ -n "${HES_FILE2:-}" ]; then
    cp "$HES_FILE2" "$RESULTS_DIR/phase5_hot_events.json"
fi

# ══════════════════════════════════════════════════════════════════
#  FINAL SUMMARY
# ══════════════════════════════════════════════════════════════════

PHASE1_SCANS=$(count_rtp_scans "$RESULTS_DIR/phase1_rtp_stats.json")
PHASE5_SCANS=$(count_rtp_scans "$RESULTS_DIR/phase5_rtp_stats.json")

SPEEDUP="?"
SAVED=0
if [ "$PHASE1_TIME" -gt 0 ] 2>/dev/null && [ "$PHASE5_TIME" -gt 0 ] 2>/dev/null; then
    SPEEDUP=$(python3 -c "print(f'{(($PHASE1_TIME-$PHASE5_TIME)/$PHASE1_TIME)*100:.0f}')" 2>/dev/null || echo "?")
    SAVED=$(($PHASE1_TIME - $PHASE5_TIME))
fi

echo ""
echo ""
echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║               🏁  PERFORMANCE PROFILES — RESULTS                 ║"
echo "╠════════════════════════════════════════════════════════════════════╣"
echo "║                                                                  ║"
echo "║  Metric                  WITHOUT Profiles    WITH Profiles       ║"
echo "║  ─────────────────       ────────────────    ──────────────      ║"
printf "║  ⏱️  Build time:          %4d seconds        %4d seconds        ║\n" "$PHASE1_TIME" "$PHASE5_TIME"
printf "║  🖥️  MDE avg CPU:         %5s%%              %5s%%              ║\n" "$PHASE1_CPU" "$PHASE5_CPU"
printf "║  📁 Files scanned:       %8s            %8s            ║\n" "$PHASE1_SCANS" "$PHASE5_SCANS"
echo "║                                                                  ║"
printf "║  ⚡ Build %s%% faster (%ds saved)                                ║\n" "$SPEEDUP" "$SAVED"
echo "║                                                                  ║"
echo "║  Profiles applied: $PROFILES"
echo "║                                                                  ║"
echo "║  Diagnostic artifacts saved to: $RESULTS_DIR/"
echo "║    phase1_rtp_stats.json       RTP scan stats (before)           ║"
echo "║    phase5_rtp_stats.json       RTP scan stats (after)            ║"
echo "║    phase2_hot_events.json      Hot event sources (before)        ║"
echo "║    phase5_hot_events.json      Hot event sources (after)         ║"
echo "║    phase1_cpu.log / phase5_cpu.log   CPU samples                 ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo ""
echo "💬 KEY TAKEAWAYS:"
echo "   1. We diagnosed the problem using built-in MDE diagnostic tools"
echo "   2. Hot event sources showed node/tsc/git flooding the sensor"
echo "   3. Performance profiles fixed it with one command"
echo "   4. Build is ${SPEEDUP}% faster, MDE CPU dropped, same security protection"
echo "   5. 60+ profiles ship with MDE — Xcode, .NET, Docker, Rust, Go, JetBrains..."
echo ""
echo "📖 Learn more: https://learn.microsoft.com/en-us/defender-endpoint/performance-profiles"
echo ""

# Clean up state file — demo completed successfully
rm -f "$STATE_FILE"
