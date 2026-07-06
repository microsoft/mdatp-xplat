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

# Default to opening the Swift package because it avoids iOS demo signing/SDK
# pitfalls and is sufficient for the IDE-tree profile demonstration.
OPEN_MODE="package"
if [[ "${1:-}" == "--ios-demo" ]]; then
    OPEN_MODE="ios-demo"
fi

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
if [[ "$OPEN_MODE" == "ios-demo" ]]; then
    if [ -d "$XCODEPROJ" ]; then
        open "$XCODEPROJ"
    else
        echo "⚠ FluentUI.Demo.xcodeproj not found — opening the Swift package instead."
        open "$WORKLOAD_DIR/Package.swift"
    fi
else
    open "$WORKLOAD_DIR/Package.swift"
fi

cat <<'EOF'

Demo ready. Once Xcode finishes resolving packages:

    1. Select the "FluentUI" scheme (top toolbar) and destination "My Mac".
    2. Build with Cmd+B — this build runs *inside* Xcode's process tree.
    3. Optional: if you explicitly want the iOS demo project, run:

             ./open-demo.sh --ios-demo

         Then choose "Demo.Development" + an iOS simulator destination.
         ("Demo.Dogfood" requires extra AppCenter/provisioning setup.)
    4. In a terminal, apply the IDE profile so this in-IDE build is muted:

       sudo mdatp performance-profiles apply --name xcode-ide-tree

    5. Watch wdavdaemon_unprivileged CPU in Activity Monitor drop on the next build.
    6. Clean up:

       sudo mdatp performance-profiles remove --name xcode-ide-tree

Want an MDE "report card" after an IDE build?

    - The automatic hook (`./xcode-report.sh on`) is attached to the iOS demo
        scheme file (`Demo.Dogfood.xcscheme`). It does not fire when building the
        package-only `FluentUI` scheme.

    - For the package/My Mac path, run this manual bracket around your IDE build:

            ./mde-profile-report.sh before
            # build once in Xcode (Cmd+B)
            ./mde-profile-report.sh after

        The report is also written to: "$TMPDIR/mde-xcode-report.txt"

    - If you want fully automatic pre/post reporting inside Xcode, open the iOS
        project path (`./open-demo.sh --ios-demo`), build the `Demo.Development`
        scheme, and then run:

            ./xcode-report.sh on      # later: ./xcode-report.sh off

For the automated, measured three-phase comparison (Baseline / AV Exclusions /
Performance Profiles) with a generated REPORT.md, run the terminal demo instead:

    ./run-demo.sh

EOF
