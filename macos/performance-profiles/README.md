# MDE Performance Profiles Demo

This directory contains simplified, hands-on demonstrations of Microsoft Defender for Endpoint (MDE) performance profiles on macOS.

## Quick Start

This README focuses on the automated **terminal** 3-phase demos.
Each sample project also includes a separate **IDE experience** in its own README.

Three sample projects are available:

### 1. Xcode Demo (Swift/Xcode)
```bash
cd sample-projects/xcode
./setup-project.sh    # Fetch the pinned workload
./run-demo.sh         # Run the three-phase demo
```

**What it shows:**
- Baseline Xcode build (no profiles/exclusions)
- Build with folder exclusions (faster, but protection gap)
- Build with `xcode` profile (fast AND protected)

Each phase runs warm-up + timed builds and writes `REPORT.md` to `run-logs/<timestamp>/`.

**IDE experience (separate from the measured terminal demo):**
- Open and build the FluentUI workload from inside Xcode to exercise IDE-tree coverage (`xcode-ide-tree`)
- See [sample-projects/xcode/README.md](sample-projects/xcode/README.md) for the exact in-IDE steps (`open-demo.sh`, scheme build flow, report-card wiring)

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
- Compilation with `node`, `vscode`, `vscode-tree`, and `git` profiles (fast AND protected)

Each phase runs several ~20-40s builds (a generated multi-file TypeScript workload),
showing realistic developer workload. The first build in each phase is a discarded warm-up.

**IDE experience (recommended path for VSCode-tree coverage):**
- Run the demo from VSCode tasks/integrated terminal so the build runs under the VSCode process tree
- See [sample-projects/vscode/README.md](sample-projects/vscode/README.md) for exact task flow and process-tree notes

---

### 3. Android Studio Demo (Gradle/Kotlin)
```bash
cd sample-projects/android-studio
./run-demo.sh
```

`run-demo.sh` auto-runs setup on first use, then performs the same three phases and
generates `REPORT.md` in `run-logs/<timestamp>/`.

**What it shows:**
- Baseline Gradle build with full scanning
- Build with folder/cache exclusions (faster, but protection gap)
- Build with `openjdk-javac` (and `git`) profiles (fast AND protected)

The Android workload is `microsoft/fluentui-android`, cloned on-demand into `workload.noindex/`.

**IDE experience (separate from the measured terminal demo):**
- Open the workload in Android Studio and build from the IDE to exercise `android-studio-tree`
- See [sample-projects/android-studio/README.md](sample-projects/android-studio/README.md) for exact in-IDE steps (`open-demo.sh`, Gradle tool window path, IDE report card)

---

## Terminal vs IDE Experiences

- **Terminal demos (this README):** automated, repeatable, 3-phase runs that generate `REPORT.md` artifacts.
- **IDE demos (sample READMEs):** interactive, in-IDE build flows that demonstrate IDE-tree profile behavior and live before/after scan changes.
- Use the sample-specific README whenever you want to validate IDE process-tree coverage details.

Direct links:
- [sample-projects/xcode/README.md](sample-projects/xcode/README.md)
- [sample-projects/vscode/README.md](sample-projects/vscode/README.md)
- [sample-projects/android-studio/README.md](sample-projects/android-studio/README.md)

---

## What the Demo Proves

| Phase | MDE Files Scanned | MDE CPU % | EICAR Detected? | Story |
|---|---|---|---|---|
| **Baseline** | Reference (highest) | High | ✅ Yes | Full scanning, full protection |
| **Exclusions** | Fewer | Lower | ❌ No | Protection gap - malware slips through |
| **Profiles** | Fewer | Lower | ✅ Yes | Fast build, real protection maintained |

The primary metric is **MDE files scanned** (from real-time protection statistics),
reported as a per-phase delta. Wall-clock build time is a
secondary, noisier signal.

**Key insight:** Performance profiles mute specific developer toolchains and process trees (Xcode/Swift, VSCode/Node, JDK/Gradle), reducing scanning overhead **without creating a protection gap**. Folder exclusions achieve speed but blind protection everywhere in those directories.

---

## Prerequisites

- **macOS** with Microsoft Defender for Endpoint installed and real-time protection enabled
- **For Xcode demo:** Xcode + command-line tools (`swift` and `xcodebuild` on `PATH`)
- **For VSCode demo:** Node.js 18+ and npm
- **For Android Studio demo:**
	- `brew install openjdk@17`
	- `brew install --cask android-commandlinetools`
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

- `xcode` and `xcode-ide-tree` — Xcode toolchain and IDE-tree coverage
- `vscode` and `vscode-tree` — mute VSCode and its language servers, watchers, debuggers
- `node` — mutes Node.js processes
- `openjdk-javac` — mutes JDK/Javac-driven Android/Gradle build activity
- `android-studio` and `android-studio-tree` — Android Studio IDE and IDE-tree coverage
- `git` — mutes Git operations

Unlike folder exclusions (which blind all protection in a directory regardless of who accesses it), profiles only mute **events from specific processes**. Other processes writing to the same directories are still fully scanned.

```bash
# List all available profiles
mdatp performance-profiles list-available

# Apply a profile
sudo mdatp performance-profiles apply --name xcode

# See what's active
mdatp performance-profiles list-applied

# Remove a profile
sudo mdatp performance-profiles remove --name xcode
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
- **Language:** Swift (SwiftPM, FluentUI Apple workload)
- **Build command:** `swift build --product FluentUI`
- **Build output:** `.build/` (cleaned between timed builds)
- **Profiles:** `xcode`, `git` (with `xcode-ide-tree` for in-IDE Xcode builds)
- **Exclusions:** `.build/`, `DerivedData/`

### VSCode Sample
- **Language:** TypeScript
- **Build command:** `npm run compile`
- **Build output:** `out.noindex/` (~20-40s per build with generated workload; first build discarded as warm-up)
- **Profiles:** `vscode`, `vscode-tree`, `node`, `git`
- **Exclusions:** `out.noindex/`, `node_modules/`, `.build/`

### Android Studio Sample
- **Language:** Gradle/Kotlin (`microsoft/fluentui-android`)
- **Build command:** `./gradlew :fluentui_core:assembleDebug --no-daemon --offline`
- **Build output:** `fluentui_core/build/` (cleaned between timed builds)
- **Profiles:** `openjdk-javac`, `git` (with `android-studio` + `android-studio-tree` for in-IDE builds)
- **Exclusions:** `fluentui_core/build/`, `~/.gradle/caches`, `~/.android`

---

## Notes

- The demo runs on any Mac with MDE installed; no special hardware or configuration needed
- Each sample includes both timing and scan-count evidence in per-run `REPORT.md`
- Terminal and in-IDE builds use different profile coverage paths in Xcode, VSCode, and Android Studio
- IDE steps and caveats are documented in each sample project's README
- EICAR detection is the bottom-line security signal—exclusions risk it, profiles don't
- For questions about performance profiles, see [Microsoft Defender Performance Profiles](https://learn.microsoft.com/en-us/defender-endpoint/performance-profiles)
