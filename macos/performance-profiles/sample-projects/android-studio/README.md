# Android Studio Performance Profile Demo

Measures how Microsoft Defender for Endpoint (MDE) affects a real Android/Gradle build,
and shows how the **`openjdk-javac` performance profile** removes the scan overhead
*without* opening the protection gap that AV folder exclusions do.

The demo builds Microsoft's own open-source **[fluentui-android](https://github.com/microsoft/fluentui-android)**
module (MIT-licensed, Gradle/Kotlin) as a realistic Android workload. That project is
**not vendored** into this repo — `setup-project.sh` shallow-clones a pinned commit into
a gitignored `workload.noindex/` directory the first time you run the demo.

## Quick Start

```bash
cd sample-projects/android-studio
./run-demo.sh
```

`run-demo.sh` auto-runs `setup-project.sh` if the workload is missing, then runs three
phases and writes a `REPORT.md` under `run-logs/<timestamp>/`.

1. **Baseline** — full scanning, full protection.
2. **AV Exclusions** — exclude the build/cache directories (faster, but EICAR goes undetected).
3. **Performance Profiles** — apply the `openjdk-javac` profile (fast AND EICAR still detected).

## Prerequisites

A one-time, no-sudo toolchain install (Homebrew, Apple Silicon or Intel):

```bash
brew install openjdk@17
brew install --cask android-commandlinetools
```

