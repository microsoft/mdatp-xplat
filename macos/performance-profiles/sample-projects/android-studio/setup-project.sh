#!/bin/bash
# setup-project.sh - Prepare the Android / Gradle build workload for the MDE
# performance demo.
#
# The workload is Microsoft's own open-source Fluent UI for Android
# (https://github.com/microsoft/fluentui-android, MIT-licensed, Gradle/Kotlin). It
# is NOT vendored into this repo — we shallow-clone a PINNED commit into a
# gitignored workload directory (mirroring the xcode and vscode samples). The build
# uses `./gradlew`, which drives the JDK toolchain (javac / Kotlin / D8) — exactly
# what the `openjdk-javac` performance profile targets for a terminal build.
#
# Toolchain (all installable without sudo, verified on Apple Silicon):
#   brew install openjdk@17
#   brew install --cask android-commandlinetools
#   sdkmanager "platform-tools" "platforms;android-34" "build-tools;31.0.0"
#   yes | sdkmanager --licenses

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

WORKLOAD_REPO="${MDE_WORKLOAD_REPO:-https://github.com/microsoft/fluentui-android.git}"
# Pin a specific commit so the demo is reproducible and a surprise upstream change
# (or a dead jcenter mirror) can't break a run. Override with MDE_WORKLOAD_REF.
WORKLOAD_REF="${MDE_WORKLOAD_REF:-71be08ca96fd3c1b449920cb8d3e1c268f3dfe35}"
# ".noindex" tells Spotlight not to index the tree, so mdworker/mds_stores don't
# add scan load that developer profiles can't mute.
WORKLOAD_DIR="$PROJECT_DIR/workload.noindex"

# Gradle module built by the demo. fluentui_core is a good size: big enough for MDE
# scan overhead to be measurable, small enough for a ~20s cached rebuild.
GRADLE_TASK="${MDE_GRADLE_TASK:-:fluentui_core:assembleDebug}"

# --- Toolchain locations (keg-only Homebrew installs) -----------------------
export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@17}"
export ANDROID_HOME="${ANDROID_HOME:-/opt/homebrew/share/android-commandlinetools}"
export ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-$ANDROID_HOME}"
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${YELLOW}ℹ $1${NC}"; }
ok()    { echo -e "${GREEN}✓ $1${NC}"; }
err()   { echo -e "${RED}✗ $1${NC}"; }

# --- Prerequisites ----------------------------------------------------------
if ! command -v git >/dev/null 2>&1; then
    err "git not found. Install the Xcode Command Line Tools: xcode-select --install"; exit 1
fi
if [ ! -x "$JAVA_HOME/bin/java" ]; then
    err "JDK 17 not found at JAVA_HOME=$JAVA_HOME"
    err "  Install it: brew install openjdk@17   (or set JAVA_HOME to a JDK 17)"; exit 1
fi
if [ ! -d "$ANDROID_HOME" ]; then
    err "Android SDK not found at ANDROID_HOME=$ANDROID_HOME"
    err "  Install it: brew install --cask android-commandlinetools"
    err "  then: sdkmanager \"platform-tools\" \"platforms;android-34\" \"build-tools;31.0.0\""
    err "  and:  yes | sdkmanager --licenses"; exit 1
fi

info "JDK: $("$JAVA_HOME/bin/java" -version 2>&1 | head -1)"
info "Android SDK: $ANDROID_HOME"

