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

MERGE_POLICY=$(mdatp performance-profiles list-applied 2>/dev/null | grep -i 'Merge policy' | head -1 || echo "")
if echo "$MERGE_POLICY" | grep -qi 'admin'; then
    echo "❌ Performance profiles are in admin-only mode."
    echo "   Your administrator must apply profiles via MDM or mdatp CLI with elevated privileges."
    echo ""
    echo "   Ask your admin to run:"
    for p in $PROFILES; do
        echo "     sudo mdatp performance-profiles apply --name $p"
    done
    echo ""
    echo "   Once the profiles are applied, re-run this script to verify the improvement."
    exit 1
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

# Remove active profiles for clean baseline
for p in $PROFILES; do mdatp performance-profiles remove --name "$p" &>/dev/null || true; done
echo "   🧹 Test profiles removed (clean baseline)"
echo ""

# ══════════════════════════════════════════════════════════════════
#  PHASE 1: Build WITHOUT profiles
# ══════════════════════════════════════════════════════════════════
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

# ══════════════════════════════════════════════════════════════════
#  PHASE 2: Apply profiles and rebuild
# ══════════════════════════════════════════════════════════════════
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ Applying profiles: $PROFILES"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

for p in $PROFILES; do
    if mdatp performance-profiles apply --name "$p" 2>/dev/null; then
        echo "   ✅ $p"
    else
        echo "   ⚠️  $p (not available)"
    fi
done
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
