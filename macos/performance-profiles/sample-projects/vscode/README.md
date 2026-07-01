# VSCode Performance Profile Demo

This is a minimal TypeScript/Node.js project demonstrating how the `vscode`, `vscode-tree`, and other performance profiles impact MDE scanning during development.

## Quick Start

```bash
cd sample-projects/vscode
npm install
# Then run the demo task via VSCode tasks: Cmd+Shift+P → "Run Task" → "MDE Demo: Run All Phases"
```

Or run directly:
```bash
./run-demo.sh
```

## What to Observe

- **Build time** for each phase (shown in terminal output)
- **MDE CPU usage** (open Activity Monitor → search `wdavdaemon_unprivileged` to watch CPU %)
- **EICAR detection** (shown at end of each phase):
  - ✅ Detected = Real-time protection is active
  - ❌ NOT Detected = Protection gap (only happens with exclusions)

## The Story

- **Phase 1 (Baseline)**: Full scanning while VSCode watches the project (TypeScript language server, IntelliSense, linters, file watchers all active). MDE CPU is high.
- **Phase 2 (Exclusions)**: Faster build (folders excluded from scanning), but malware in those directories goes undetected.
- **Phase 3 (Profiles)**: VSCode process tree muted (vscode-tree profile), so child processes don't generate scan events. Node build stays fast AND malware is still detected. No protection gap.

## Prerequisites

- macOS with Microsoft Defender for Endpoint installed
- Real-time protection enabled (`mdatp health --field real_time_protection_enabled` returns `true`)
- Node.js 18+, npm
- VSCode (for the native task experience)
- `sudo` access (for mdatp commands)

## Quick Start

**Easiest way — just run this:**
```bash
./open-demo.sh
```

This will:
1. Install dependencies (if needed)
2. Open the project in VSCode with all settings pre-configured
3. Show you next steps in the terminal

Then in VSCode: Command Palette (Cmd+Shift+P) → "Run Task" → "MDE Demo: Run All Phases"

---

## Running from VSCode

**Manual setup:**
1. Double-click `mde-demo.code-workspace` to open the project
2. From Command Palette (Cmd+Shift+P):
   - Type "Run Task"
   - Select "MDE Demo: Run All Phases"
   - Watch the terminal panel for the three-phase demo

Or run individual phases:
- "MDE Demo: Phase 1 - Baseline Build"
- "MDE Demo: Phase 2 - AV Exclusions"
- "MDE Demo: Phase 3 - Performance Profiles"

**Alternative (command line):**
```bash
code mde-demo.code-workspace
```

## Running from Terminal

```bash
./run-demo.sh
```

## Project Details

- **Build command**: `npm run compile` (TypeScript compilation)
- **Watch command**: `npm run watch` (continuous compilation while editing)
- **Build output**: `out/` directory
- **Cache/temp files**: `node_modules/`, `.build/`
- **AV exclusion paths**: `out/`, `node_modules/`, `.build/`
- **Profiles applied**: `node`, `vscode`, `vscode-tree`, `git`

## Notes

- The project compiles ~145 seconds on first build (full npm install + TypeScript compilation)
- Incremental rebuilds are faster (~30-40s)
- This is a realistic developer scenario: Node/TypeScript build with language server active
- Each phase takes ~150 seconds (mostly from initial node_modules install)

## What vscode-tree Does

The `vscode-tree` profile mutes **VSCode and all its child processes** (language servers, file watchers, debuggers, terminals, etc.). This allows VSCode to remain responsive while providing AV profile benefits for the build process.
