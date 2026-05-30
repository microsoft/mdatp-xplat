#!/bin/bash
set -euo pipefail

#=============================================================================
# MDE Performance Profiles — Quick Xcode Demo
#
# A shorter demo using microsoft/fluentui-apple (Swift/Xcode build).
# Good for iOS/macOS developer audiences or when time is limited (~10 min).
#
# Repo:     microsoft/fluentui-apple
# Profiles: xcode, xcode-ide-tree, git
#
# Usage:    ./perf-profile-demo-xcode.sh [path-to-fluentui-apple-repo]
#           Default repo path: ~/demo/fluentui-apple
#
# Prerequisites:
#   - macOS with MDE installed (real-time protection enabled)
#   - Xcode (with command line tools), git, jq
#   - sudo access (for hot-event-sources collection)
#
# Note: The fluentui-apple repo will be cloned automatically if not present.
#
# Learn more: https://learn.microsoft.com/en-us/defender-endpoint/performance-profiles
#=============================================================================

REPO_DIR="${1:-$HOME/demo/fluentui-apple}"
RESULTS_DIR="$HOME/demo/results"
PROFILES="xcode xcode-ide-tree git"

mkdir -p "$RESULTS_DIR"
STATE_FILE="$RESULTS_DIR/.xcode-demo-state"

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║   MDE Performance Profiles — Quick Xcode Demo               ║"
echo "║   Repo: microsoft/fluentui-apple                            ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# ── Preflight ──
echo "🔍 Preflight checks..."

if ! command -v mdatp &>/dev/null; then
    echo "❌ mdatp not found. Install MDE first."
    exit 1
fi

RTP=$(mdatp health --field real_time_protection_enabled 2>/dev/null || echo "unknown")
if [ "$RTP" != "true" ]; then
    echo "❌ Real-time protection not enabled."
    exit 1
fi
echo "   ✅ Real-time protection: ON"
echo "   ✅ MDE version: $(mdatp health --field app_version 2>/dev/null || echo '?')"

# ── Resume detection ──────────────────────────────────────────────
RESUME=false
if [ -f "$STATE_FILE" ]; then
    source "$STATE_FILE"
    if [ "${BASELINE_COMPLETE:-}" = "true" ]; then
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "  📋 Previous run detected — baseline already complete."
        printf "     Baseline build time: %d seconds\n" "${SAVED_PHASE1_TIME:-0}"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        read -rp "  Continue to comparison build, or restart from scratch? [C/r] " resume_answer
        if [[ "$resume_answer" =~ ^[Rr] ]]; then
            echo "  🔄 Restarting from scratch..."
            rm -f "$STATE_FILE"
        else
            RESUME=true
            PHASE1_TIME="${SAVED_PHASE1_TIME:-0}"
            echo "  ▶️  Resuming — skipping to comparison build..."
        fi
        echo ""
    fi
fi