That's the only manual step — `setup-project.sh` then installs the pinned SDK
packages (`platform-tools`, `platforms;android-34`, `build-tools;31.0.0`) and accepts
the licenses for you (no sudo). To do it by hand instead:

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@17
export ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
SDKM="$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager"
"$SDKM" "platform-tools" "platforms;android-34" "build-tools;31.0.0"
yes | "$SDKM" --licenses
```

Plus:

- macOS with Microsoft Defender for Endpoint installed
- Real-time protection enabled (`mdatp health --field real_time_protection_enabled` → `true`)
- `sudo` access (for `mdatp` exclusion/profile commands)
- Network access on first run (to clone the workload and warm the Gradle cache)

The scripts default `JAVA_HOME` to `/opt/homebrew/opt/openjdk@17` and `ANDROID_HOME` to
`/opt/homebrew/share/android-commandlinetools`. Override those env vars if your install
lives elsewhere.

If Tamper Protection is in `block` mode, `real-time-protection-statistics` can return
null; enable troubleshooting mode so scan counts are captured (see the macOS perf TSG).

## What Gets Measured

Each phase runs a warm-up build plus several timed builds and records, as deltas across
the phase, into the report:

- **Median / average build time**
- **MDE files scanned** and **scan time** (from `real-time-protection-statistics`)
- **AV / EDR / all-daemon average CPU %** and **peak RSS**
- **EICAR detection** — ✅ Detected vs ❌ Missed
- **Scan Activity by Phase** — hot-event **Sources** (processes driving scans) and
  **Targets** (the actual files/paths scanned). Targets are the direct signal for
  whether an exclusion is actually being honored.

## The Story

- **Phase 1 (Baseline):** MDE scans the JDK toolchain and every build artifact. Highest CPU.
- **Phase 2 (Exclusions):** Excluding `fluentui_core/build` and the Gradle/Android caches
  speeds the build, but an EICAR file dropped into an excluded folder is **not detected** —
  a protection gap.
- **Phase 3 (Profiles):** The `openjdk-javac` profile mutes the toolchain's scan load, so
  the build stays fast **and** EICAR is still detected. No protection gap.

## Terminal build vs. in-IDE build (important)

There are two related profiles, and they cover different things:

- **`openjdk-javac`** — matches the JDK by its install location. It applies to a
  command-line `./gradlew` build, so it is the profile this terminal demo uses
  (`DEMO_PROFILES="openjdk-javac git"` by default).
- **`android-studio` / `android-studio-tree`** — `android-studio-tree` only mutes builds
  launched from **inside the Android Studio IDE process tree**. A terminal `./gradlew`
  build is *not* covered by it. To exercise this profile, open the workload in Android
  Studio and build from there.

### Running the build from inside Android Studio

This is the interactive "watch CPU drop" demonstration for the IDE-tree profile. It is
**not** the automated measured demo — `run-demo.sh` (terminal) is the one that generates
`REPORT.md`; there is no scripted 3-phase measurement around an in-IDE build because we
can't drive Android Studio's internal build engine from a script.

1. **Open the project.** The `fluentui-android` workload is a standard Gradle project —
   the `workload.noindex/` directory *is* the Android Studio project (there is no separate
   project file like Xcode's `.xcodeproj`):

   ```bash
   ./open-demo.sh   # runs setup if needed, then opens workload.noindex/ in Android Studio
   ```

   Wait for the Gradle sync to finish (progress in the bottom status bar).

2. **Build from within the IDE** (either triggers a build inside Android Studio's process
   tree):
   - **Build → Make Module 'fluentui_core'**, or
   - Gradle tool window (right edge) → `fluentui_core` → `Tasks` → `build` → double-click
     **assembleDebug**.

3. **Apply the IDE profiles** in a terminal (needs sudo):

   ```bash
   sudo mdatp performance-profiles apply --name android-studio
   sudo mdatp performance-profiles apply --name android-studio-tree
   ```

4. **Rebuild** (⌘F9 / Make again) and watch `wdavdaemon_unprivileged` CPU in Activity
   Monitor drop for the in-IDE build. Then clean up:

   ```bash
   sudo mdatp performance-profiles remove --name android-studio-tree
   sudo mdatp performance-profiles remove --name android-studio
   ```

`open-demo.sh` also echoes these steps after launching the IDE.

> Note: there is no Android emulator/AVD performance profile, so this demo is scoped to
> the **build**, not to installing/launching the app on an emulator.

## Build Details

- **Workload:** `microsoft/fluentui-android` (MIT), pinned commit, cloned into `workload.noindex/`
- **Build command:** `./gradlew :fluentui_core:assembleDebug --no-daemon --offline`
- **Build output directory:** `fluentui_core/build/` (removed between builds for a clean recompile)
- **AV exclusion paths (Phase 2):** `fluentui_core/build/`, `~/.gradle/caches`, `~/.android`
- **Profiles applied (Phase 3):** `openjdk-javac`, `git` (override with `DEMO_PROFILES=...`)

> The timed builds run with `--offline` for reproducible timing; `setup-project.sh` does a
> full online build first to download all dependencies into `~/.gradle`.

## Configuration

Environment variables honored by the scripts:

| Variable | Default | Purpose |
|---|---|---|
| `DEMO_PROFILES` | `openjdk-javac git` | Profiles applied in Phase 3 |
| `MDE_GRADLE_TASK` | `:fluentui_core:assembleDebug` | Gradle task to build |
| `MDE_WORKLOAD_REPO` | `microsoft/fluentui-android` | Workload git repo |
| `MDE_WORKLOAD_REF` | pinned SHA | Workload commit/ref to check out |
| `JAVA_HOME` | `/opt/homebrew/opt/openjdk@17` | JDK 17 location |
| `ANDROID_HOME` | `/opt/homebrew/share/android-commandlinetools` | Android SDK location |

## Files

- `setup-project.sh` — clones the pinned workload and warms the Gradle cache
- `run-demo.sh` — the measured three-phase terminal demo (generates `REPORT.md`)
- `open-demo.sh` — opens the workload in Android Studio for the `android-studio-tree` path
- The report is rendered by the shared `../lib/generate-report.js`

## Cleanup

```bash
rm -rf workload.noindex run-logs
```

## Attribution

The build workload is [microsoft/fluentui-android](https://github.com/microsoft/fluentui-android),
© Microsoft, licensed under the MIT License. It is fetched at setup time and is not
redistributed as part of this repository.
