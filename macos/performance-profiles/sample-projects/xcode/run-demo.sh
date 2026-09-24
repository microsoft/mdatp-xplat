#!/bin/bash
# run-demo.sh - Three-phase MDE performance-profile demo for an Xcode / Swift build.
#
# The workload is Microsoft's own open-source Fluent UI for Apple
# (microsoft/fluentui-apple), fetched by setup-project.sh into a gitignored
# workload.noindex/ directory. Each phase runs `swift build` (which drives the
# Xcode toolchain — swift-frontend / clang / ld under Xcode.app) and measures the
# MDE scan load it produces.
#
#   Phase 1 Baseline    - full scanning, full protection.
#   Phase 2 Exclusions  - exclude the build dir (faster, but EICAR goes undetected).
#   Phase 3 Profiles    - apply the `xcode` profile (fast AND EICAR still detected).
#
# The generic measurement engine (measurement, phases, report) lives in
# ../lib/measure.sh. This script only supplies the Xcode-specific config + build.

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$(cd "$PROJECT_DIR/../lib" && pwd)"

# --- Sample configuration ---------------------------------------------------
SAMPLE_TITLE="Xcode / Swift build (Fluent UI for Apple)"
WORKLOAD_DIR="$PROJECT_DIR/workload.noindex"
# SwiftPM product to build. FluentUI includes the macOS sources on a macOS host.
SWIFT_PRODUCT="${MDE_SWIFT_PRODUCT:-FluentUI}"

# Profiles applied in Phase 3. The `xcode` profile matches the toolchain by install
# location and works for a terminal `swift build`. `xcode-ide-tree` is intentionally
# NOT a default — it only mutes builds launched from inside the Xcode IDE process
# tree, so a terminal build would not be covered by it.
DEMO_PROFILES="${DEMO_PROFILES:-xcode git}"
IDE_TREE_PROFILE="xcode-ide-tree"
IDE_PROCESS_MATCH="Xcode.app"

# Folders excluded in Phase 2, and where the EICAR probe is dropped (an excluded dir).
EXCLUDE_PATHS=("$WORKLOAD_DIR/.build" "$WORKLOAD_DIR/DerivedData")
EICAR_TARGET_DIR="$WORKLOAD_DIR/.build"

# Report text.
REPORT_TITLE="MDE Performance Profile Demo — Xcode / Swift"
REPORT_EXCLUDED_NOTE="Exclusions phase excluded folders: \`.build\`, \`DerivedData\`."
REPORT_ENV_INTRO="Machine-specific facts captured at run time (useful when this report was produced on a different machine — e.g. to confirm which Xcode/Swift toolchain ran the build and whether the \`xcode\` performance profile could actually match it):"

# --- Sample hooks -----------------------------------------------------------

# macOS SDK path used for the build.
macos_sdk() { xcrun --sdk macosx --show-sdk-path 2>/dev/null; }

# Remove build artifacts so each build is a full, comparable clean compile. The
# workload has no external SwiftPM dependencies, so removing .build only forces a
# recompile (no network refetch).
cleanup_build() {
    rm -rf "$WORKLOAD_DIR/.build" 2>/dev/null || true
}

# One clean build of the workload. Output/errors discarded; timing done by caller.
build_once() {
    cleanup_build
    ( cd "$WORKLOAD_DIR" && swift build --product "$SWIFT_PRODUCT" \
        -Xswiftc -sdk -Xswiftc "$(macos_sdk)" ) >/dev/null 2>&1
}

# Verify Xcode/Swift toolchain is present and fetch the workload if needed.
check_tools() {
    if ! command -v xcodebuild &> /dev/null || ! command -v swift &> /dev/null; then
        print_error "xcodebuild/swift not found. Install Xcode and run: sudo xcode-select --switch /Applications/Xcode.app"
        exit 1
    fi
    if [ ! -f "$WORKLOAD_DIR/Package.swift" ]; then
        print_info "Build workload not found — running setup-project.sh..."
        "$PROJECT_DIR/setup-project.sh"
    fi
    print_success "Workload present: $WORKLOAD_DIR ($SWIFT_PRODUCT)"
}

# Toolchain-specific diagnostics block appended to diagnostics.txt.
capture_toolchain_diagnostics() {
    local swift_bin toolchain_dir frontend
    swift_bin=$(command -v swift 2>/dev/null)
    toolchain_dir=$(dirname "$(xcrun -f swift-frontend 2>/dev/null)" 2>/dev/null)
    frontend=$(xcrun -f swift-frontend 2>/dev/null)

    echo "Xcode toolchain (this is what runs the build; the 'xcode' profile must cover its install location):"
    echo "  Xcode: $(xcodebuild -version 2>/dev/null | tr '\n' ' ')"
    echo "  Developer dir: $(xcode-select -p 2>/dev/null)"
    echo "  swift on PATH: ${swift_bin:-not found}"
    echo "  swift version: $(swift --version 2>/dev/null | head -1)"
    echo "  Toolchain dir: ${toolchain_dir:-n/a}"
    echo "  macOS SDK: $(macos_sdk)"
    if [ -n "$frontend" ]; then
        echo "  swift-frontend code signature (determines executable-signature match):"
        codesign -dv --verbose=4 "$frontend" 2>&1 \
            | grep -iE '^Identifier=|^TeamIdentifier=|^Authority=' \
            | head -3 | sed 's/^/    /' || echo "    (unable to read signature)"
    fi
    echo ""
    echo "Workload:"
    echo "  Repo: $(git -C "$WORKLOAD_DIR" config --get remote.origin.url 2>/dev/null)"
    echo "  Commit: $(git -C "$WORKLOAD_DIR" rev-parse HEAD 2>/dev/null)"
    echo "  Product built: $SWIFT_PRODUCT"
    echo "  Swift sources: $(find "$WORKLOAD_DIR/Sources" -name '*.swift' 2>/dev/null | wc -l | tr -d ' ')"
}

# --- Run --------------------------------------------------------------------
source "$LIB_DIR/measure.sh"
demo_main
