#!/bin/bash
set -euo pipefail

#=============================================================================
# MDE Performance Profiles — Bootstrap Launcher
#
# Purpose:
#   Keep one shell entrypoint that sets up Python environment, then runs
#   the Python demo framework with the selected scenario.
#
# Usage:
#   ./perf-profile-demo.sh                   # prompt for scenario
#   ./perf-profile-demo.sh vscode            # run VS Code scenario
#   ./perf-profile-demo.sh xcode             # run Xcode scenario
#   ./perf-profile-demo.sh xcode-simulator   # run simulator-profile scenario
#   ./perf-profile-demo.sh android-studio    # run Android Studio emulator scenario
#   ./perf-profile-demo.sh --no-sudo-prep xcode  # skip sudo prewarm
#   ./perf-profile-demo.sh vscode --repo ~/demo/vscode
#=============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
REQ_FILE="$SCRIPT_DIR/requirements.txt"
PY_ENTRY="$SCRIPT_DIR/demo.py"
BOOTSTRAP_STAMP="$VENV_DIR/.bootstrap-stamp"
PREP_SUDO=1
SUDO_KEEPALIVE_PID=""
INTERACTIVE=0

if [ -t 0 ] && [ -t 1 ]; then
    INTERACTIVE=1
fi

cleanup() {
    if [ -n "${SUDO_KEEPALIVE_PID:-}" ]; then
        kill "$SUDO_KEEPALIVE_PID" >/dev/null 2>&1 || true
    fi
}

trap cleanup EXIT INT TERM

ARGS=()
POSITIONAL_ARGS=()

HAS_SCENARIO=0
HAS_REPO=0
HAS_RESUME_FROM=0
HAS_INCLUDE_INSTALL=0
HAS_REQUIRE_CLIENT_ANALYZER=0
HAS_CLIENT_ANALYZER_DIR=0
HAS_CLIENT_ANALYZER_MODE=0
HAS_AV_EXCLUSIONS_MODE=0
HAS_REQUIRE_GHCP_CLI=0
HAS_HOT_EVENTS_ANALYSIS=0
HAS_PROFILE_CHANGE_POLICY=0
HAS_HELP=0

SCENARIO_VALUE=""
REPO_OVERRIDE=""
RESUME_FROM_VALUE=""
INCLUDE_INSTALL=0
REQUIRE_CLIENT_ANALYZER=0
CLIENT_ANALYZER_DIR_VALUE=""
CLIENT_ANALYZER_MODE_VALUE="auto"
AV_EXCLUSIONS_MODE_VALUE="auto"
REQUIRE_GHCP_CLI=0
HOT_EVENTS_ANALYSIS_VALUE="prompt"
PROFILE_CHANGE_POLICY_VALUE="prompt"

