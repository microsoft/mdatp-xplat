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

The demo reports these per-phase metrics automatically (no manual Activity Monitor needed):

- **MDE files scanned during builds** — the *accurate* scan-overhead signal. Delta of
  `Total files scanned` from `mdatp diagnostic real-time-protection-statistics`.
  Baseline scans the most; exclusions and profiles scan far fewer.
- **MDE CPU** — average %CPU consumed by `wdavdaemon_unprivileged` (the AV scanner
  users complain about) and by all Defender daemons combined, over the build window.
  Computed from the delta of cumulative CPU time / wall time.
- **MDE memory** — peak RSS (MB) of `wdavdaemon_unprivileged`, sampled once per second
  during the builds.
- **Wall-clock build time** (median / avg / min / max) — a *secondary*, noisier signal.
  A warm-up build is always discarded first to avoid cold-cache skew.

Also watch:

- **EICAR detection** (shown at end of each phase):
  - ✅ Detected = Real-time protection is active
  - ❌ NOT Detected = Protection gap (only happens with exclusions)
- Optionally, **Activity Monitor** → search `wdavdaemon_unprivileged` to watch CPU % live.

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

> **Important: run the demo from VSCode, not a plain terminal.**
> The `vscode-tree` profile only mutes `node` when the build runs **inside VSCode's
> process tree**. If you launch `run-demo.sh` from Terminal.app, the build's `node` is a
> child of your shell (not VSCode), so `vscode-tree` won't cover it and Phase 3 (profiles)
> will look identical to the baseline. To match a real dev workflow, run the
> **"MDE Demo: Run All Phases"** task from VSCode (Terminal → Run Task) or launch
> `./run-demo.sh` from VSCode's integrated terminal.
>
> The script detects its launch context: it walks the parent-process chain and refuses to
> run outside VSCode. The `diagnostics.txt` in each run records the full process ancestry
> and a "Build process tree under VSCode: yes/no" verdict. To run from a terminal anyway
> (results then reflect terminal builds only), set `MDE_ALLOW_NON_VSCODE=1`.

## Project Details

- **Build command**: `npm run compile` (TypeScript compilation)
- **Watch command**: `npm run watch` (continuous compilation while editing)
- **Compile workload**: `generate-workload.js` creates ~4000 interdependent `.ts`
  modules under `src/generated.noindex/` so each build takes ~20-40s and produces real
  file I/O for MDE to scan. A single source file compiles in <1s, which is too
  small to measure. Adjust size with `MDE_DEMO_MODULES` (e.g. `MDE_DEMO_MODULES=2000`).
- **Build output**: `out.noindex/` directory
- **Cache/temp files**: `node_modules/`, `.build/`
- **AV exclusion paths**: `out.noindex/`, `node_modules/`, `.build/`
- **Profiles applied**: `node`, `vscode`, `vscode-tree`, `git`

## Notes

- **Accurate measurement** relies on `mdatp diagnostic real-time-protection-statistics`
  (per-process `Total files scanned`). The demo enables it automatically
  (`mdatp config real-time-protection-statistics --value enabled`) and reports the
  per-phase delta. Wall-clock time is kept only as a secondary signal.
- **Live hot-event capture:** during each phase's measured build window the demo streams
  `mdatp diagnostic hot-event-sources` concurrently and keeps the final cumulative
  top-sources table (per-phase `*_hot_events.txt`, also embedded in `REPORT.md`). Unlike
  the post-build snapshot — which only samples ~1s of idle activity after the build exits —
  this shows the processes actually driving scan load *while* the build runs, and whether an
  applied profile suppresses them.
- **Tamper Protection** in block mode can make scan statistics return null — use
  troubleshooting mode if scan counts come back as 0. The demo warns when TP is in block mode.
- **Spotlight suppression:** the generated modules and build output live in folders whose
  names end in `.noindex` (`src/generated.noindex/`, `out.noindex/`). Spotlight skips any
  `.noindex` directory, so `mdworker_shared`/`mds_stores` don't index the thousands of
  generated files. Otherwise that indexing dominates MDE scan load and — because it isn't
  muted by developer profiles — masks the Phase 3 profile benefit. (No profile mutes
  Spotlight by design: it would blind protection like an exclusion does. A
  `.metadata_never_index` marker was tried first but is only honored at a volume root, not
  in nested folders — the `.noindex` folder name is the reliable no-sudo equivalent.)
- **Canonical node install (important):** performance profiles match a process by its
  on-disk install location. Homebrew's **version-pinned** formulas (`node@22`, `node@24`)
  install under a differently-named directory than the canonical `node` formula, so a
  profile that targets the canonical node install may not cover a version-pinned one. If
  your `node` on PATH is a version-pinned build, the node profile can end up a silent
  no-op and Phase 3 looks identical to the baseline. The demo detects this and pins the
  build to the canonical node install (`/opt/homebrew/opt/node/bin/node`) when available;
  if none is found it prints how to fix it (`brew install node`).
- With the default workload, each build takes ~20-40s; the first (warm-up) build is discarded.
- This is a realistic developer scenario: Node/TypeScript build with a language server active.

## What vscode-tree Does

The `vscode-tree` profile mutes **VSCode and all its child processes** (language servers, file watchers, debuggers, terminals, etc.). This allows VSCode to remain responsive while providing AV profile benefits for the build process.
