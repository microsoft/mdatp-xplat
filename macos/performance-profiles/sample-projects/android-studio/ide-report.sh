#!/bin/bash
# ide-report.sh - Enable/disable the MDE performance-profile report card for
# Android Studio builds.
#
# The terminal demo (run-demo.sh) can pass mde-profile-report.gradle with
# `--init-script` directly. Android Studio has no per-build init-script flag, so to make
# the report appear in its Build console we install the script into the Gradle user
# init directory ($GRADLE_USER_HOME/init.d/), which Gradle auto-applies to EVERY build —
# including the ones Android Studio launches.
#
# The report only READS mdatp state (list-applied + real-time-protection-statistics) and
# prints a summary; it never applies/removes profiles or changes protection. Even so, it
# applies to all Gradle builds on this machine while enabled, so disable it when done.
#
# Usage:
#   ./ide-report.sh on       # install into ~/.gradle/init.d/
#   ./ide-report.sh off      # remove it
#   ./ide-report.sh status   # show whether it is installed

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$PROJECT_DIR/mde-profile-report.gradle"
INIT_DIR="${GRADLE_USER_HOME:-$HOME/.gradle}/init.d"
DEST="$INIT_DIR/mde-profile-report.gradle"

case "${1:-status}" in
    on|enable|install)
        [ -f "$SRC" ] || { echo "✗ Missing $SRC"; exit 1; }
        mkdir -p "$INIT_DIR"
        cp "$SRC" "$DEST"
        echo "✓ MDE report enabled for all Gradle builds: $DEST"
        echo "  Now build in Android Studio (Build > Make Module 'fluentui_core')."
        echo "  The report card prints in the Build tool window when the build finishes."
        echo "  Run './ide-report.sh off' when you're done demoing."
        ;;
    off|disable|remove|uninstall)
        if [ -f "$DEST" ]; then
            rm -f "$DEST"
            echo "✓ MDE report disabled (removed $DEST)"
        else
            echo "• Not installed (nothing to remove): $DEST"
        fi
        ;;
    status)
        if [ -f "$DEST" ]; then
            echo "● ENABLED: $DEST"
        else
            echo "○ disabled (not installed at $DEST)"
        fi
        ;;
    *)
        echo "Usage: $0 {on|off|status}"; exit 2
        ;;
esac
