# Xcode Performance Profile Demo

Measures how Microsoft Defender for Endpoint (MDE) affects a real Swift/Xcode build,
and shows how the **`xcode` performance profile** removes the scan overhead *without*
opening the protection gap that AV folder exclusions do.

The demo builds Microsoft's own open-source **[fluentui-apple](https://github.com/microsoft/fluentui-apple)**
package (MIT-licensed, SwiftPM-native) as a realistic Swift workload. That project is
**not vendored** into this repo — `setup-project.sh` shallow-clones a pinned commit
into a gitignored `workload.noindex/` directory the first time you run the demo.

## Quick Start

```bash
cd sample-projects/xcode
./run-demo.sh
```

`run-demo.sh` auto-runs `setup-project.sh` if the workload is missing, then runs three
phases and writes a `REPORT.md` under `run-logs/<timestamp>/`.

1. **Baseline** — full scanning, full protection.
2. **AV Exclusions** — exclude the build directories (faster, but EICAR goes undetected).
3. **Performance Profiles** — apply the `xcode` profile (fast AND EICAR still detected).

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

- **Phase 1 (Baseline):** MDE scans the toolchain and every build artifact. Highest CPU.
- **Phase 2 (Exclusions):** Excluding `.build`/`DerivedData` speeds the build, but an
  EICAR file dropped into an excluded folder is **not detected** — a protection gap.
- **Phase 3 (Profiles):** The `xcode` profile mutes the toolchain's scan load, so the
  build stays fast **and** EICAR is still detected. No protection gap.

## Terminal build vs. in-IDE build (important)

There are two related profiles, and they cover different things:

- **`xcode`** — matches the Swift/Clang toolchain by its install location. It applies to
  a command-line `swift build`, so it is the profile this terminal demo uses
  (`DEMO_PROFILES="xcode git"` by default).
- **`xcode-ide-tree`** — only mutes builds launched from **inside the Xcode IDE process
  tree**. A terminal `swift build` is *not* covered by it. To exercise this profile,
  open the workload in Xcode and build with Cmd+B:

  ```bash
  ./open-demo.sh   # fetches the workload and opens Package.swift in Xcode
  ```

  `open-demo.sh` prints the exact `mdatp performance-profiles apply --name xcode-ide-tree`
  steps to run while building from the IDE.

> Note: the earlier version of this demo referenced a profile named `xcode-tree`. That
> profile does not exist — the real names are `xcode` and `xcode-ide-tree`.

## Prerequisites

- macOS with Microsoft Defender for Endpoint installed
- Real-time protection enabled (`mdatp health --field real_time_protection_enabled` → `true`)
- Xcode + command-line tools (`swift` and `xcodebuild` on `PATH`)
- `sudo` access (for `mdatp` exclusion/profile commands)
- Network access on first run (to clone the workload)

If Tamper Protection is in `block` mode, `real-time-protection-statistics` can return
null; enable troubleshooting mode so scan counts are captured (see the macOS perf TSG).

## Build Details

- **Workload:** `microsoft/fluentui-apple` (MIT), pinned commit, cloned into `workload.noindex/`
- **Build command:** `swift build --product FluentUI` (debug) against the macOS SDK
- **Build output directory:** `.build/` (removed between builds for a clean recompile)
- **AV exclusion paths (Phase 2):** `.build/`, `DerivedData/`
- **Profiles applied (Phase 3):** `xcode`, `git` (override with `DEMO_PROFILES=...`)

## Configuration

Environment variables honored by the scripts:

| Variable | Default | Purpose |
|---|---|---|
| `DEMO_PROFILES` | `xcode git` | Profiles applied in Phase 3 |
| `MDE_SWIFT_PRODUCT` | `FluentUI` | SwiftPM product to build |
| `MDE_WORKLOAD_REPO` | `microsoft/fluentui-apple` | Workload git repo |
| `MDE_WORKLOAD_REF` | pinned SHA | Workload commit/ref to check out |

## Files

- `setup-project.sh` — clones the pinned workload into `workload.noindex/`
- `run-demo.sh` — the measured three-phase terminal demo (generates `REPORT.md`)
- `open-demo.sh` — opens the workload in Xcode for the `xcode-ide-tree` path
- `generate-report.js` — renders `REPORT.md` from the captured snapshots

## Cleanup

```bash
rm -rf workload.noindex run-logs
```

## Attribution

The build workload is [microsoft/fluentui-apple](https://github.com/microsoft/fluentui-apple),
© Microsoft, licensed under the MIT License. It is fetched at setup time and is not
redistributed as part of this repository.