while [ $# -gt 0 ]; do
    arg="$1"
    case "$arg" in
        --no-sudo-prep)
            PREP_SUDO=0
            shift
            ;;
        --repo)
            HAS_REPO=1
            ARGS+=("$1")
            shift
            if [ $# -gt 0 ]; then
                REPO_OVERRIDE="$1"
                ARGS+=("$1")
                shift
            fi
            ;;
        --repo=*)
            HAS_REPO=1
            REPO_OVERRIDE="${1#--repo=}"
            ARGS+=("$1")
            shift
            ;;
        --resume-from)
            HAS_RESUME_FROM=1
            ARGS+=("$1")
            shift
            if [ $# -gt 0 ]; then
                RESUME_FROM_VALUE="$1"
                ARGS+=("$1")
                shift
            fi
            ;;
        --resume-from=*)
            HAS_RESUME_FROM=1
            RESUME_FROM_VALUE="${1#--resume-from=}"
            ARGS+=("$1")
            shift
            ;;
        --include-install)
            HAS_INCLUDE_INSTALL=1
            INCLUDE_INSTALL=1
            ARGS+=("$1")
            shift
            ;;
        --require-client-analyzer)
            HAS_REQUIRE_CLIENT_ANALYZER=1
            REQUIRE_CLIENT_ANALYZER=1
            ARGS+=("$1")
            shift
            ;;
        --client-analyzer-dir)
            HAS_CLIENT_ANALYZER_DIR=1
            ARGS+=("$1")
            shift
            if [ $# -gt 0 ]; then
                CLIENT_ANALYZER_DIR_VALUE="$1"
                ARGS+=("$1")
                shift
            fi
            ;;
        --client-analyzer-dir=*)
            HAS_CLIENT_ANALYZER_DIR=1
            CLIENT_ANALYZER_DIR_VALUE="${1#--client-analyzer-dir=}"
            ARGS+=("$1")
            shift
            ;;
        --client-analyzer-mode)
            HAS_CLIENT_ANALYZER_MODE=1
            ARGS+=("$1")
            shift
            if [ $# -gt 0 ]; then
                CLIENT_ANALYZER_MODE_VALUE="$1"
                ARGS+=("$1")
                shift
            fi
            ;;
        --client-analyzer-mode=*)
            HAS_CLIENT_ANALYZER_MODE=1
            CLIENT_ANALYZER_MODE_VALUE="${1#--client-analyzer-mode=}"
            ARGS+=("$1")
            shift
            ;;
        --av-exclusions-mode)
            HAS_AV_EXCLUSIONS_MODE=1
            ARGS+=("$1")
            shift
            if [ $# -gt 0 ]; then
                AV_EXCLUSIONS_MODE_VALUE="$1"
                ARGS+=("$1")
                shift
            fi
            ;;
        --av-exclusions-mode=*)
            HAS_AV_EXCLUSIONS_MODE=1
            AV_EXCLUSIONS_MODE_VALUE="${1#--av-exclusions-mode=}"
            ARGS+=("$1")
            shift
            ;;
        --require-ghcp-cli)
            HAS_REQUIRE_GHCP_CLI=1
            REQUIRE_GHCP_CLI=1
            ARGS+=("$1")
            shift
            ;;
        --hot-events-analysis)
            HAS_HOT_EVENTS_ANALYSIS=1
            ARGS+=("$1")
            shift
            if [ $# -gt 0 ]; then
                HOT_EVENTS_ANALYSIS_VALUE="$1"
                ARGS+=("$1")
                shift
            fi
            ;;
        --hot-events-analysis=*)
            HAS_HOT_EVENTS_ANALYSIS=1
            HOT_EVENTS_ANALYSIS_VALUE="${1#--hot-events-analysis=}"
            ARGS+=("$1")
            shift
            ;;
        --profile-change-policy)
            HAS_PROFILE_CHANGE_POLICY=1
            ARGS+=("$1")
            shift
            if [ $# -gt 0 ]; then
                PROFILE_CHANGE_POLICY_VALUE="$1"
                ARGS+=("$1")
                shift
            fi
            ;;
        --profile-change-policy=*)
            HAS_PROFILE_CHANGE_POLICY=1
            PROFILE_CHANGE_POLICY_VALUE="${1#--profile-change-policy=}"
            ARGS+=("$1")
            shift
            ;;
        --*)
            if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
                HAS_HELP=1
            fi
            ARGS+=("$1")
            shift
            ;;
        *)
            POSITIONAL_ARGS+=("$1")
            shift
            ;;
    esac
done

if [ ${#POSITIONAL_ARGS[@]} -gt 0 ]; then
    SCENARIO_VALUE="${POSITIONAL_ARGS[0]}"
    HAS_SCENARIO=1
    if [ ${#ARGS[@]} -gt 0 ]; then
        ARGS=("${POSITIONAL_ARGS[0]}" "${ARGS[@]}")
    else
        ARGS=("${POSITIONAL_ARGS[0]}")
    fi
fi

if [ "$HAS_HELP" -eq 1 ]; then
    PREP_SUDO=0
fi

prompt_yes_no() {
    local prompt_text="$1"
    local default_value="$2"
    local reply=""

    if [ "$INTERACTIVE" -ne 1 ]; then
        [ "$default_value" = "y" ] && return 0
        return 1
    fi

    while true; do
        if [ "$default_value" = "y" ]; then
            read -r -p "$prompt_text [Y/n]: " reply
            reply="${reply:-y}"
        else
            read -r -p "$prompt_text [y/N]: " reply
            reply="${reply:-n}"
        fi

        case "$(printf '%s' "$reply" | tr '[:upper:]' '[:lower:]')" in
            y|yes) return 0 ;;
            n|no) return 1 ;;
            *) echo "Please answer y or n." ;;
        esac
    done
}

prompt_choice() {
    local prompt_text="$1"
    local default_value="$2"
    local allowed_csv="$3"
    local reply=""

    if [ "$INTERACTIVE" -ne 1 ]; then
        printf '%s' "$default_value"
        return 0
    fi

    while true; do
        read -r -p "$prompt_text [$allowed_csv] (default: $default_value): " reply
        reply="${reply:-$default_value}"
        reply_lower="$(printf '%s' "$reply" | tr '[:upper:]' '[:lower:]')"
        case "$reply_lower" in
            auto|on|off|prompt|python|ghcp|both|always|never)
                printf '%s' "$reply_lower"
                return 0
                ;;
            *)
                echo "Please enter one of: $allowed_csv"
                ;;
        esac
    done
}

