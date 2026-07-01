# Xcode Performance Profile Demo

This is a minimal command-line app demonstrating how the `xcode` and `xcode-tree` performance profiles impact MDE scanning during Xcode builds.

## Quick Start

```bash
cd sample-projects/xcode
./run-demo.sh
```

This will run three phases:
1. **Baseline**: Build with no profiles or exclusions
2. **AV Exclusions**: Build with folder exclusions (protection gap)
3. **Performance Profiles**: Build with `xcode` and `xcode-tree` profiles (protected build)

## What to Observe

- **Build time** for each phase (shown in terminal output)
- **MDE CPU usage** (open Activity Monitor → search `wdavdaemon_unprivileged` to watch CPU %)
- **EICAR detection** (shown at end of each phase):
  - ✅ Detected = Real-time protection is active
  - ❌ NOT Detected = Protection gap (only happens with exclusions)

## The Story

- **Phase 1 (Baseline)**: Full scanning, full protection. MDE CPU is high as Xcode and all child processes are scanned.
- **Phase 2 (Exclusions)**: Faster build (folders excluded from scanning), but malware in those directories goes undetected.
- **Phase 3 (Profiles)**: Build stays fast (MDE process tree muted) AND malware is still detected. No protection gap.

## Prerequisites

- macOS with Microsoft Defender for Endpoint installed
- Real-time protection enabled (`mdatp health --field real_time_protection_enabled` returns `true`)
- Xcode with command-line tools
- `sudo` access (for mdatp commands)

## Build Details

- **Project**: Simple C+Objective-C command-line tool
- **Build command**: `xcodebuild -project MDE-Demo.xcodeproj -scheme MDE-Demo -derivedDataPath build build`
- **Build output directory**: `build/` (cleaned between phases)
- **AV exclusion paths**: `build/`, `DerivedData/`
- **Profiles applied**: `xcode`, `xcode-tree`

## Notes

- Each phase takes ~20-30 seconds to build
- Open Activity Monitor to watch `wdavdaemon_unprivileged` CPU spike and drop across the three phases
- The `run-demo.sh` script handles all profile/exclusion toggling automatically
- Clean up with: `rm -rf build`
