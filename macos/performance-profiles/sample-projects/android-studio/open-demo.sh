#!/bin/bash
# open-demo.sh - Fetch the build workload and open it in Android Studio.
#
# The terminal demo (./run-demo.sh) exercises the `openjdk-javac` toolchain profile,
# which matches the JDK by install location and therefore applies to a command-line
# `./gradlew` build. The `android-studio-tree` profile is different: it only mutes
# builds launched from *inside* the Android Studio IDE process tree. To exercise that
# profile you have to build from within Android Studio — which is what this script
# sets up for.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKLOAD_DIR="$PROJECT_DIR/workload.noindex"

echo "🔧 Preparing the MDE Android Studio performance-profile demo..."
echo ""

# Fetch + warm the open-source build workload (microsoft/fluentui-android) if needed.
if [ ! -f "$WORKLOAD_DIR/local.properties" ] || [ ! -x "$WORKLOAD_DIR/gradlew" ]; then
    echo "📦 Build workload not ready — running setup-project.sh..."
    "$PROJECT_DIR/setup-project.sh"
else
    echo "✓ Build workload already present: $WORKLOAD_DIR"
fi

echo ""
if [ -d "/Applications/Android Studio.app" ]; then
    echo "🚀 Opening the workload in Android Studio..."
    open -a "Android Studio" "$WORKLOAD_DIR"
else
    echo "⚠ Android Studio.app not found in /Applications."
    echo "  Install it from https://developer.android.com/studio, then open:"
    echo "    $WORKLOAD_DIR"
fi

cat <<'EOF'

Demo ready. Once Android Studio finishes the Gradle sync:

  1. Select the "fluentui_core" module.
  2. Build with Build > Make Module 'fluentui_core' — this runs *inside*
     Android Studio's process tree.
  3. In a terminal, apply the IDE profile so this in-IDE build is muted:

       sudo mdatp performance-profiles apply --name android-studio
       sudo mdatp performance-profiles apply --name android-studio-tree

  4. Watch wdavdaemon_unprivileged CPU in Activity Monitor drop on the next build.
  5. Clean up:

       sudo mdatp performance-profiles remove --name android-studio-tree
       sudo mdatp performance-profiles remove --name android-studio

For the automated, measured three-phase comparison (Baseline / AV Exclusions /
Performance Profiles) with a generated REPORT.md, run the terminal demo instead:

    ./run-demo.sh

EOF
