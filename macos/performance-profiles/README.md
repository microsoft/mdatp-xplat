# MDE Performance Profiles — Before/After Build Demo

Performance profiles are **curated sets of antivirus exclusions** for Microsoft Defender for Endpoint on macOS. Instead of IT admins manually researching which file paths, processes, and file extensions to exclude for common developer tools and third-party software, MDE ships 60+ pre-built profiles that can be activated with a single command.

```bash
# List all available profiles
mdatp performance-profiles list-available

# Apply a profile
mdatp performance-profiles apply xcode

# Apply multiple profiles at once
mdatp performance-profiles apply xcode dotnet-build node

# See what's currently active
mdatp performance-profiles list-active

# Remove a profile
mdatp performance-profiles remove xcode
```

**Why they matter:** Real-time protection scans every file read/write operation. During software builds, compilers read and write thousands of files per second. Without exclusions, MDE's scanning can add 30–200% overhead to build times. Performance profiles eliminate this by excluding known-safe build artifacts, intermediate files, and tool-specific paths — without reducing security posture.

> **Learn more:** [Performance profiles documentation](https://learn.microsoft.com/en-us/defender-endpoint/performance-profiles)

## Demo Overview

This directory contains scripts that demonstrate the impact of performance profiles by:

1. **Building** a Microsoft open-source project on macOS with MDE real-time protection on
2. **Diagnosing** the performance impact using MDE's built-in diagnostic tools
3. **Applying** performance profiles with one command
4. **Verifying** the improvement by rebuilding and re-running diagnostics

The demo tells a complete story: diagnose → identify → fix → verify — the same workflow a field engineer or IT admin would follow with a real customer.

## Available Demo Scripts

| Script | Target Repo | Build System | Profiles Used | Duration |
|---|---|---|---|---|
| [`perf-profile-demo.sh`](perf-profile-demo.sh) | [microsoft/vscode](https://github.com/microsoft/vscode) | Node.js / TypeScript | `node`, `git`, `xcode`, `vscode`, `vscode-tree` | ~20 min |
| [`perf-profile-demo-xcode.sh`](perf-profile-demo-xcode.sh) | [microsoft/fluentui-apple](https://github.com/microsoft/fluentui-apple) | Xcode / Swift | `xcode`, `xcode-ide-tree`, `git` | ~10 min |

For the Python entrypoint (`demo.py`), an additional scenario is available:
- `xcode-simulator` (HelloDefender simulator workflow): runs `xcodebuild test` by default, then builds the in-repo `apps/hello-defender-ios` app, boots simulator, installs and launches app using `simctl`; profile set: `xcode`, `ios-simulator-tree`, `iphone-simulator-tree`, `git`

## Prerequisites

- **macOS** with [Microsoft Defender for Endpoint](https://learn.microsoft.com/en-us/defender-endpoint/microsoft-defender-endpoint-mac) installed
- MDE version that supports performance profiles (check `mdatp performance-profiles list-available`)
- **Real-time protection enabled** (`mdatp health --field real_time_protection_enabled` should return `true`)
- `sudo` access — most `mdatp` commands require elevated privileges (profile management, diagnostics, configuration). The script will prompt for your password on first use
- Build tools for your chosen demo:
  - **VS Code demo:** `node` (v22+), `git`, `jq`, `python3`, Xcode Command Line Tools — see the [official VS Code build prerequisites](https://github.com/microsoft/vscode/wiki/How-to-Contribute#prerequisites)
  - **Xcode demo:** Xcode (with command line tools), `git`, `jq`

### One-Time Setup

The VS Code demo follows the official [How to Contribute](https://github.com/microsoft/vscode/wiki/How-to-Contribute) build instructions.

```bash
# ── For the VS Code demo ──

# Install build tools (Python + Xcode CLT also required for node-gyp)
brew install node@22 git jq
xcode-select --install   # if not already installed

# Clone VS Code (pinned to a stable tag)
git clone --depth 1 --branch 1.122.1 https://github.com/microsoft/vscode.git ~/demo/vscode
cd ~/demo/vscode
npm install   # follows official VS Code build steps

# ── For the Xcode demo ──

# Clone Fluent UI Apple
git clone https://github.com/microsoft/fluentui-apple.git ~/demo/fluentui-apple

# ── Client Analyzer (optional, enhances both demos) ──

mkdir -p ~/demo/analyzer && cd ~/demo/analyzer
curl -s -L -o XMDEClientAnalyzerBinary.zip "https://aka.ms/XMDEClientAnalyzerBinary"
unzip -q XMDEClientAnalyzerBinary.zip -d XMDEClientAnalyzerBinary
cd XMDEClientAnalyzerBinary && unzip -q SupportToolMacOSBinary.zip
xattr -cr MDESupportTool
```

## Running the Demo

```bash
# Make the script executable
chmod +x perf-profile-demo.sh

# Run with default settings (builds VS Code from ~/demo/vscode)
./perf-profile-demo.sh

# Choose consent policy for applying/removing profiles
python3 demo.py vscode --profile-change-policy prompt   # default
python3 demo.py vscode --profile-change-policy always   # no prompts
python3 demo.py vscode --profile-change-policy never    # never apply/remove

# Or specify a custom repo path
./perf-profile-demo.sh ~/my/vscode/checkout

# Quick Xcode demo
chmod +x perf-profile-demo-xcode.sh
./perf-profile-demo-xcode.sh

# Simulator-profile demo via Python entrypoint
python3 demo.py xcode-simulator

# Optional: run xcode-simulator with your own local iOS app project
# python3 demo.py xcode-simulator --repo ~/demo/my-ios-app

# When recommendations are available, you'll be prompted with consolidated choices.
# Duplicate profile sets are merged and labeled with all contributing sources
# (GHCP, Python, Intersection, Union, Defaults).
# The run log records each source set and the selected consolidated source label.
```

## The 5-Phase Story

| Phase | What You Do | What the Audience Sees |
|---|---|---|
| **1. Baseline Build** | Build with no profiles active | "Look how slow this is with MDE scanning everything" |
| **2. Diagnose — Hot Event Sources** | Run `mdatp diagnostic hot-event-sources` | Ranked list of processes flooding the MDE sensor |
| **3. Diagnose — RTP Statistics** | Capture `real-time-protection-statistics` | Top file-scanning processes ranked by scan count |
| **4. Apply Profiles** | `mdatp performance-profiles apply ...` | One-command fix — no MDM, no JSON, no manual paths |
| **5. Verify** | Rebuild + re-run diagnostics | Build faster, hot events gone, CPU drops |

## Diagnostic Tools Used

### Admin-Only Mode (MDM-Managed Profiles)

When performance profiles are deployed via MDM (Intune, JAMF, etc.), the endpoint is in **admin-only mode** — local users cannot apply or remove profiles. The demo scripts detect this automatically and guide you through a two-session workflow.

#### Step 1: Enable Performance Profiles in Intune

In your management portal, create or edit a **Settings Catalog** policy. Add the **Microsoft Defender > Performance Profiles Configuration** and **Features** settings:

- **Performance profiles merge policy** → `admin_only` (prevents local users from applying/removing profiles)
- **Performance Profiles** → `enabled`

**Intune:**

![Intune Settings Catalog — Performance Profiles enabled with admin-only merge policy](images/intune-perf-profiles-enabled.png)

**Security Settings Management (Microsoft Defender portal):**

![Security Settings Management — Performance Profiles enabled with admin-only merge policy](images/ssm-perf-profiles-enabled.png)

> With `admin_only` merge policy, profiles can only be deployed and removed through MDM. The demo scripts detect this and guide you through a two-session workflow.

#### Step 2: Run the Baseline (Session 1)

Run the demo script. It detects admin-only mode with no profiles applied and runs the baseline build:

```
✅ Profile mode: admin-only (no profiles applied — ready for baseline)
```

After the baseline completes, the script saves a checkpoint and exits with instructions:

```
⚠️  Admin-only mode — profiles cannot be applied locally.
Ask your IT admin to deploy these profiles via MDM (Intune, JAMF, etc.):
  - node
  - git
  - vscode
  - vscode-tree

Once deployed, re-run this script to see the comparison.
(Your baseline results have been saved — you'll be prompted to continue.)
```

#### Step 3: Deploy Profiles via MDM

In **Microsoft Defender > Performance Profiles Configuration > Performance Profiles**, add the profiles requested by the demo (for VS Code: `git`, `node`, `vscode`, `vscode-tree`).

**Intune profile selection example:**

![Intune Settings Catalog — Performance Profiles enabled with selected profiles for deployment](images/intune-perf-profiles-enabled-with-profiles.png)

Deploy the requested profiles through your MDM solution. The profiles will appear in `mdatp performance-profiles list-applied` once the policy syncs to the endpoint.

#### Step 4: Resume the Demo (Session 2)

Re-run the script. It detects the saved checkpoint and prompts:

```
📋 Previous run detected — baseline already complete.
   Baseline build time: 182 seconds
   MDE avg CPU:         94%

Continue to comparison build, or restart from scratch? [C/r]
```

Press **Enter** (or **C**) to continue. The script verifies all profiles are deployed, then runs the comparison build and shows results.

---

### Diagnostic Tools Used

### `mdatp diagnostic hot-event-sources`

Counts **all sensor-level events** (AUTH + NOTIFY) by process. Shows which processes are generating the most file system activity that MDE must process.

```bash
# Collect for 60 seconds (run during a build for meaningful data)
sudo mdatp diagnostic hot-event-sources --time=60

# Output: hot_event_source_<uuid>.json in current directory
jq '.eventSource[0:5]' hot_event_source_*.json
```

### `mdatp diagnostic real-time-protection-statistics`

Tracks which processes triggered the most **antivirus file scans** (a subset of all sensor events).

```bash
# Enable collection
mdatp config real-time-protection-statistics --value enabled

# (run your build)

# Capture snapshot
mdatp diagnostic real-time-protection-statistics --output json > rtp_stats.json

# Parse with the official high_cpu_parser.py
curl -O https://raw.githubusercontent.com/microsoft/mdatp-xplat/master/linux/diagnostic/high_cpu_parser.py
cat rtp_stats.json | python3 high_cpu_parser.py | head -10
```

### XMDE Client Analyzer (optional)

The Client Analyzer's `performance` mode produces an HTML report with hot event sources in a visual, shareable format.

```bash
sudo ./MDESupportTool performance --length 30
# Output: MDESupportTool_<timestamp>.zip with eps_event_stat_sample.html
```

> **Learn more:** [Troubleshoot performance issues](https://learn.microsoft.com/en-us/defender-endpoint/mac-support-perf)

## Available Profiles

The scripts use profiles relevant to the build being demonstrated. Here are some of the 60+ profiles available:

| Profile | What It Excludes |
|---|---|
| `xcode` | Xcode.app, DerivedData, build intermediates, simulator runtimes |
| `xcode-ide-tree` | Xcode IDE workspace caches and index files |
| `dotnet-build` | `bin/`, `obj/`, NuGet caches, MSBuild temp files |
| `node` | `node_modules/`, npm caches, V8 compilation cache |
| `git` | `.git/` objects, pack files, index operations |
| `make-tree` | Make build output trees |
| `rust` | `target/`, cargo registry, incremental compilation cache |
| `google-golang` | Go module cache, build cache, `GOPATH` artifacts |
| `vscode` / `vscode-tree` | VS Code extension host, workspace storage |
| `docker` | Docker images, volumes, build cache |
| `jetbrains` | IntelliJ/PyCharm/Rider caches and indexes |

Run `mdatp performance-profiles list-available` to see the full list.

## Expected Results

Results vary by hardware (Apple Silicon vs Intel), disk speed, and MDE version. Typical results:

| Metric | Without Profiles | With Profiles | Improvement |
|---|---|---|---|
| VS Code build time | ~180s | ~120s | ~33% faster |
| MDE CPU (avg) | 80–120% | 5–15% | ~85% drop |
| Files scanned (RTP) | 50,000+ | 2,000–5,000 | ~90% fewer |
| Fluent UI (Xcode) build | ~90s | ~60s | ~33% faster |

> **Tip:** Run the demo on your target hardware at least once before presenting to get real numbers for your environment.

## Presenter Talking Points

1. "A customer calls: 'MDE is slowing down our developer builds on macOS.'"
2. "We use **hot event sources** — a built-in sensor diagnostic — to see which processes are flooding MDE with file system events."
3. "Then **RTP statistics** tells us exactly how many files each process triggered scans on."
4. "The diagnosis is clear: `node`, `tsc`, `npm`, and `git` are the top offenders — all build tools."
5. "The old way: manually craft exclusions, figure out file paths, deploy via MDM, test, iterate."
6. "The new way: `mdatp performance-profiles apply node git vscode`. Done."
7. "We ship **60+ profiles** — Xcode, .NET, Docker, Rust, Go, JetBrains, and more."
8. "Build is X% faster, MDE CPU dropped, and security protection is unchanged."

## Other Repos to Try

These Microsoft first-party repos also work well with performance profiles:

| Repo | Profiles | Build Command | Notes |
|---|---|---|---|
| [PowerShell/PowerShell](https://github.com/PowerShell/PowerShell) | `dotnet-build`, `git` | `dotnet build` | .NET build, 2–5 min |
| [dotnet/maui](https://github.com/dotnet/maui) | `dotnet-build`, `xcode`, `git` | `dotnet build -f net8.0-maccatalyst` | Xcode + .NET combo |
| [dotnet/runtime](https://github.com/dotnet/runtime) | `dotnet-build`, `git`, `make-tree` | `./build.sh` | Long build (15–30 min) |

## Contributing

Found a bug or want to improve these scripts? PRs welcome! See the [contribution guidelines](../../CONTRIBUTING.md).
