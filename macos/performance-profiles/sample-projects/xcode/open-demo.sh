#!/bin/bash
# open-demo.sh - Fetch the build workload and open it in Xcode.
#
# The terminal demo (./run-demo.sh) exercises the `xcode` toolchain profile, which
# matches the Swift/Clang toolchain by install location and therefore applies to a
# command-line `swift build`. The `xcode-ide-tree` profile is different: it only
# mutes builds launched from *inside* the Xcode IDE process tree. To exercise that
# profile you have to build from within Xcode.app — which is what this script sets
# up for.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKLOAD_DIR="$PROJECT_DIR/workload.noindex"

echo "🔧 Preparing the MDE Xcode performance-profile demo..."
echo ""

if ! command -v xcodebuild &> /dev/null; then
    echo "❌ Xcode command-line tools not found. Install Xcode first."
    exit 1
fi

# Fetch the open-source build workload (microsoft/fluentui-apple) if needed.
if [ ! -f "$WORKLOAD_DIR/Package.swift" ]; then
    echo "📦 Build workload not found — running setup-project.sh..."
    "$PROJECT_DIR/setup-project.sh"
else
    echo "✓ Build workload already present: $WORKLOAD_DIR"
fi

echo ""
echo "🚀 Opening the workload in Xcode..."
XCODEPROJ="$WORKLOAD_DIR/Demos/FluentUIDemo_iOS/FluentUI.Demo.xcodeproj"
if [ -d "$XCODEPROJ" ]; then
    open "$XCODEPROJ"
else
    echo "⚠ FluentUI.Demo.xcodeproj not found — opening the Swift package instead."
    open "$WORKLOAD_DIR/Package.swift"
fi

cat <<'EOF'

Demo ready. Once Xcode finishes resolving packages:

  1. Select the "Demo.Dogfood" scheme (top toolbar) and an iOS Simulator destination.
  2. Build with Cmd+B — this build runs *inside* Xcode's process tree.
  3. In a terminal, apply the IDE profile so this in-IDE build is muted:

       sudo mdatp performance-profiles apply --name xcode-ide-tree

  4. Watch wdavdaemon_unprivileged CPU in Activity Monitor drop on the next build.
  5. Clean up:

       sudo mdatp performance-profiles remove --name xcode-ide-tree

Want an MDE "report card" printed in Xcode's build log after each build (applied
profiles + files scanned during the build)? Enable the scheme pre/post-actions:

    ./xcode-report.sh on      # then build in Xcode; ./xcode-report.sh off when done

For the automated, measured three-phase comparison (Baseline / AV Exclusions /
Performance Profiles) with a generated REPORT.md, run the terminal demo instead:

    ./run-demo.sh

EOF
