#!/bin/bash
# xcode-report.sh - Install/remove the MDE report card into an Xcode scheme's Build
# pre/post-actions, so building that scheme inside Xcode prints an MDE profile report.
#
# This is the Xcode analog of the Android sample's ide-report.sh. Xcode has no global
# init directory like Gradle's ~/.gradle/init.d, so instead we inject Build *pre-actions*
# and *post-actions* (Edit Scheme > Build > Pre-actions / Post-actions) that call
# mde-profile-report.sh to bracket the build. The pre-action snapshots MDE scan counters;
# the post-action snapshots again and prints the report.
#
# The target scheme lives inside the gitignored workload.noindex/ clone, so these edits
# are local only. `off` removes just the actions we added.
#
# Usage:
#   ./xcode-report.sh on       # inject pre/post-actions into the scheme
#   ./xcode-report.sh off      # remove them
#   ./xcode-report.sh status   # show whether they are installed

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORT_SCRIPT="$PROJECT_DIR/mde-profile-report.sh"
WORKLOAD_DIR="$PROJECT_DIR/workload.noindex"
# The iOS demo app scheme (an .xcodeproj scheme persists pre/post-actions; a SwiftPM
# Package.swift scheme does not). Default to Demo.Development because Demo.Dogfood
# requires extra AppCenter/provisioning setup. Override with MDE_XCODE_SCHEME if needed.
SCHEME="${MDE_XCODE_SCHEME:-$WORKLOAD_DIR/Demos/FluentUIDemo_iOS/FluentUI.Demo.xcodeproj/xcshareddata/xcschemes/Demo.Development.xcscheme}"

MARKER="MDE report:"

if [ ! -f "$SCHEME" ]; then
    echo "✗ Scheme not found: $SCHEME"
    echo "  Run ./setup-project.sh first (it clones the workload), or set MDE_XCODE_SCHEME."
    exit 1
fi

action="${1:-status}"

case "$action" in
    on|enable|install)
        [ -x "$REPORT_SCRIPT" ] || chmod +x "$REPORT_SCRIPT" 2>/dev/null || true
        REPORT_SCRIPT="$REPORT_SCRIPT" MARKER="$MARKER" /usr/bin/python3 - "$SCHEME" <<'PY'
import sys, os
import xml.etree.ElementTree as ET

scheme = sys.argv[1]
report = os.environ["REPORT_SCRIPT"]
marker = os.environ["MARKER"]

tree = ET.parse(scheme)
root = tree.getroot()
build = root.find("BuildAction")
if build is None:
    print("✗ No <BuildAction> in scheme"); sys.exit(1)

AT = "Xcode.IDEStandardExecutionActionsCore.ExecutionActionType.ShellScriptAction"

def make_actions(title, cmd):
    ea = ET.Element("ExecutionAction", {"ActionType": AT})
    ac = ET.SubElement(ea, "ActionContent", {
        "title": title,
        "scriptText": f'/bin/bash "{report}" {cmd}\n',
    })
    return ea

def ensure_container(tag, index):
    el = build.find(tag)
    if el is None:
        el = ET.Element(tag)
        build.insert(index, el)
    # drop any of OUR previous actions so this is idempotent
    for ea in list(el.findall("ExecutionAction")):
        ac = ea.find("ActionContent")
        if ac is not None and (ac.get("title") or "").startswith(marker):
            el.remove(ea)
    return el

# BuildAction child order must be: PreActions, PostActions, BuildActionEntries.
pre = ensure_container("PreActions", 0)
post = ensure_container("PostActions", 1 if build.find("PreActions") is not None else 0)

pre.append(make_actions(f"{marker} snapshot before", "before"))
post.append(make_actions(f"{marker} snapshot after and report", "after"))

tree.write(scheme, encoding="UTF-8", xml_declaration=True)
print("✓ MDE report installed into scheme pre/post-actions")
PY
        echo "  Scheme: $SCHEME"
        echo "  Open FluentUI.Demo.xcodeproj in Xcode, select the 'Demo.Development' scheme, and Build (Cmd+B)."
        echo "  The report prints in the build log (Report navigator) and as a notification."
        echo "  Run './xcode-report.sh off' when you're done."
        ;;
    off|disable|remove|uninstall)
        MARKER="$MARKER" /usr/bin/python3 - "$SCHEME" <<'PY'
import sys, os
import xml.etree.ElementTree as ET

scheme = sys.argv[1]
marker = os.environ["MARKER"]
tree = ET.parse(scheme)
root = tree.getroot()
build = root.find("BuildAction")
removed = 0
if build is not None:
    for tag in ("PreActions", "PostActions"):
        el = build.find(tag)
        if el is None:
            continue
        for ea in list(el.findall("ExecutionAction")):
            ac = ea.find("ActionContent")
            if ac is not None and (ac.get("title") or "").startswith(marker):
                el.remove(ea); removed += 1
        if len(list(el)) == 0:
            build.remove(el)
tree.write(scheme, encoding="UTF-8", xml_declaration=True)
print(f"✓ MDE report removed from scheme ({removed} action(s))")
PY
        ;;
    status)
        if grep -q "$MARKER" "$SCHEME" 2>/dev/null; then
            echo "● ENABLED in $SCHEME"
        else
            echo "○ disabled (not present in $SCHEME)"
        fi
        ;;
    *)
        echo "Usage: $0 {on|off|status}"; exit 2
        ;;
esac