MERGE_POLICY=$(mdatp performance-profiles list-applied 2>/dev/null | grep -i 'Merge policy' | head -1 || echo "")
ADMIN_ONLY=false
if echo "$MERGE_POLICY" | grep -qi 'admin'; then
    ADMIN_ONLY=true
    APPLIED_OUTPUT=$(mdatp performance-profiles list-applied 2>/dev/null)

    if [ "$RESUME" = true ]; then
        # Resuming — all profiles should now be deployed by the admin
        MISSING_PROFILES=()
        for p in $PROFILES; do
            if ! echo "$APPLIED_OUTPUT" | grep -q "^${p} "; then
                MISSING_PROFILES+=("$p")
            fi
        done
        if [ ${#MISSING_PROFILES[@]} -gt 0 ]; then
            echo "⚠️  Admin-only mode — some profiles are still not deployed:"
            for p in "${MISSING_PROFILES[@]}"; do
                echo "     - $p"
            done
            echo ""
            echo "   Ask your IT admin to deploy these via MDM, then re-run."
            exit 1
        fi
        echo "   ✅ Profile mode: admin-only (all profiles deployed — ready for comparison)"
    else
        # First run — check that NO profiles are applied (clean baseline)
        APPLIED_PROFILES=()
        for p in $PROFILES; do
            if echo "$APPLIED_OUTPUT" | grep -q "^${p} "; then
                APPLIED_PROFILES+=("$p")
            fi
        done
        if [ ${#APPLIED_PROFILES[@]} -gt 0 ]; then
            echo "⚠️  Performance profiles are in admin-only mode."
            echo "   The following profiles are currently applied: ${APPLIED_PROFILES[*]}"
            echo ""
            echo "   This demo needs a clean baseline (no profiles) for the first build."
            echo "   Ask your IT admin to remove these profiles via MDM (Intune, JAMF, etc.):"
            for p in "${APPLIED_PROFILES[@]}"; do
                echo "     - $p"
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

if [ ! -d "$REPO_DIR" ]; then
    echo "   ⬇️  Repo not found — cloning now..."
    mkdir -p "$(dirname "$REPO_DIR")"
    git clone --depth 1 https://github.com/microsoft/fluentui-apple.git "$REPO_DIR"
fi
echo "   ✅ Repo: $REPO_DIR"

if ! command -v xcodebuild &>/dev/null; then
    echo "❌ xcodebuild not found. Install Xcode and command line tools."
    exit 1
fi
echo "   ✅ Xcode: $(xcodebuild -version 2>/dev/null | head -1 || echo '?')"
echo ""
if [ "$RESUME" = false ]; then
    if [ "$ADMIN_ONLY" = false ]; then
        for p in $PROFILES; do mdatp performance-profiles remove --name "$p" &>/dev/null || true; done
        echo "   🧹 Test profiles removed (clean baseline)"
    else
        echo "   ℹ️  Admin-only mode — skipping profile removal (managed via MDM)"
    fi
fi
echo ""

# ══════════════════════════════════════════════════════════════════
#  PHASE 1: Build WITHOUT profiles (skipped on resume)
# ══════════════════════════════════════════════════════════════════
if [ "$RESUME" = false ]; then

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🔴 Building WITHOUT performance profiles..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

mdatp config real-time-protection-statistics --value enabled 2>/dev/null || true
cd "$REPO_DIR"

BUILD_START=$(date +%s)
xcodebuild -workspace FluentUI.xcworkspace \
    -scheme FluentUI-macOS -destination 'platform=macOS' \
    clean build 2>&1 | tail -5
BUILD_END=$(date +%s)
PHASE1_TIME=$((BUILD_END - BUILD_START))

mdatp diagnostic real-time-protection-statistics --output json \
    > "$RESULTS_DIR/xcode_before_rtp.json" 2>/dev/null || true

echo ""
printf "   ⏱️  Build time (no profiles): %d seconds\n" "$PHASE1_TIME"
echo ""

# ── Hot event sources ──
echo "   📊 Collecting hot event sources (30s)..."
sudo mdatp diagnostic hot-event-sources --time=30 > /dev/null 2>&1 || true

HES_FILE=$(ls -t hot_event_source_*.json 2>/dev/null | head -1)
if [ -n "${HES_FILE:-}" ]; then
    cp "$HES_FILE" "$RESULTS_DIR/xcode_before_hot_events.json"
    echo ""
    echo "   🔥 Hot event sources (BEFORE profiles):"
    echo "   ──────────────────────────────────────────"
    jq -r '.eventSource[0:5] | .[] | "   \(.path) — auth:\(.authCount) notify:\(.notifyCount)"' \
        "$RESULTS_DIR/xcode_before_hot_events.json" 2>/dev/null || echo "   (could not parse)"
fi
echo ""

# ── Save checkpoint for resume ────────────────────────────────────
cat > "$STATE_FILE" <<CHECKPOINT
BASELINE_COMPLETE=true
SAVED_PHASE1_TIME=$PHASE1_TIME
SAVED_ADMIN_ONLY=$ADMIN_ONLY
CHECKPOINT

fi  # end RESUME=false (phase 1)

# ══════════════════════════════════════════════════════════════════
#  PHASE 2: Apply profiles and rebuild
# ══════════════════════════════════════════════════════════════════
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ Applying profiles: $PROFILES"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ "$ADMIN_ONLY" = true ]; then
    if [ "$RESUME" = true ]; then
        echo "      ℹ️  Admin-only mode — profiles deployed via MDM:"
        for p in $PROFILES; do
            echo "      ✅ $p [managed]"
        done
    else
        echo ""
        echo "   ⚠️  Admin-only mode — profiles cannot be applied locally."
        echo "   Ask your IT admin to deploy these profiles via MDM (Intune, JAMF, etc.):"
        for p in $PROFILES; do
            echo "     - $p"
        done
        echo ""
        echo "   Once deployed, re-run this script to see the comparison."
        echo "   (Your baseline results have been saved — you'll be prompted to continue.)"
        echo ""
        echo "   Baseline results saved to: $RESULTS_DIR/"
        exit 0
    fi
else
    for p in $PROFILES; do
        if mdatp performance-profiles apply --name "$p" 2>/dev/null; then
            echo "   ✅ $p"
        else
            echo "   ⚠️  $p (not available)"
        fi
    done
fi
echo ""

mdatp config real-time-protection-statistics --value enabled 2>/dev/null || true

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🟢 Building WITH performance profiles..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd "$REPO_DIR"
BUILD_START=$(date +%s)
xcodebuild -workspace FluentUI.xcworkspace \
    -scheme FluentUI-macOS -destination 'platform=macOS' \
    clean build 2>&1 | tail -5
BUILD_END=$(date +%s)
PHASE2_TIME=$((BUILD_END - BUILD_START))

mdatp diagnostic real-time-protection-statistics --output json \
    > "$RESULTS_DIR/xcode_after_rtp.json" 2>/dev/null || true

echo ""
printf "   ⏱️  Build time (with profiles): %d seconds\n" "$PHASE2_TIME"
echo ""

# ══════════════════════════════════════════════════════════════════
#  RESULTS
# ══════════════════════════════════════════════════════════════════

SPEEDUP="?"
SAVED=0
if [ "$PHASE1_TIME" -gt 0 ] 2>/dev/null && [ "$PHASE2_TIME" -gt 0 ] 2>/dev/null; then
    SPEEDUP=$(python3 -c "print(f'{(($PHASE1_TIME-$PHASE2_TIME)/$PHASE1_TIME)*100:.0f}')" 2>/dev/null || echo "?")
    SAVED=$(($PHASE1_TIME - $PHASE2_TIME))
fi

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║            🏁  XCODE DEMO — RESULTS                          ║"
echo "╠════════════════════════════════════════════════════════════════╣"
echo "║                                                              ║"
printf "║  ⏱️  Build WITHOUT profiles:  %4d seconds                   ║\n" "$PHASE1_TIME"
printf "║  ⏱️  Build WITH profiles:     %4d seconds                   ║\n" "$PHASE2_TIME"
printf "║  ⚡ Improvement:             %s%% faster (%ds saved)         ║\n" "$SPEEDUP" "$SAVED"
echo "║                                                              ║"
echo "║  Profiles: $PROFILES"
echo "║  Diagnostics: $RESULTS_DIR/xcode_*.json"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "📖 Learn more: https://learn.microsoft.com/en-us/defender-endpoint/performance-profiles"
echo ""

# Clean up state file — demo completed successfully
rm -f "$STATE_FILE"
