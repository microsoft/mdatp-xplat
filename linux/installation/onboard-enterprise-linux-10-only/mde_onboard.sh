#!/bin/bash

#============================================================================
# Minimal MDE onboarding script.
# Onboards an already-installed Microsoft Defender for Endpoint agent using
# the Python onboarding blob (MicrosoftDefenderATPOnboardingLinuxServer.py).
# Use this on distros not yet supported by mde_installer.sh (e.g. AlmaLinux 10,
# RHEL 10, etc) where mdatp is installed manually via the package manager.
#============================================================================

set -u

ERR_INTERNAL=1
ERR_INVALID_ARGUMENTS=3
ERR_ONBOARDING_NOT_FOUND=15
ERR_ONBOARDING_FAILED=16
ERR_FAILED_DEPENDENCY=21

ONBOARDING_SCRIPT=""
TAG_NAME=""
TAG_VALUE=""

log_info()  { echo "$1"; }
log_error() { echo "$1" >&2; }

script_exit()
{
    if [ "$2" -eq 0 ]; then
        log_info "$1"
    else
        log_error "$1"
    fi
    echo "[*] exiting ($2)"
    exit "$2"
}

usage()
{
    echo "Usage: $(basename "$0") --onboard <MicrosoftDefenderATPOnboardingLinuxServer.py>"
    echo
    echo "  -o|--onboard <script>     path to the Python onboarding blob"
    echo "  -t|--tag <name> <value>   set an EDR group tag after onboarding"
    echo "  -h|--help                 show this help"
}

verify_privileges()
{
    if [ "$(id -u)" -ne 0 ]; then
        script_exit "error: '$1' requires root privileges. Re-run with sudo." $ERR_INTERNAL
    fi
}

exit_if_mde_not_installed()
{
    if ! command -v mdatp >/dev/null 2>&1; then
        script_exit "error: mdatp is not installed. Install the package first." $ERR_FAILED_DEPENDENCY
    fi
}

check_if_device_is_onboarded()
{
    local licensed
    licensed=$(mdatp health --field licensed 2>/dev/null | tr -d '"')
    [ "$licensed" = "true" ]
}

onboard_device()
{
    exit_if_mde_not_installed

    if check_if_device_is_onboarded; then
        log_info "[i] MDE already onboarded"
        return
    fi

    if [ ! -f "$ONBOARDING_SCRIPT" ]; then
        script_exit "error: onboarding script not found." $ERR_ONBOARDING_NOT_FOUND
    fi

    if [[ "$ONBOARDING_SCRIPT" != *.py ]]; then
        script_exit "error: expected a Python (.py) onboarding script." $ERR_INVALID_ARGUMENTS
    fi

    PYTHON=$(which python 2>/dev/null || which python3 2>/dev/null)
    if [ -z "$PYTHON" ]; then
        script_exit "error: could not locate python." $ERR_FAILED_DEPENDENCY
    fi

    # Remove stale offboarding blob if present
    mdatp_offboard_file=/etc/opt/microsoft/mdatp/mdatp_offboard.json
    if [ -f "$mdatp_offboard_file" ]; then
        rm -f "$mdatp_offboard_file" || \
            script_exit "error: failed to remove offboarding blob" $ERR_ONBOARDING_FAILED
    fi

    log_info "[i] Running onboarding script with $PYTHON ..."
    if ! "$PYTHON" "$ONBOARDING_SCRIPT"; then
        script_exit "error: python onboarding failed" $ERR_ONBOARDING_FAILED
    fi

    # Validate onboarding (wait up to ~80s for licensing to flip)
    local license_found=false
    for ((i = 1; i <= 8; i++)); do
        sleep 10
        if check_if_device_is_onboarded; then
            license_found=true
            break
        fi
    done

    if [ "$license_found" = "false" ]; then
        script_exit "onboarding failed" $ERR_ONBOARDING_FAILED
    fi

    log_info "[v] Onboarded"
}

set_device_tags()
{
    [ -z "$TAG_NAME" ] && return
    log_info "[i] Setting tag $TAG_NAME=$TAG_VALUE ..."
    if ! mdatp edr tag set --name "$TAG_NAME" --value "$TAG_VALUE"; then
        script_exit "error: failed to set tag $TAG_NAME" $ERR_INTERNAL
    fi
    log_info "[v] Tag set: $TAG_NAME=$TAG_VALUE"
}

if [ $# -eq 0 ]; then
    usage
    exit $ERR_INVALID_ARGUMENTS
fi

while [ $# -ne 0 ]; do
    case "$1" in
        -o|--onboard)
            if [ -z "${2:-}" ]; then
                script_exit "error: --onboard requires a path argument." $ERR_INVALID_ARGUMENTS
            fi
            ONBOARDING_SCRIPT="$2"
            shift 2
            ;;
        -t|--tag)
            if [ -z "${2:-}" ] || [ -z "${3:-}" ]; then
                script_exit "error: --tag requires <name> <value> arguments." $ERR_INVALID_ARGUMENTS
            fi
            TAG_NAME="$2"
            TAG_VALUE="$3"
            shift 3
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            script_exit "error: unknown argument '$1'" $ERR_INVALID_ARGUMENTS
            ;;
    esac
done

verify_privileges "onboard"
onboard_device
set_device_tags
