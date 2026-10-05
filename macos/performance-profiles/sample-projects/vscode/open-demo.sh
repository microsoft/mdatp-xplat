#!/bin/bash
# open-demo.sh - Open the MDE demo workspace in VSCode with setup

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🔧 Setting up MDE Performance Profile Demo..."
echo ""

# Check if npm is installed
if ! command -v npm &> /dev/null; then
    echo "❌ npm not found. Please install Node.js first."
    exit 1
fi

# Install dependencies if needed
if [ ! -d "$PROJECT_DIR/node_modules" ]; then
    echo "📦 Installing npm dependencies..."
    cd "$PROJECT_DIR"
    npm install
    echo "✓ Dependencies installed"
else
    echo "✓ Dependencies already installed"
fi

echo ""
echo "🚀 Opening VSCode workspace..."
open "$PROJECT_DIR/mde-demo.code-workspace"

echo ""
echo "Demo ready! Once VSCode opens:"
echo "  1. Command Palette: Cmd+Shift+P"
echo "  2. Type: Run Task"
echo "  3. Select: MDE Demo: Run All Phases"
echo ""
