#!/bin/bash
# setup-project.sh - Prepare the Xcode build workload for the MDE performance demo.
#
# Unlike a hand-written toy CLI tool (which compiles in <1s and is far too small
# for MDE scan overhead to be measurable), this demo builds a real, sizable native
# codebase: Microsoft's own open-source Fluent UI for Apple
# (https://github.com/microsoft/fluentui-apple, MIT-licensed, SwiftPM-native).
#
# We do NOT vendor that project into this repo. Instead we shallow-clone a PINNED
# commit into a gitignored workload directory at setup time (mirroring how the
# vscode sample generates its gitignored workload). The build uses `swift build`,
# which drives the Xcode toolchain (swift-frontend / clang / ld under Xcode.app) —
# exactly what the `xcode` performance profile targets — with no code-signing setup.

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The upstream workload. Pin a specific commit so the demo is reproducible and a
# surprise upstream change can't break a run. Override with MDE_WORKLOAD_REF.
WORKLOAD_REPO="${MDE_WORKLOAD_REPO:-https://github.com/microsoft/fluentui-apple.git}"
WORKLOAD_REF="${MDE_WORKLOAD_REF:-c591a08e27335099e9bc919ab9eb29a88e80fe02}"
# ".noindex" suffix tells Spotlight not to index the tree, so mdworker/mds_stores
# don't add scan load that developer profiles can't mute.
WORKLOAD_DIR="$PROJECT_DIR/workload.noindex"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${YELLOW}ℹ $1${NC}"; }
ok()    { echo -e "${GREEN}✓ $1${NC}"; }
err()   { echo -e "${RED}✗ $1${NC}"; }

# --- Prerequisites ----------------------------------------------------------
if ! command -v git >/dev/null 2>&1; then
    err "git not found. Install the Xcode Command Line Tools: xcode-select --install"; exit 1
fi
if ! command -v xcodebuild >/dev/null 2>&1 || ! command -v swift >/dev/null 2>&1; then
    err "xcodebuild/swift not found. Install Xcode and run: sudo xcode-select --switch /Applications/Xcode.app"; exit 1
fi

info "Xcode: $(xcodebuild -version 2>/dev/null | tr '\n' ' ')"
info "Toolchain: $(dirname "$(xcrun -f swift-frontend 2>/dev/null)")"

# --- Fetch the pinned workload ---------------------------------------------
if [ -d "$WORKLOAD_DIR/.git" ] && git -C "$WORKLOAD_DIR" rev-parse --verify --quiet "$WORKLOAD_REF^{commit}" >/dev/null 2>&1; then
    ok "Workload already present at pinned commit ($WORKLOAD_DIR)"
else
    info "Cloning workload: $WORKLOAD_REPO @ ${WORKLOAD_REF:0:12}"
    rm -rf "$WORKLOAD_DIR"
    # Fetch just the pinned commit shallowly to keep the download small.
    git init -q "$WORKLOAD_DIR"
    git -C "$WORKLOAD_DIR" remote add origin "$WORKLOAD_REPO"
    if git -C "$WORKLOAD_DIR" fetch -q --depth 1 origin "$WORKLOAD_REF" 2>/dev/null; then
        git -C "$WORKLOAD_DIR" checkout -q FETCH_HEAD
    else
        # Some servers disallow fetching a raw SHA; fall back to a full-ish fetch.
        info "Direct SHA fetch unsupported; fetching default branch and checking out the pin..."
        git -C "$WORKLOAD_DIR" fetch -q --depth 50 origin
        git -C "$WORKLOAD_DIR" checkout -q "$WORKLOAD_REF"
    fi
    ok "Workload checked out at ${WORKLOAD_REF:0:12}"
fi

# --- Sanity-check the workload is buildable ---------------------------------
if [ ! -f "$WORKLOAD_DIR/Package.swift" ]; then
    err "Package.swift not found in workload — the upstream layout may have changed."; exit 1
fi
info "Workload products: $(cd "$WORKLOAD_DIR" && swift package dump-package 2>/dev/null | python3 -c 'import json,sys;print(", ".join(p["name"] for p in json.load(sys.stdin).get("products",[])))' 2>/dev/null || echo "(unable to enumerate)")"

ok "Setup complete. Run: ./run-demo.sh"