yn_text() {
    if [ "$1" -eq 1 ]; then
        printf '%s' "on"
    else
        printf '%s' "off"
    fi
}

lock_text() {
    if [ "$1" -eq 1 ]; then
        printf '%s' " [locked via CLI]"
    else
        printf '%s' ""
    fi
}

if ! command -v python3 >/dev/null 2>&1; then
    echo "❌ python3 not found in PATH."
    echo "   Install Python 3 and re-run this script."
    echo "   macOS option: brew install python"
    exit 1
fi

if [ ! -f "$PY_ENTRY" ]; then
    echo "❌ Missing Python entrypoint: $PY_ENTRY"
    exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "🐍 Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# Install or refresh dependencies when requirements changed.
if [ ! -f "$BOOTSTRAP_STAMP" ] || [ "$REQ_FILE" -nt "$BOOTSTRAP_STAMP" ]; then
    echo "📦 Installing Python dependencies..."
    python3 -m pip install --upgrade pip >/dev/null
    python3 -m pip install -r "$REQ_FILE"
    date +%s > "$BOOTSTRAP_STAMP"
fi

if [ "$PREP_SUDO" -eq 1 ] && command -v sudo >/dev/null 2>&1; then
    echo "🔐 Caching sudo credentials (one prompt max)..."
    if sudo -v; then
        (
            while true; do
                sudo -n true >/dev/null 2>&1 || exit
                sleep 60
            done
        ) &
        SUDO_KEEPALIVE_PID=$!
    else
        echo "⚠️  Could not cache sudo credentials now."
        echo "   Demo can continue, but privileged steps may prompt later."
    fi
fi

if [ "$HAS_SCENARIO" -eq 0 ]; then
    SCENARIO_VALUE="vscode"
fi

