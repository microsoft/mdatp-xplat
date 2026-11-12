#!/bin/bash
# run-demo.sh - Three-phase MDE performance-profile demo for an Android / Gradle build.
#
# The workload is Microsoft's own open-source Fluent UI for Android
# (microsoft/fluentui-android, MIT-licensed), fetched by setup-project.sh into a
# gitignored workload.noindex/ directory. Each phase runs `./gradlew` (which drives
# the JDK toolchain — javac / Kotlin / D8) and measures the MDE scan load it produces.
#
#   Phase 1 Baseline    - full scanning, full protection.
#   Phase 2 Exclusions  - exclude the build dirs (faster, but EICAR goes undetected).
#   Phase 3 Profiles    - apply `openjdk-javac` (fast AND EICAR still detected).
#
# The generic measurement engine (measurement, phases, report) lives in
# ../lib/measure.sh. This script only supplies the Android-specific config + build.

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$(cd "$PROJECT_DIR/../lib" && pwd)"

# --- Toolchain locations (keg-only Homebrew installs; overridable) ----------
export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@17}"
export ANDROID_HOME="${ANDROID_HOME:-/opt/homebrew/share/android-commandlinetools}"
export ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-$ANDROID_HOME}"
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH"

# --- Sample configuration ---------------------------------------------------
SAMPLE_TITLE="Android Studio / Gradle build (Fluent UI for Android)"
WORKLOAD_DIR="$PROJECT_DIR/workload.noindex"
GRADLE_TASK="${MDE_GRADLE_TASK:-:fluentui_core:assembleDebug}"
# The project build dir produced by GRADLE_TASK (module 'fluentui_core').
MODULE_BUILD_DIR="$WORKLOAD_DIR/fluentui_core/build"

# Profiles applied in Phase 3. For a terminal `./gradlew` build the toolchain-by-
# location profile is `openjdk-javac` (it matches the JDK that runs javac/kotlinc).
# `android-studio-tree` is intentionally NOT a default — like xcode-ide-tree it only
# mutes builds launched from INSIDE Android Studio's process tree, so it would not
# cover this terminal build.
DEMO_PROFILES="${DEMO_PROFILES:-openjdk-javac git}"
IDE_TREE_PROFILE="android-studio-tree"
IDE_PROCESS_MATCH="Android Studio"

# Folders excluded in Phase 2, and where the EICAR probe is dropped (an excluded dir).
# The module build dir is the demo's own output; ~/.gradle/caches and ~/.android are
# the shared Gradle/Android caches a developer would typically be tempted to exclude.
EXCLUDE_PATHS=("$MODULE_BUILD_DIR" "$HOME/.gradle/caches" "$HOME/.android")
EICAR_TARGET_DIR="$MODULE_BUILD_DIR"

# Report text.
REPORT_TITLE="MDE Performance Profile Demo — Android Studio / Gradle"
REPORT_EXCLUDED_NOTE="Exclusions phase excluded folders: \`fluentui_core/build\`, \`~/.gradle/caches\`, \`~/.android\`."
REPORT_ENV_INTRO="Machine-specific facts captured at run time (useful when this report was produced on a different machine — e.g. to confirm which JDK/Android SDK ran the build and whether the \`openjdk-javac\` performance profile could actually match it):"

# --- Sample hooks -----------------------------------------------------------

# Remove the module build output so each build is a full, comparable recompile.
# Only the project build dir is removed — the ~/.gradle dependency cache is kept, so
# --offline builds still resolve (no network refetch between builds).
cleanup_build() {
    rm -rf "$MODULE_BUILD_DIR" 2>/dev/null || true
}

# One clean build of the workload. --offline keeps timing reproducible (no network
# variance); setup-project.sh warmed the caches with a full online build first.
# Output/errors discarded; timing done by caller.
build_once() {
    cleanup_build
    ( cd "$WORKLOAD_DIR" && ./gradlew "$GRADLE_TASK" --no-daemon --offline -q ) >/dev/null 2>&1
}

# Verify the JDK + Android SDK are present and fetch/warm the workload if needed.
check_tools() {
    if [ ! -x "$JAVA_HOME/bin/java" ]; then
        print_error "JDK 17 not found at JAVA_HOME=$JAVA_HOME. Install: brew install openjdk@17"
        exit 1
    fi
    if [ ! -d "$ANDROID_HOME" ]; then
        print_error "Android SDK not found at ANDROID_HOME=$ANDROID_HOME. Install: brew install --cask android-commandlinetools"
        exit 1
    fi
    # Missing workload OR cold caches (no local.properties / never built) → run setup,
    # which clones the pinned commit and does a full online cache-warming build. This
    # is required because build_once uses --offline.
    if [ ! -f "$WORKLOAD_DIR/local.properties" ] || [ ! -x "$WORKLOAD_DIR/gradlew" ]; then
        print_info "Build workload not ready — running setup-project.sh..."
        "$PROJECT_DIR/setup-project.sh"
    fi
    print_success "Workload present: $WORKLOAD_DIR ($GRADLE_TASK)"
}

# Toolchain-specific diagnostics block appended to diagnostics.txt.
capture_toolchain_diagnostics() {
    echo "JDK / Android toolchain (this is what runs the build; the 'openjdk-javac' profile must cover the JDK install location):"
    echo "  JAVA_HOME: $JAVA_HOME"
    echo "  java: $("$JAVA_HOME/bin/java" -version 2>&1 | head -1)"
    echo "  javac: $("$JAVA_HOME/bin/javac" -version 2>&1 | head -1)"
    echo "  ANDROID_HOME: $ANDROID_HOME"
    echo "  Gradle wrapper: $(cd "$WORKLOAD_DIR" 2>/dev/null && ./gradlew --version --offline 2>/dev/null | awk '/^Gradle/{print $2; exit}')"
    echo "  Build tools: $(ls "$ANDROID_HOME/build-tools" 2>/dev/null | tr '\n' ' ')"
    echo "  Platforms: $(ls "$ANDROID_HOME/platforms" 2>/dev/null | tr '\n' ' ')"
    echo ""
    echo "Workload:"
    echo "  Repo: $(git -C "$WORKLOAD_DIR" config --get remote.origin.url 2>/dev/null)"
    echo "  Commit: $(git -C "$WORKLOAD_DIR" rev-parse HEAD 2>/dev/null)"
    echo "  Gradle task: $GRADLE_TASK"
    echo "  Kotlin sources: $(find "$WORKLOAD_DIR/fluentui_core/src" -name '*.kt' 2>/dev/null | wc -l | tr -d ' ')"
}

# --- Run --------------------------------------------------------------------
source "$LIB_DIR/measure.sh"
demo_main