# The workload pins compileSdk 34 + build-tools 31.0.0. If those SDK packages are
# missing, Gradle fails deep in the build with an opaque error — check up front and
# give an actionable message instead.
missing_pkgs=()
[ -d "$ANDROID_HOME/platforms/android-34" ] || missing_pkgs+=("platforms;android-34")
ls "$ANDROID_HOME"/build-tools/31.* >/dev/null 2>&1 || missing_pkgs+=("build-tools;31.0.0")
[ -d "$ANDROID_HOME/platform-tools" ] || missing_pkgs+=("platform-tools")
if [ ${#missing_pkgs[@]} -gt 0 ]; then
    err "Required Android SDK packages are missing: ${missing_pkgs[*]}"
    err "  Install them (no sudo):"
    err "    \"$ANDROID_HOME/bin/sdkmanager\" ${missing_pkgs[*]}"
    err "    yes | \"$ANDROID_HOME/bin/sdkmanager\" --licenses"
    exit 1
fi
# Licenses must be accepted or Gradle's SDK auto-provisioning aborts.
if [ ! -d "$ANDROID_HOME/licenses" ] || [ -z "$(ls -A "$ANDROID_HOME/licenses" 2>/dev/null)" ]; then
    err "Android SDK licenses have not been accepted."
    err "  Run: yes | \"$ANDROID_HOME/bin/sdkmanager\" --licenses"
    exit 1
fi

# --- Fetch the pinned workload ---------------------------------------------
if [ -d "$WORKLOAD_DIR/.git" ] && git -C "$WORKLOAD_DIR" rev-parse --verify --quiet "$WORKLOAD_REF^{commit}" >/dev/null 2>&1; then
    ok "Workload already present at pinned commit ($WORKLOAD_DIR)"
else
    info "Cloning workload: $WORKLOAD_REPO @ ${WORKLOAD_REF:0:12}"
    rm -rf "$WORKLOAD_DIR"
    git init -q "$WORKLOAD_DIR"
    git -C "$WORKLOAD_DIR" remote add origin "$WORKLOAD_REPO"
    if git -C "$WORKLOAD_DIR" fetch -q --depth 1 origin "$WORKLOAD_REF" 2>/dev/null; then
        git -C "$WORKLOAD_DIR" checkout -q FETCH_HEAD
    else
        info "Direct SHA fetch unsupported; fetching default branch and checking out the pin..."
        git -C "$WORKLOAD_DIR" fetch -q --depth 200 origin
        git -C "$WORKLOAD_DIR" checkout -q "$WORKLOAD_REF"
    fi
    ok "Workload checked out at ${WORKLOAD_REF:0:12}"
fi

if [ ! -f "$WORKLOAD_DIR/settings.gradle" ] && [ ! -f "$WORKLOAD_DIR/settings.gradle.kts" ]; then
    err "settings.gradle not found in workload — the upstream layout may have changed."; exit 1
fi

# --- Point Gradle at the local SDK ------------------------------------------
# local.properties is git-ignored by the workload and machine-specific; write it so
# Gradle can find the Android SDK without an ANDROID_HOME lookup at build time.
echo "sdk.dir=$ANDROID_HOME" > "$WORKLOAD_DIR/local.properties"
ok "Wrote local.properties (sdk.dir=$ANDROID_HOME)"

# --- Warm the Gradle caches with one full (online) build --------------------
# The demo's timed builds run with --offline for reproducibility, so we must
# download every dependency ONCE here. This also verifies the workload builds on
# this machine before the measured run.
info "Warming Gradle caches with an initial build ($GRADLE_TASK) — first run downloads dependencies, may take a few minutes..."
BUILD_LOG="$PROJECT_DIR/setup-build.log"
if ( cd "$WORKLOAD_DIR" && ./gradlew "$GRADLE_TASK" --no-daemon --stacktrace ) >"$BUILD_LOG" 2>&1; then
    ok "Initial build succeeded — caches warm, workload verified buildable"
    rm -f "$BUILD_LOG"
else
    err "Initial Gradle build failed. Last 40 lines of the build log:"
    echo "----------------------------------------------------------------------"
    tail -40 "$BUILD_LOG"
    echo "----------------------------------------------------------------------"
    err "Full log saved to: $BUILD_LOG"
    err "Reproduce manually with:"
    err "  ( cd $WORKLOAD_DIR && JAVA_HOME=$JAVA_HOME ANDROID_HOME=$ANDROID_HOME ./gradlew $GRADLE_TASK --no-daemon --stacktrace )"
    err "Common causes on a fresh/lab machine:"
    err "  • Network/proxy blocks dependency download — set HTTP(S)_PROXY or use a machine with access."
    err "  • Missing SDK packages or unaccepted licenses (see checks above)."
    exit 1
fi

ok "Setup complete. Run: ./run-demo.sh"