if [ "$HAS_HELP" -eq 0 ] && [ "$INTERACTIVE" -eq 1 ]; then
    while true; do
        echo ""
        echo "⚙️  Demo defaults (select one to change, Enter to run):"
        echo "  1) Scenario: $SCENARIO_VALUE$(lock_text "$HAS_SCENARIO")"
        echo "  2) Repo path override: ${REPO_OVERRIDE:-'(default)'}$(lock_text "$HAS_REPO")"
        echo "  3) Resume from phase: ${RESUME_FROM_VALUE:-'(none)'}$(lock_text "$HAS_RESUME_FROM")"
        echo "  4) Include install in timed build: $(yn_text "$INCLUDE_INSTALL")$(lock_text "$HAS_INCLUDE_INSTALL")"
        echo "  5) Require Client Analyzer: $(yn_text "$REQUIRE_CLIENT_ANALYZER")$(lock_text "$HAS_REQUIRE_CLIENT_ANALYZER")"
        echo "  6) Client Analyzer dir: ${CLIENT_ANALYZER_DIR_VALUE:-'(default)'}$(lock_text "$HAS_CLIENT_ANALYZER_DIR")"
        echo "  7) Client Analyzer mode: $CLIENT_ANALYZER_MODE_VALUE$(lock_text "$HAS_CLIENT_ANALYZER_MODE")"
        echo "  8) AV exclusions mode: $AV_EXCLUSIONS_MODE_VALUE$(lock_text "$HAS_AV_EXCLUSIONS_MODE")"
        echo "  9) Require GH Copilot CLI: $(yn_text "$REQUIRE_GHCP_CLI")$(lock_text "$HAS_REQUIRE_GHCP_CLI")"
        echo " 10) Hot events analysis: $HOT_EVENTS_ANALYSIS_VALUE$(lock_text "$HAS_HOT_EVENTS_ANALYSIS")"
        echo " 11) Profile change policy: $PROFILE_CHANGE_POLICY_VALUE$(lock_text "$HAS_PROFILE_CHANGE_POLICY")"
        read -r -p "Choose [1-11], R=run, Q=quit (default: R): " menu_choice
        menu_choice="$(printf '%s' "${menu_choice:-r}" | tr '[:upper:]' '[:lower:]')"

        case "$menu_choice" in
            ""|r|run)
                break
                ;;
            q|quit)
                exit 130
                ;;
            1)
                if [ "$HAS_SCENARIO" -eq 1 ]; then
                    echo "Scenario is locked via CLI."
                else
                    echo "Select a demo scenario:"
                    echo "  1) vscode"
                    echo "  2) xcode"
                    echo "  3) xcode-simulator"
                    echo "  4) android-studio"
                    read -r -p "Enter choice [1/2/3/4] (default: 1): " choice
                    case "${choice:-1}" in
                        2) SCENARIO_VALUE="xcode" ;;
                        3) SCENARIO_VALUE="xcode-simulator" ;;
                        4) SCENARIO_VALUE="android-studio" ;;
                        *) SCENARIO_VALUE="vscode" ;;
                    esac
                fi
                ;;
            2)
                if [ "$HAS_REPO" -eq 1 ]; then
                    echo "Repo path is locked via CLI."
                else
                    read -r -p "Repo path override (blank for default): " REPO_OVERRIDE
                fi
                ;;
            3)
                if [ "$HAS_RESUME_FROM" -eq 1 ]; then
                    echo "Resume phase is locked via CLI."
                else
                    read -r -p "Resume from phase index (blank for none): " RESUME_FROM_VALUE
                fi
                ;;
            4)
                if [ "$HAS_INCLUDE_INSTALL" -eq 1 ]; then
                    echo "Include install is locked via CLI."
                else
                    if [ "$SCENARIO_VALUE" != "vscode" ]; then
                        echo "Include install applies to vscode scenario only."
                    fi
                    if prompt_yes_no "Include npm install in timed build phases?" "$( [ "$INCLUDE_INSTALL" -eq 1 ] && echo y || echo n )"; then
                        INCLUDE_INSTALL=1
                    else
                        INCLUDE_INSTALL=0
                    fi
                fi
                ;;
            5)
                if [ "$HAS_REQUIRE_CLIENT_ANALYZER" -eq 1 ]; then
                    echo "Require Client Analyzer is locked via CLI."
                else
                    if prompt_yes_no "Require Client Analyzer in preflight?" "$( [ "$REQUIRE_CLIENT_ANALYZER" -eq 1 ] && echo y || echo n )"; then
                        REQUIRE_CLIENT_ANALYZER=1
                    else
                        REQUIRE_CLIENT_ANALYZER=0
                    fi
                fi
                ;;
            6)
                if [ "$HAS_CLIENT_ANALYZER_DIR" -eq 1 ]; then
                    echo "Client Analyzer dir is locked via CLI."
                else
                    read -r -p "Client Analyzer directory override (blank for default): " CLIENT_ANALYZER_DIR_VALUE
                fi
                ;;
            7)
                if [ "$HAS_CLIENT_ANALYZER_MODE" -eq 1 ]; then
                    echo "Client Analyzer mode is locked via CLI."
                else
                    CLIENT_ANALYZER_MODE_VALUE="$(prompt_choice "Client Analyzer mode" "$CLIENT_ANALYZER_MODE_VALUE" "auto/on/off")"
                fi
                ;;
            8)
                if [ "$HAS_AV_EXCLUSIONS_MODE" -eq 1 ]; then
                    echo "AV exclusions mode is locked via CLI."
                else
                    AV_EXCLUSIONS_MODE_VALUE="$(prompt_choice "Temporary AV exclusions mode" "$AV_EXCLUSIONS_MODE_VALUE" "auto/on/off")"
                fi
                ;;
            9)
                if [ "$HAS_REQUIRE_GHCP_CLI" -eq 1 ]; then
                    echo "Require GH Copilot CLI is locked via CLI."
                else
                    if prompt_yes_no "Require GH Copilot CLI in preflight?" "$( [ "$REQUIRE_GHCP_CLI" -eq 1 ] && echo y || echo n )"; then
                        REQUIRE_GHCP_CLI=1
                    else
                        REQUIRE_GHCP_CLI=0
                    fi
                fi
                ;;
            10)
                if [ "$HAS_HOT_EVENTS_ANALYSIS" -eq 1 ]; then
                    echo "Hot events analysis is locked via CLI."
                else
                    HOT_EVENTS_ANALYSIS_VALUE="$(prompt_choice "Hot events analysis mode" "$HOT_EVENTS_ANALYSIS_VALUE" "prompt/python/ghcp/both")"
                fi
                ;;
            11)
                if [ "$HAS_PROFILE_CHANGE_POLICY" -eq 1 ]; then
                    echo "Profile change policy is locked via CLI."
                else
                    PROFILE_CHANGE_POLICY_VALUE="$(prompt_choice "Profile change policy" "$PROFILE_CHANGE_POLICY_VALUE" "prompt/always/never")"
                fi
                ;;
            *)
                echo "Please choose 1-11, R, or Q."
                ;;
        esac
    done
