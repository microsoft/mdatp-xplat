# MDE Performance Profiles Demo

This directory contains simplified, hands-on demonstrations of Microsoft Defender for Endpoint (MDE) performance profiles on macOS.

## Quick Start

Two sample projects, designed to run natively in their IDEs:

### 1. Xcode Demo (C/Objective-C)
```bash
cd sample-projects/xcode
./setup-project.sh    # Generate the Xcode project
./run-demo.sh         # Run the three-phase demo
```

**What it shows:**
- Baseline Xcode build (no profiles/exclusions)
- Build with folder exclusions (faster, but protection gap)
- Build with `xcode` and `xcode-tree` profiles (fast AND protected)

Each phase takes ~20-30 seconds, making the MDE CPU impact visible in Activity Monitor.

---

### 2. VSCode Demo (TypeScript/Node.js)

**Easiest way:**
```bash
cd sample-projects/vscode
./open-demo.sh
```

This opens VSCode with everything pre-configured. Then: Command Palette (Cmd+Shift+P) → "Run Task" → "MDE Demo: Run All Phases"

**Or manually:**
```bash
cd sample-projects/vscode
npm install           # Install dependencies
./run-demo.sh         # Run from terminal
```

Or double-click `mde-demo.code-workspace` to open in VSCode directly.

**What it shows:**
- Baseline TypeScript compilation with VSCode language server active
- Compilation with folder exclusions (faster, but protection gap)
- Compilation with `vscode`, `vscode-tree`, and `node` profiles (fast AND protected)

Each phase runs several ~20-40s builds (a generated multi-file TypeScript workload),
showing realistic developer workload. The first build in each phase is a discarded warm-up.

---

## What the Demo Proves

| Phase | MDE Files Scanned | MDE CPU % | EICAR Detected? | Story |
|---|---|---|---|---|
| **Baseline** | Reference (highest) | High | ✅ Yes | Full scanning, full protection |
| **Exclusions** | Fewer | Lower | ❌ No | Protection gap - malware slips through |
| **Profiles** | Fewer | Lower | ✅ Yes | Fast build, real protection maintained |

The primary metric is **MDE files scanned** (from real-time protection statistics),
which the VSCode demo reports as a per-phase delta. Wall-clock build time is a
secondary, noisier signal.

**Key insight:** Performance profiles mute specific developer process trees (VSCode, Xcode, Node), reducing scanning overhead **without creating a protection gap**. Folder exclusions achieve speed but blind protection everywhere in those directories.

---

## Prerequisites

- **macOS** with Microsoft Defender for Endpoint installed and real-time protection enabled
- **For Xcode demo:** Xcode Command Line Tools (`xcode-select --install`)
- **For VSCode demo:** Node.js 18+ and npm
- **`sudo` access** (for mdatp profile/exclusion commands)

---

## How It Works

Each `run-demo.sh` script:
1. **Phase 1 (Baseline):** Builds with no profiles or exclusions
2. **Phase 2 (Exclusions):** Adds folder exclusions, builds, tests EICAR detection
3. **Phase 3 (Profiles):** Applies MDE profiles, builds, tests EICAR detection

The EICAR test file is the security checkpoint — if it's not detected (Phase 2), real-time protection has a gap. If it's detected (Phase 3), protection is intact.

---

## Understanding Performance Profiles

Performance profiles are **built-in MDE configurations** that reduce scanning for specific developer tools:

- `xcode` and `xcode-tree` — mute Xcode compiler processes
- `vscode` and `vscode-tree` — mute VSCode and its language servers, watchers, debuggers
- `node` — mutes Node.js processes  
- `git` — mutes Git operations

Unlike folder exclusions (which blind all protection in a directory regardless of who accesses it), profiles only mute **events from specific processes**. Other processes writing to the same directories are still fully scanned.

```bash
# List all available profiles
mdatp performance-profiles list-available

# Apply a profile
sudo mdatp performance-profiles apply xcode

# See what's active
mdatp performance-profiles list-applied

# Remove a profile
sudo mdatp performance-profiles remove xcode
```

---

## Watching CPU Impact in Real-Time

During the demo, open **Activity Monitor** on another desktop:
1. Go to **Activity Monitor** → **Processes**
2. Search for `wdavdaemon_unprivileged`
3. Click the **%CPU** column to sort
4. Watch during each phase—you'll see MDE CPU drop as profiles kick in

---

## Project Details

### Xcode Sample
- **Language:** C + Objective-C
- **Build command:** `xcodebuild -project MDE-Demo.xcodeproj -scheme MDE-Demo build`
- **Build output:** `build/` directory (~20-30s per build)
- **Profiles:** `xcode`, `xcode-tree`
- **Exclusions:** `build/`, `DerivedData/`

### VSCode Sample
- **Language:** TypeScript
- **Build command:** `npm run compile`
- **Build output:** `out/` directory (~20-40s per build with the generated workload; first build discarded as warm-up)
- **Profiles:** `vscode`, `vscode-tree`, `node`, `git`
- **Exclusions:** `out/`, `node_modules/`, `.build/`

---

## Notes

- The demo runs on any Mac with MDE installed; no special hardware or configuration needed
- Each phase pauses so you can observe Activity Monitor CPU % before proceeding
- EICAR detection is the bottom-line security signal—exclusions risk it, profiles don't
- For questions about performance profiles, see [Microsoft Defender Performance Profiles](https://learn.microsoft.com/en-us/defender-endpoint/performance-profiles)
