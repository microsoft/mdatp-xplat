#!/bin/bash
set -euo pipefail

#=============================================================================
# MDE Performance Profiles — Bootstrap Launcher
#
# Purpose:
#   Keep one shell entrypoint that sets up Python environment, then runs
#   the Python demo framework with the selected scenario.
#
# Usage:
#   ./perf-profile-demo.sh                   # prompt for scenario
#   ./perf-profile-demo.sh vscode            # run VS Code scenario
#   ./perf-profile-demo.sh xcode             # run Xcode scenario
#   ./perf-profile-demo.sh vscode --repo ~/demo/vscode
#=============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
REQ_FILE="$SCRIPT_DIR/requirements.txt"
PY_ENTRY="$SCRIPT_DIR/demo.py"
BOOTSTRAP_STAMP="$VENV_DIR/.bootstrap-stamp"

if ! command -v python3 >/dev/null 2>&1; then
    echo "❌ python3 not found in PATH."
    echo "   Install Python 3 and re-run this script."
    echo "   macOS option: brew install python"
    exit 1
fi

if [ ! -f "$PY_ENTRY" ]; then
    echo "❌ Missing Python entrypoint: $PY_ENTRY"
    exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "🐍 Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# Install or refresh dependencies when requirements changed.
if [ ! -f "$BOOTSTRAP_STAMP" ] || [ "$REQ_FILE" -nt "$BOOTSTRAP_STAMP" ]; then
    echo "📦 Installing Python dependencies..."
    python3 -m pip install --upgrade pip >/dev/null
    python3 -m pip install -r "$REQ_FILE"
    date +%s > "$BOOTSTRAP_STAMP"
fi

if [ $# -eq 0 ]; then
    echo ""
    echo "Select a demo scenario:"
    echo "  1) vscode  - Microsoft VS Code build demo"
    echo "  2) xcode   - FluentUI Apple Xcode build demo"
    read -r -p "Enter choice [1/2] (default: 1): " choice
    case "${choice:-1}" in
        2)
            set -- xcode
            ;;
        *)
            set -- vscode
            ;;
    esac
fi

exec python3 "$PY_ENTRY" "$@"
