#!/bin/bash
# mde-profile-report.sh - MDE performance-profile "report card" for an Xcode build.
#
# This is the Xcode analog of the Android sample's Gradle init script. It is invoked by
# Xcode Scheme *Build* pre/post-actions (installed by ./xcode-report.sh), which bracket a
# build inside Xcode's process tree:
#
#   pre-action  ->  mde-profile-report.sh before   (snapshot MDE scan counters + time)
#   post-action ->  mde-profile-report.sh after    (snapshot again, print the report)
#
# It only READS mdatp state (performance-profiles list-applied + diagnostic
# real-time-protection-statistics). It never applies/removes profiles or changes
# protection, so it is safe to leave installed. Because Xcode buries pre/post-action
# output in the build log, `after` also writes REPORT to a file and fires a desktop
# notification so the result is visible.

set -uo pipefail

MODE="${1:-after}"
STATE="${MDE_REPORT_STATE:-${TMPDIR:-/tmp}/mde-xcode-report.state}"
REPORT_OUT="${MDE_REPORT_OUT:-${TMPDIR:-/tmp}/mde-xcode-report.txt}"

# Sum totalFilesScanned + totalScanTime(ns) across all per-process counters.
scan_totals() {
    mdatp diagnostic real-time-protection-statistics --output json 2>/dev/null \
    | /usr/bin/python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print("0 0"); sys.exit(0)
f = t = 0
for c in d.get("counters", []):
    try: f += int(c.get("totalFilesScanned") or 0)
    except Exception: pass
    try: t += int(c.get("totalScanTime") or 0)
    except Exception: pass
print(f"{f} {t}")
' 2>/dev/null || echo "0 0"
}

# Profiles listed between the ==== fences of `list-applied`.
applied_profiles() {
    mdatp performance-profiles list-applied 2>/dev/null | awk '
        /^====/ { inside = !inside; next }
        inside && $0 !~ /^---/ && NF { print }
    ' | paste -sd',' - | sed 's/,/, /g'
}

# Walk the parent-process chain looking for the Xcode IDE.
under_xcode() {
    local pid=$PPID i line comm
    for ((i=0; i<30; i++)); do
        [ "${pid:-0}" -le 1 ] && break
        line=$(ps -o ppid=,comm= -p "$pid" 2>/dev/null) || break
        [ -z "$line" ] && break
        comm=$(printf '%s' "$line" | sed 's/^[[:space:]]*[0-9]*[[:space:]]*//')
        case "$comm" in *Xcode*) return 0;; esac
        pid=$(printf '%s' "$line" | awk '{print $1}')
    done
    return 1
}

if [ "$MODE" = "before" ]; then
    read -r bf bt < <(scan_totals)
    printf '%s %s %s\n' "${bf:-0}" "${bt:-0}" "$(date +%s)" > "$STATE"
    exit 0
fi

# ---- after: compute delta + render ----------------------------------------
bf=0; bt=0; bstart=$(date +%s)
[ -f "$STATE" ] && read -r bf bt bstart < "$STATE"
read -r af at < <(scan_totals)
dfiles=$(( ${af:-0} - ${bf:-0} ))
dns=$(( ${at:-0} - ${bt:-0} ))
neg=0
[ "$dfiles" -lt 0 ] && { dfiles=0; neg=1; }
[ "$dns" -lt 0 ] && { dns=0; neg=1; }
dms=$(awk -v n="$dns" 'BEGIN{printf "%.1f", n/1000000.0}')
elapsed=$(( $(date +%s) - ${bstart:-$(date +%s)} ))
profiles=$(applied_profiles)
ide="no / can't tell (daemon or terminal)"; under_xcode && ide="yes"

cover=""
case ",$profiles," in *,xcode,*) cover="xcode";; esac
treeapplied=0
case ",$profiles," in *,xcode-ide-tree,*) treeapplied=1;; esac
suppressed=0
[ "$dfiles" -lt 200 ] && suppressed=1

render() {
    printf '  ┌─ MDE performance-profile report ─────────────────────────────\n'
    printf '  │ Build wall time (pre→post action): %ss\n' "$elapsed"
    printf '  │ Launched inside Xcode process tree: %s\n' "$ide"
    printf '  │ Applied performance profiles: %s\n' "${profiles:-(none)}"
    if [ -n "$cover" ]; then
        printf "  │ ✅ Covered by toolchain profile '%s' (matches the Xcode toolchain).\n" "$cover"
    elif [ "$treeapplied" = 1 ]; then
        printf "  │ ℹ  'xcode-ide-tree' is applied — it covers builds run INSIDE Xcode.\n"
        printf "  │    (Trust the scan delta below as the real proof it's taking effect.)\n"
    elif [ -z "$profiles" ]; then
        printf "  │ ⚠  No profiles applied — MDE is scanning this build at full load.\n"
    else
        printf "  │ ⚠  No profile covers this build — apply 'xcode' (terminal) or 'xcode-ide-tree' (in-IDE).\n"
    fi
    printf '  │ MDE files scanned during build: %s%s\n' "$dfiles" "$([ "$neg" = 1 ] && printf ' (≈)')"
    printf '  │ MDE scan time during build:     %s ms%s\n' "$dms" "$([ "$neg" = 1 ] && printf ' (≈)')"
    if [ "$suppressed" = 1 ]; then
        printf "  │    → ✅ scanning suppressed for this build (profile is working).\n"
    else
        printf "  │    → scanning active — a covering profile would drive this toward ≈0.\n"
    fi
    printf '  └──────────────────────────────────────────────────────────────\n'
    [ "$neg" = 1 ] && printf '  note: a negative raw delta (a busy process exited mid-build) clamped to ≈0.\n'
}

report="$(render)"
printf '%s\n' "$report"
printf '%s\n' "$report" > "$REPORT_OUT" 2>/dev/null || true
osascript -e "display notification \"${dfiles} files scanned this build (see build log)\" with title \"MDE profile report\"" >/dev/null 2>&1 || true
rm -f "$STATE" 2>/dev/null || true
exit 0