fi

if [ "$HAS_HELP" -eq 0 ] && [ "$HAS_SCENARIO" -eq 0 ]; then
    if [ ${#ARGS[@]} -gt 0 ]; then
        ARGS=("$SCENARIO_VALUE" "${ARGS[@]}")
    else
        ARGS=("$SCENARIO_VALUE")
    fi
fi

if [ "$HAS_HELP" -eq 0 ] && [ "$HAS_REPO" -eq 0 ] && [ -n "${REPO_OVERRIDE:-}" ]; then
    ARGS+=("--repo" "$REPO_OVERRIDE")
fi

if [ "$HAS_HELP" -eq 0 ] && [ "$HAS_RESUME_FROM" -eq 0 ] && [ -n "${RESUME_FROM_VALUE:-}" ]; then
    ARGS+=("--resume-from" "$RESUME_FROM_VALUE")
fi

if [ "$HAS_HELP" -eq 0 ] && [ "$HAS_INCLUDE_INSTALL" -eq 0 ] && [ "$SCENARIO_VALUE" = "vscode" ] && [ "$INCLUDE_INSTALL" -eq 1 ]; then
    ARGS+=("--include-install")
fi

if [ "$HAS_HELP" -eq 0 ] && [ "$HAS_REQUIRE_CLIENT_ANALYZER" -eq 0 ] && [ "$REQUIRE_CLIENT_ANALYZER" -eq 1 ]; then
    ARGS+=("--require-client-analyzer")
fi

if [ "$HAS_HELP" -eq 0 ] && [ "$HAS_CLIENT_ANALYZER_DIR" -eq 0 ] && [ -n "${CLIENT_ANALYZER_DIR_VALUE:-}" ]; then
    ARGS+=("--client-analyzer-dir" "$CLIENT_ANALYZER_DIR_VALUE")
fi

if [ "$HAS_HELP" -eq 0 ] && [ "$HAS_CLIENT_ANALYZER_MODE" -eq 0 ]; then
    ARGS+=("--client-analyzer-mode" "$CLIENT_ANALYZER_MODE_VALUE")
fi

if [ "$HAS_HELP" -eq 0 ] && [ "$HAS_AV_EXCLUSIONS_MODE" -eq 0 ]; then
    ARGS+=("--av-exclusions-mode" "$AV_EXCLUSIONS_MODE_VALUE")
fi

if [ "$HAS_HELP" -eq 0 ] && [ "$HAS_REQUIRE_GHCP_CLI" -eq 0 ] && [ "$REQUIRE_GHCP_CLI" -eq 1 ]; then
    ARGS+=("--require-ghcp-cli")
fi

if [ "$HAS_HELP" -eq 0 ] && [ "$HAS_HOT_EVENTS_ANALYSIS" -eq 0 ] && [ "$SCENARIO_VALUE" = "vscode" ]; then
    ARGS+=("--hot-events-analysis" "$HOT_EVENTS_ANALYSIS_VALUE")
fi

if [ "$HAS_HELP" -eq 0 ] && [ "$HAS_PROFILE_CHANGE_POLICY" -eq 0 ]; then
    ARGS+=("--profile-change-policy" "$PROFILE_CHANGE_POLICY_VALUE")
fi

if [ ${#ARGS[@]} -gt 0 ]; then
    set -- "${ARGS[@]}"
else
    set --
fi

set +e
python3 "$PY_ENTRY" "$@"
PY_EXIT=$?
set -e

exit "$PY_EXIT"
