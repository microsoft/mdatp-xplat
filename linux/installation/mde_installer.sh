#!/bin/bash
#
# shellcheck disable=SC1091
# SC1091: Don't follow sourced files (os-release may not exist during linting)

#============================================================================
#
#  Copyright (c) 2021 Microsoft Corporation.  All rights reserved.
#
#  Abstract:
#    MDE installation script
#    - Fingerprinting OS and manually installs MDE as described in the online documentation
#      https://learn.microsoft.com/en-us/defender-endpoint/linux-install-manually?view=o365-worldwide
#    - Runs additional optional checks: minimal requirements, fanotify subscribers, etc.
#
#============================================================================

# Strict mode: exit on error, undefined variable, and pipeline failures
set -euo pipefail

# Read version from central VERSION file if it exists, otherwise use fallback
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." 2>/dev/null && pwd)" || REPO_ROOT=""
if [[ -n "${REPO_ROOT}" ]] && [[ -f "${REPO_ROOT}/VERSION" ]]; then
    SCRIPT_VERSION=$(tr -d '[:space:]' < "${REPO_ROOT}/VERSION")
else
    SCRIPT_VERSION="1.2.0"  # Fallback version
fi
ASSUMEYES=-y
CHANNEL=
MDE_VERSION=
DISTRO=
DISTRO_FAMILY=
ARCHITECTURE=
PKG_MGR=
INSTALL_MODE=
DEBUG=0
VERBOSE=
PMC_URL=https://packages.microsoft.com/config
SCALED_VERSION=
VERSION=
ONBOARDING_SCRIPT=
OFFBOARDING_SCRIPT=
MIN_REQUIREMENTS=
SKIP_CONFLICTING_APPS=
PASSIVE_MODE=
RTP_MODE=
MIN_CORES=1
MIN_MEM_MB=1024
MIN_DISK_SPACE_MB=2048
declare -A tags

# Error codes
SUCCESS=0
ERR_INTERNAL=1
ERR_INVALID_ARGUMENTS=2
ERR_INSUFFICIENT_PRIVILAGES=3
ERR_CONFLICTING_APPS=5
ERR_UNSUPPORTED_DISTRO=10
ERR_UNSUPPORTED_VERSION=11
ERR_INSUFFICIENT_REQUIREMENTS=12
ERR_CORRUPT_MDE_INSTALLED=15
ERR_MDE_NOT_INSTALLED=20
ERR_INSTALLATION_FAILED=21
ERR_UNINSTALLATION_FAILED=22
ERR_FAILED_DEPENDENCY=23
ERR_FAILED_REPO_SETUP=24
ERR_INVALID_CHANNEL=25
ERR_FAILED_REPO_CLEANUP=26
ERR_ONBOARDING_NOT_FOUND=30
ERR_ONBOARDING_FAILED=31
ERR_OFFBOARDING_NOT_FOUND=32
ERR_OFFBOARDING_FAILED=33
ERR_TAG_NOT_SUPPORTED=40
ERR_PARAMETER_SET_FAILED=41
ERR_INSTALL_PATH_SETUP=51
ERR_INSTALL_PATH_PERMISSIONS=52

# Predefined values
export DEBIAN_FRONTEND=noninteractive

# Trap for cleanup on exit
trap 'cleanup_on_exit' EXIT

cleanup_on_exit() {
    # Cleanup temporary files created by the script
    if [[ -n "${TEMP_FILES_TO_CLEANUP:-}" ]]; then
        for temp_file in ${TEMP_FILES_TO_CLEANUP}; do
            rm -f "$temp_file" 2>/dev/null || true
        done
    fi
}

# Secure temporary file creation
# Usage: temp_file=$(create_secure_temp_file)
create_secure_temp_file() {
    local temp_file
    temp_file=$(mktemp -t "mde_installer.XXXXXX") || {
        log_error "[!] Failed to create secure temporary file"
        return 1
    }
    # Track for cleanup
    TEMP_FILES_TO_CLEANUP="${TEMP_FILES_TO_CLEANUP:-} $temp_file"
    echo "$temp_file"
}

# Set secure permissions on a file
# Usage: set_secure_permissions <file_path> [mode]
set_secure_permissions() {
    local file_path="$1"
    local mode="${2:-0660}"

    if [[ ! -f "$file_path" ]]; then
        log_error "[!] Cannot set permissions: file does not exist: $file_path"
        return 1
    fi

    # Check if mdatp group exists
    if getent group mdatp >/dev/null 2>&1; then
        if ! chown root:mdatp "$file_path" 2>/dev/null; then
            log_warning "[!] Failed to chown $file_path to root:mdatp, falling back to root:root"
            chown root:root "$file_path" || return 1
        fi
    else
        chown root:root "$file_path" || {
            log_error "[!] Failed to chown $file_path"
            return 1
        }
    fi

    chmod "$mode" "$file_path" || {
        log_error "[!] Failed to chmod $file_path to $mode"
        return 1
    }

    [[ "$DEBUG" != "0" ]] && log_debug "[v] Set permissions on $file_path: mode=$mode"
    return 0
}

# Atomic file copy - copies to temp then moves
# Usage: atomic_copy <source> <destination>
atomic_copy() {
    local src="$1"
    local dest="$2"
    local temp_dest

    # Create temp file in same directory as destination for atomic move
    temp_dest=$(mktemp "${dest}.XXXXXX") || {
        log_error "[!] Failed to create temp file for atomic copy"
        return 1
    }

    # Copy to temp file
    if ! cp "$src" "$temp_dest" 2>/dev/null; then
        rm -f "$temp_dest" 2>/dev/null
        log_error "[!] Failed to copy $src to temp file"
        return 1
    fi

    # Atomic move
    if ! mv "$temp_dest" "$dest" 2>/dev/null; then
        rm -f "$temp_dest" 2>/dev/null
        log_error "[!] Failed to atomic move to $dest"
        return 1
    fi

    return 0
}

_log() {
    level="$1"
    dest="$2"
    msg="${*:3}"
    ts=$(date -u +"%Y-%m-%dT%H:%M:%S")

    if [[ "$dest" == "stdout" ]]; then
       echo "$msg"
    elif [[ "$dest" == "stderr" ]]; then
       >&2 echo "$msg"
    fi

    if [[ -n "$log_path" ]]; then
       echo "$ts $level $msg" >> "$log_path"
    fi
}

log_debug() {
    _log "DEBUG" "stdout" "$@"
}

log_info() {
    _log "INFO " "stdout" "$@"
}

log_warning() {
    _log "WARN " "stderr" "$@"
}

log_error() {
    _log "ERROR" "stderr" "$@"
}

script_exit()
{
    local message="$1"
    local exit_code="${2:-$ERR_INTERNAL}"
    
    if [[ -z "$message" ]]; then
        log_error "[!] INTERNAL ERROR. script_exit requires a message argument"
        exit $ERR_INTERNAL
    fi

    if [[ "$DEBUG" != "0" ]]; then
        print_state
    fi

    # Validate exit code is a number
    if ! [[ "$exit_code" =~ ^[0-9]+$ ]]; then
        log_error "[!] INTERNAL ERROR. Invalid exit code: $exit_code"
        exit $ERR_INTERNAL
    fi

    # REL-003: Clear distinction between success and failure messages
    if [[ "$exit_code" == "0" ]]; then
        log_info "[SUCCESS] $message"
        log_info "[*] Script completed successfully (exit code: 0)"
    else
        log_error "[FAILED] $message"
        log_error "[*] Script failed with exit code: $exit_code"
        # Provide hint for common error codes
        case "$exit_code" in
            "$ERR_INVALID_ARGUMENTS")
                log_error "[*] Hint: Check command line arguments. Use --help for usage."
                ;;
            "$ERR_INSUFFICIENT_PRIVILAGES")
                log_error "[*] Hint: This operation requires root privileges. Try running with sudo."
                ;;
            "$ERR_FAILED_REPO_SETUP")
                log_error "[*] Hint: Repository setup failed. Check network connectivity and proxy settings."
                ;;
            "$ERR_INSTALLATION_FAILED")
                log_error "[*] Hint: Installation failed. Check system requirements and disk space."
                ;;
        esac
    fi

    cleanup "$exit_code"
    exit "$exit_code"
}

# =============================================================================
# Input Validation Functions (SEC-002)
# =============================================================================

# Validate that a path is safe (no path traversal, valid characters)
validate_path() {
    local path="$1"
    local path_type="$2"  # "file" or "directory"
    
    # Check for empty path
    if [[ -z "$path" ]]; then
        log_error "[!] Empty path provided"
        return 1
    fi
    
    # Check for null bytes (command injection attempt)
    if [[ "$path" == *$'\0'* ]]; then
        log_error "[!] Invalid path: contains null bytes"
        return 1
    fi
    
    # Check for path traversal attempts
    if [[ "$path" == *".."* ]]; then
        log_error "[!] Invalid path: path traversal detected"
        return 1
    fi
    
    # Check for shell metacharacters that could enable injection
    if [[ "$path" =~ [\;\|\&\$\`\(\)\{\}\<\>\!] ]]; then
        log_error "[!] Invalid path: contains shell metacharacters"
        return 1
    fi
    
    # Resolve to absolute path and verify it's valid
    local resolved_path
    if ! resolved_path=$(realpath -m "$path" 2>/dev/null); then
        log_error "[!] Invalid path: cannot resolve"
        return 1
    fi
    
    echo "$resolved_path"
    return 0
}

# Validate onboarding/offboarding script path
validate_script_path() {
    local script_path="$1"
    local script_type="$2"  # "onboarding" or "offboarding"
    
    # Basic path validation
    local validated_path
    if ! validated_path=$(validate_path "$script_path" "file"); then
        return 1
    fi
    
    # Check file exists
    if [[ ! -f "$validated_path" ]]; then
        log_error "[!] $script_type script not found: $validated_path"
        return 1
    fi
    
    # Check file is readable
    if [[ ! -r "$validated_path" ]]; then
        log_error "[!] $script_type script not readable: $validated_path"
        return 1
    fi
    
    # Validate file extension
    local extension="${validated_path##*.}"
    case "$extension" in
        py|sh|json)
            ;;
        *)
            log_error "[!] Invalid $script_type script extension: .$extension (expected .py, .sh, or .json)"
            return 1
            ;;
    esac
    
    echo "$validated_path"
    return 0
}

# Validate installation directory path
validate_install_path() {
    local install_path="$1"
    
    # Basic path validation
    local validated_path
    if ! validated_path=$(validate_path "$install_path" "directory"); then
        return 1
    fi
    
    # Restrict to allowed parent directories
    local allowed_prefixes=("/opt" "/usr/local" "/home")
    local is_allowed=false
    
    for prefix in "${allowed_prefixes[@]}"; do
        if [[ "$validated_path" == "$prefix"* ]]; then
            is_allowed=true
            break
        fi
    done
    
    if [[ "$is_allowed" != "true" ]]; then
        log_error "[!] Installation path must be under /opt, /usr/local, or /home"
        return 1
    fi
    
    # Prevent installation to sensitive system directories
    local blocked_paths=("/opt/microsoft/mdatp" "/usr" "/bin" "/sbin" "/lib" "/etc")
    for blocked in "${blocked_paths[@]}"; do
        if [[ "$validated_path" == "$blocked" ]]; then
            log_error "[!] Cannot install to system directory: $validated_path"
            return 1
        fi
    done
    
    echo "$validated_path"
    return 0
}

# =============================================================================
# GPG Key Verification Functions (SEC-007)
# =============================================================================

# Microsoft GPG key fingerprints (official)
MICROSOFT_GPG_FINGERPRINT="BC52 8686 B50D 79E3 39D3  721C EB3E 94AD BE12 29CF"
MICROSOFT_2025_GPG_FINGERPRINT="BC52 8686 B50D 79E3 39D3  721C EB3E 94AD BE12 29CF"

# Verify GPG key fingerprint
verify_gpg_key_fingerprint() {
    local key_file="$1"
    local expected_fingerprint="$2"
    
    if [[ ! -f "$key_file" ]]; then
        log_error "[!] GPG key file not found: $key_file"
        return 1
    fi
    
    # Extract fingerprint from key file
    local actual_fingerprint
    actual_fingerprint=$(gpg --show-keys --fingerprint "$key_file" 2>/dev/null | grep -A1 "pub" | tail -1 | tr -d ' ' | tr '[:lower:]' '[:upper:]')
    local expected_clean
    expected_clean=$(echo "$expected_fingerprint" | tr -d ' ' | tr '[:lower:]' '[:upper:]')
    
    if [[ -z "$actual_fingerprint" ]]; then
        log_error "[!] Could not extract fingerprint from GPG key"
        return 1
    fi
    
    if [[ "$actual_fingerprint" != "$expected_clean" ]]; then
        log_error "[!] GPG key fingerprint mismatch!"
        log_error "[!] Expected: $expected_fingerprint"
        log_error "[!] Got: $actual_fingerprint"
        return 1
    fi
    
    log_info "[v] GPG key fingerprint verified successfully"
    return 0
}

# Download and verify GPG key with fingerprint check
download_and_verify_gpg_key() {
    local key_url="$1"
    local output_file="$2"
    local expected_fingerprint="$3"
    
    local temp_key
    temp_key=$(create_secure_temp_file) || return 1
    
    # Download the key
    if ! curl -fsSL "$key_url" -o "$temp_key" 2>/dev/null; then
        log_error "[!] Failed to download GPG key from $key_url"
        rm -f "$temp_key"
        return 1
    fi
    
    # Verify the fingerprint before installing
    local temp_gpg
    temp_gpg=$(create_secure_temp_file) || { rm -f "$temp_key"; return 1; }
    
    if ! gpg --dearmor -o "$temp_gpg" < "$temp_key" 2>/dev/null; then
        log_error "[!] Failed to dearmor GPG key"
        rm -f "$temp_key" "$temp_gpg"
        return 1
    fi
    
    # Verify fingerprint
    if ! verify_gpg_key_fingerprint "$temp_gpg" "$expected_fingerprint"; then
        log_error "[!] GPG key verification failed - possible man-in-the-middle attack!"
        rm -f "$temp_key" "$temp_gpg"
        return 1
    fi
    
    # Move verified key to final location
    if ! mv "$temp_gpg" "$output_file"; then
        log_error "[!] Failed to install GPG key to $output_file"
        rm -f "$temp_key" "$temp_gpg"
        return 1
    fi
    
    rm -f "$temp_key"
    chmod o+r "$output_file" 2>/dev/null || true
    
    log_info "[v] GPG key downloaded and verified: $output_file"
    return 0
}

# =============================================================================
# Timeout Handling Functions (REL-006)
# =============================================================================

# Run a command with timeout and proper cleanup
run_with_timeout() {
    local timeout_seconds="$1"
    local error_msg="$2"
    local error_code="$3"
    shift 3
    local cmd=("$@")
    
    local pid
    local result
    
    # Start command in background
    "${cmd[@]}" &
    pid=$!
    
    # Wait with timeout
    local count=0
    while kill -0 "$pid" 2>/dev/null; do
        if [[ $count -ge $timeout_seconds ]]; then
            log_warning "[!] Command timed out after ${timeout_seconds}s, killing process..."
            kill -TERM "$pid" 2>/dev/null
            sleep 2
            kill -KILL "$pid" 2>/dev/null
            wait "$pid" 2>/dev/null
            log_error "[!] $error_msg (timeout)"
            return "$error_code"
        fi
        sleep 1
        ((count++))
    done
    
    wait "$pid"
    result=$?
    
    if [[ $result -ne 0 ]]; then
        log_error "[!] $error_msg (exit code: $result)"
        return "$error_code"
    fi
    
    return 0
}

get_python() {
   if command -v python3 &> /dev/null; then
      echo "python3"
   elif command -v python2 &> /dev/null; then
      echo "python2"
   elif command -v python &> /dev/null; then
      echo "python"
   else
      log_error "[!] No Python interpreter found"
      return 1
   fi
}


parse_uri() {
   cat <<EOF | /usr/bin/env "$(get_python)"
import sys

if sys.version_info < (3,):
   from urlparse import urlparse
else:
   from urllib.parse import urlparse

uri = urlparse("$1")
print(uri.scheme or "")
print(uri.hostname or "")
print(uri.port or "")
EOF
}

get_rpm_proxy_params() {
    proxy_params=""
    if [[ -n "$http_proxy" ]]; then
	    proxy_host=$(parse_uri "$http_proxy" | sed -n '2p')
        if [[ -n "$proxy_host" ]]; then
           proxy_params="$proxy_params --httpproxy $proxy_host"
        fi

	    proxy_port=$(parse_uri "$http_proxy" | sed -n '3p')
        if [[ -n "$proxy_port" ]]; then
           proxy_params="$proxy_params --httpport $proxy_port"
        fi
    fi
    if [[ -n "$ftp_proxy" ]]; then
       proxy_host=$(parse_uri "$ftp_proxy" | sed -n '2p')
       if [[ -n "$proxy_host" ]]; then
          proxy_params="$proxy_params --ftpproxy $proxy_host"
       fi

       proxy_port=$(parse_uri "$ftp_proxy" | sed -n '3p')
       if [[ -n "$proxy_port" ]]; then
          proxy_params="$proxy_params --ftpport $proxy_port"
       fi
    fi
    echo "$proxy_params"
}

cleanup()
{
    # If installation failed in case of custom installation, delete symlink
    if [[ "$1" == "$ERR_INSTALLATION_FAILED" ]] && [[ -n "$INSTALL_PATH" ]]; then
        local mdatp_symlink="/opt/microsoft/mdatp"
        delete_sym_link "$mdatp_symlink"
    fi
}

run_quietly()
{
    # run_quietly <command> <error_msg> [<error_code>]
    # use error_code for script_exit
    #
    # SECURITY NOTE: This function executes shell commands. The command string
    # should only contain trusted, script-controlled content - never user input.

    if [[ $# -lt 2 ]] || [[ $# -gt 3 ]]; then
        log_error "[!] INTERNAL ERROR. run_quietly requires 2 or 3 arguments"
        exit 1
    fi

    local out exit_code
    local cmd="$1"

    if [[ "$DEBUG" != "0" ]]; then
        log_debug "[>] Running command: $cmd"
    fi

    # Use bash -c instead of eval for slightly better isolation
    # Note: Still requires trusted input - do not pass user-controlled data
    if out=$(bash -c "$cmd" 2>&1); then
        exit_code=0
    else
        exit_code=$?
    fi

    if [[ -n "$VERBOSE" ]]; then
        log_info "$out"
    fi

    if [[ "$exit_code" != "0" ]]; then
        if [[ "$DEBUG" != "0" ]]; then
            log_debug "[>] Command output: $out"
            log_debug "[>] Command exit_code: $exit_code"
        fi

        if [[ $# -eq 2 ]]; then
            log_error "$2"
        else
            script_exit "$2" "$3"
        fi
    fi

    return "$exit_code"
}

retry_quietly()
{
    # retry_quietly <retries> <command> <error_msg> [<error_code>]
    # use error_code for script_exit
    
    if [[ $# -lt 3 ]] || [[ $# -gt 4 ]]; then
        log_error "[!] INTERNAL ERROR. retry_quietly requires 3 or 4 arguments"
        exit 1
    fi

    local exit_code=
    local retries=$1

    while [[ $retries -gt 0 ]]
    do

        if run_quietly "$2" "$3"; then
            exit_code=0
        else
            exit_code=1
        fi
        
        if [[ $exit_code -ne 0 ]]; then
            sleep 1
            ((retries--))
            log_info "[r] $(($1-$retries))/$1"
        else
            retries=0
        fi
    done

    if [[ $# -eq 4 ]] && [[ $exit_code -ne 0 ]]; then
        script_exit "$3" "$4"
    fi

    return $exit_code
}

get_health_field()
{
    # get_health_field <field>
    # get the health field from mdatp health --field <field>
    # extract the value from the output and return it

    if ! command -v mdatp >/dev/null 2>&1; then
        return 1
    fi

    local val
    val=$(mdatp health --field "$1" 2>/dev/null)
    cmd_status=$?
    if [[ $cmd_status -ne 0 ]]; then
        return 1
    fi
    clean_output=$(echo "$val" | sed '1{/^ATTENTION/d}' | sed 's/^"\(.*\)"$/\1/')
    echo "$clean_output"
    return 0
}

print_state()
{
    if ( ! check_if_pkg_is_installed mdatp ) && ( ! command -v mdatp >/dev/null 2>&1 ); then
        log_warning "[S] MDE not installed."
    else
        log_info "[S] MDE installed."
        if run_quietly "mdatp health" "[S] Could not connect to the daemon -- MDE is not ready to connect yet."; then
            log_info "[S] Version: $(get_health_field "app_version")"
            log_info "[S] Onboarded: $(get_health_field "licensed")"
            log_info "[S] Passive mode: $(get_health_field "passive_mode_enabled")"
            log_info "[S] Device tags: $(get_health_field "edr_device_tags")"
            log_info "[S] Subsystem: $(get_health_field "real_time_protection_subsystem")"
            log_info "[S] Conflicting applications: $(get_health_field "conflicting_applications")"
        fi
    fi
}

detect_arch()
{
    arch=$(uname -m)
    ARCHITECTURE=$arch
    log_info "[v] detected: $ARCHITECTURE architecture"
}

detect_distro()
{
    if [[ -f /etc/os-release ]]; then
        # shellcheck source=/dev/null
        . /etc/os-release
        DISTRO="${ID:-}"
        VERSION="${VERSION_ID:-}"
        VERSION_NAME="${VERSION_CODENAME:-}"
    elif [[ -f /etc/mariner-release ]]; then
        # shellcheck source=/dev/null
        . /etc/os-release
        DISTRO="${ID:-mariner}"
        VERSION="${VERSION_ID:-}"
        VERSION_NAME=""
    elif [[ -f /etc/redhat-release ]]; then
        if [[ -f /etc/oracle-release ]]; then
            DISTRO="ol"
        elif grep -qi "Red Hat" /etc/redhat-release 2>/dev/null; then
            DISTRO="rhel"
        elif grep -qi "CentOS" /etc/redhat-release 2>/dev/null; then
            DISTRO="centos"
        elif grep -qi "Rocky" /etc/redhat-release 2>/dev/null; then
            DISTRO="rocky"
        elif grep -qi "AlmaLinux" /etc/redhat-release 2>/dev/null; then
            DISTRO="almalinux"
        else
            DISTRO="rhel"
        fi
        VERSION=$(grep -o "release [0-9.]*" /etc/redhat-release | cut -d ' ' -f2)
    else
        script_exit "unable to detect distro" "$ERR_UNSUPPORTED_DISTRO"
    fi

    # Handle Ubuntu derivatives - map to Ubuntu
    case "$DISTRO" in
        linuxmint|pop|elementary|zorin|neon|kde-neon)
            # These are Ubuntu derivatives
            if [[ -n "${UBUNTU_CODENAME:-}" ]]; then
                VERSION_NAME="$UBUNTU_CODENAME"
            fi
            DISTRO="ubuntu"
            ;;
        kali|parrot)
            # These are Debian derivatives
            DISTRO="debian"
            ;;
    esac

    # Validate we got a valid distro
    if [[ -z "$DISTRO" ]]; then
        script_exit "unable to detect distro (empty ID)" "$ERR_UNSUPPORTED_DISTRO"
    fi

    # Set distro family
    case "$DISTRO" in
        debian|ubuntu)
            DISTRO_FAMILY="debian"
            ;;
        rhel|centos|ol|fedora|amzn|almalinux|rocky)
            DISTRO_FAMILY="fedora"
            ;;
        mariner)
            DISTRO_FAMILY="mariner"
            ;;
        azurelinux)
            DISTRO_FAMILY="azurelinux"
            ;;
        sles|sle-hpc|sles_sap|opensuse-leap|opensuse-tumbleweed)
            DISTRO_FAMILY="sles"
            ;;
        *)
            script_exit "unsupported distro $DISTRO $VERSION" "$ERR_UNSUPPORTED_DISTRO"
            ;;
    esac

    log_info "[v] detected: $DISTRO $VERSION ${VERSION_NAME:-} ($DISTRO_FAMILY)"
}

verify_channel()
{
    if [[ "$CHANNEL" != "prod" ]] && [[ "$CHANNEL" != "insiders-fast" ]] && [[ "$CHANNEL" != "insiders-slow" ]]; then
        script_exit "Invalid channel: $CHANNEL. Please provide valid channel. Available channels are prod, insiders-fast, insiders-slow" $ERR_INVALID_CHANNEL
    fi
}

verify_privileges()
{
    if [[ -z "$1" ]]; then
        script_exit "Internal error. verify_privileges require a parameter" $ERR_INTERNAL
    fi

    if [[ "$(id -u)" -ne 0 ]]; then
        script_exit "root privileges required to perform $1 operation" $ERR_INSUFFICIENT_PRIVILAGES
    fi
}

verify_min_requirements()
{
    # verifying minimal reuirements: $MIN_CORES cores, $MIN_MEM_MB MB RAM, $MIN_DISK_SPACE_MB MB disk space
    
    local cores mem_mb disk_space_mb

    cores=$(nproc --all)
    if [[ "$cores" -lt $MIN_CORES ]]; then
        script_exit "MDE requires $MIN_CORES cores or more to run, found $cores." $ERR_INSUFFICIENT_REQUIREMENTS
    fi

    mem_mb=$(free -m | grep Mem | awk '{print $2}')
    if [[ "$mem_mb" -lt $MIN_MEM_MB ]]; then
        script_exit "MDE requires at least $MIN_MEM_MB MB of RAM to run. found $mem_mb MB." $ERR_INSUFFICIENT_REQUIREMENTS
    fi

    disk_space_mb=$(df -m . | tail -1 | awk '{print $4}')
    if [[ "$disk_space_mb" -lt $MIN_DISK_SPACE_MB ]]; then
        script_exit "MDE requires at least $MIN_DISK_SPACE_MB MB of free disk space for installation. found $disk_space_mb MB." $ERR_INSUFFICIENT_REQUIREMENTS
    fi

    log_info "[v] minimal requirements met"
}

find_service()
{
    if [[ -z "$1" ]]; then
        script_exit "INTERNAL ERROR. find_service requires an argument" $ERR_INTERNAL
    fi

	lines=$(systemctl status $1 2>&1 | grep "Active: active" | wc -l)
	
    if [[ $lines -eq 0 ]]; then
		return 1
	fi

	return 0
}

verify_mdatp_installed()
{
    op=$(command -v mdatp)
            #make sure mdatp is installed
    if [[ -n "$op" ]]; then
        #check if mdatp is onboarded or not
        check_missing_license=$(get_health_field "health_issues" | grep "missing license" -c)
        onboard_file=/etc/opt/microsoft/mdatp/mdatp_onboard.json
        if [[ "$check_missing_license" -gt 0 ]] || [[ ! -f "$onboard_file" ]]; then
            log_info "[i] MDE already installed but not onboarded. Please use --onboard command to onboard the product."
        else
            current_mdatp_version=$(get_health_field "app_version")
            org_id=$(get_health_field "org_id")          
            if [[ -n "$MDE_VERSION" ]]; then
                local current_version requested_version
                current_version=$(echo "$current_mdatp_version" | sed 's/"//' | awk '{print $NF}' | awk -F. '{ printf("%d%05d%05d\n", $1,$2,$3); }')
                requested_version=$(echo "$MDE_VERSION" | awk -F. '{ printf("%d%05d%05d\n", $1,$2,$3); }')

                if [[ "$current_version" -lt "$requested_version" ]]; then
                    log_info "[i] Found MDE version $current_mdatp_version already installed and onboarded with org_id $org_id. To install newer version please use --upgrade option"
                elif [[ "$current_version" -gt "$requested_version" ]]; then
                    log_info "[i] Found MDE version $current_mdatp_version already installed and onboarded with org_id $org_id. To install older version please use --downgrade option"
                else
                    log_info "[i] The requested MDE version $current_mdatp_version already installed and onboarded with org_id $org_id."
                fi
            else
                log_info "[i] Found MDE already installed and onboarded with org_id $org_id and app_version $current_mdatp_version. Either try to upgrade/downgrade your MDE version using --upgrade/--downgrade option or Please verify that the onboarded linux server appears in Microsoft 365 Defender."
            fi
        fi
    else
        script_exit "Seems like, previous version of MDE is corrupted. Please, first try to uninstall the previous version of MDE using --remove option, aborting" $ERR_CORRUPT_MDE_INSTALLED
    fi
}

verify_conflicting_applications()
{
    # identifying conflicting applications (fanotify mounts)
    if ! command -v timeout >/dev/null 2>&1; then
        log_warning "[!] 'timeout' command not found. Skipping conflicting application check"
        return
    fi

    # find applications that are using fanotify
    local conflicting_apps
    conflicting_apps=$(timeout 5m find /proc/*/fdinfo/ -type f -print0 2>/dev/null \
        | xargs -r0 grep -Fl "fanotify mnt_id" 2>/dev/null \
        | xargs -I {} -r sh -c 'tr "\0" "" < "$(dirname {})/../cmdline"' 2>/dev/null)

    if [[ -n "$conflicting_apps" ]]; then
        if [[ "$conflicting_apps" == "/opt/microsoft/mdatp/sbin/wdavdaemon" ]]; then
            verify_mdatp_installed
        elif [[ "$conflicting_apps" =~ "fapolicyd" ]]; then
            # fapolicyd is supported with MDE in non-blocking mode
            log_warning "[!] [$conflicting_apps] is supported with MDE but for any run time conflicts, please check mdatp health output."
        else
            script_exit "found conflicting applications: [$conflicting_apps], aborting" $ERR_CONFLICTING_APPS
        fi

    fi

    # find known security services
    # | Vendor      | Service       |
    # |-------------|---------------|
    # | CrowdStrike | falcon-sensor | (removed in 0.8.2)
    # | CarbonBlack | cbsensor      |
    # | McAfee      | MFEcma        |
    # | Trend Micro | ds_agent      |

    local conflicting_services=('ds_agent' 'cbsensor' 'MFEcma')
    for t in "${conflicting_services[@]}"
    do
        set -- $t
        # locating service: $1
        if find_service $1; then
            script_exit "found conflicting service: [$1], aborting" $ERR_CONFLICTING_APPS
        fi        
    done 

    log_info "[v] no conflicting applications found"
}

set_package_manager()
{
    if [[ "$DISTRO_FAMILY" = "debian" ]]; then
        PKG_MGR=apt
        PKG_MGR_INVOKER="apt $ASSUMEYES"
    elif [[ "$DISTRO_FAMILY" = "fedora" ]]; then
        # Prefer dnf over yum on modern systems
        if command -v dnf &>/dev/null; then
            PKG_MGR=dnf
            PKG_MGR_INVOKER="dnf $ASSUMEYES"
        else
            PKG_MGR=yum
            PKG_MGR_INVOKER="yum $ASSUMEYES"
        fi
    elif [[ "$DISTRO_FAMILY" = "mariner" ]] || [[ "$DISTRO_FAMILY" = "azurelinux" ]]; then
        PKG_MGR=dnf
        PKG_MGR_INVOKER="dnf $ASSUMEYES"
    elif [[ "$DISTRO_FAMILY" = "sles" ]]; then
        DISTRO="sles"
        PKG_MGR="zypper"
        PKG_MGR_INVOKER="zypper --non-interactive"
    else
        script_exit "unsupported distro" "$ERR_UNSUPPORTED_DISTRO"
    fi

    log_info "[v] set package manager: $PKG_MGR"
}

check_if_pkg_is_installed()
{
    if [[ -z "$1" ]]; then
        script_exit "INTERNAL ERROR. check_if_pkg_is_installed requires an argument" "$ERR_INTERNAL"
    fi

    if [[ "$PKG_MGR" = "apt" ]]; then
        dpkg -s "$1" 2> /dev/null | grep Status | grep "install ok installed" 1> /dev/null
    else
        # shellcheck disable=SC2046
        rpm --quiet --query $(get_rpm_proxy_params) "$1"
    fi

    return $?
}

check_if_device_is_onboarded()
{
    local onboarded
    onboarded=$(get_health_field "licensed")
    if [[ "$onboarded" == "true" ]]; then
        return 0
    fi
    return 1
}

skip_if_mde_installed()
{
    if check_if_pkg_is_installed mdatp; then
        verify_mdatp_installed
        pkg_version=$(get_health_field "app_version") || script_exit "unable to fetch the app version. please upgrade to latest version $?" $ERR_INTERNAL
        log_info "[i] MDE already installed ($pkg_version)"
        return 0
    else
        return 1
    fi
}

exit_if_mde_not_installed()
{
    if ! check_if_pkg_is_installed mdatp; then
        script_exit "MDE package is not installed. Please install it with --install option" $ERR_MDE_NOT_INSTALLED
    fi
}

get_mdatp_version()
{
    local PKG_VERSION=""

    if [[ "$DISTRO_FAMILY" == "debian" ]]; then
        PKG_VERSION=$(dpkg -s mdatp | grep -i version)
    else
        PKG_VERSION=$(rpm -qi mdatp | grep -i version)
    fi

    echo "$PKG_VERSION"
}

get_mdatp_channel()
{
    local release_ring=""
    release_ring=$(mdatp health --field release_ring)
    if [[ "$?" == "0" ]] && [[ -n "$release_ring" ]]; then
        release_ring=$(echo "$release_ring" | tail -n 1 | awk -F'"' '{print $2}')
    else
        install_log=/var/log/microsoft/mdatp/install.log
        if [[ -e "$install_log" ]]; then
            release_ring=$(cat "$install_log" | grep "Release ring: " | tail -n 1 | awk -F': ' '{print $2}')
        fi
    fi

    local channel=""
    if [[ "$release_ring" == *"Production"* ]]; then
        channel="prod"
    elif [[ "$release_ring" == *"InsiderFast"* ]]; then
        channel="insiders-fast"
    elif [[ "$release_ring" == *"External"* ]]; then
        channel="insiders-slow"
    else
        channel="dogfood"
    fi

    echo "$channel"
}

install_required_pkgs()
{
    local packages=()
    local pkgs_to_be_installed=
    local exit_on_failure=1  # Default: exit on failure

    if [[ -z "$1" ]]; then
        script_exit "INTERNAL ERROR. install_required_pkgs requires an argument" $ERR_INTERNAL
    fi

    if [[ "$1" == "--no-exit" ]]; then
        exit_on_failure=0
        shift 1  # Remove the flag from arguments
    fi

    packages=("$@")
    for pkg in "${packages[@]}"
    do
        if  ! check_if_pkg_is_installed "$pkg"; then
            pkgs_to_be_installed="$pkgs_to_be_installed $pkg"
        fi
    done

    if [[ -n "$pkgs_to_be_installed" ]]; then
        log_info "[>] installing $pkgs_to_be_installed"

        if [[ "$exit_on_failure" -eq 1 ]]; then
            run_quietly "$PKG_MGR_INVOKER install $pkgs_to_be_installed" "Unable to install the required packages ($?)" $ERR_FAILED_DEPENDENCY
        else
            run_quietly "$PKG_MGR_INVOKER install $pkgs_to_be_installed" "Unable to install the required packages ($?)"
        fi
    else
        log_info "[v] required pkgs are installed"
    fi
}

wait_for_package_manager_to_complete()
{
    local lines=
    local counter=120

    while [[ $counter -gt 0 ]]
    do
        lines=$(ps axo pid,comm | grep "$PKG_MGR" | grep -v grep -c)
        if [[ "$lines" -eq 0 ]]; then
            log_info "[>] package manager freed, resuming installation"
            return
        fi
        sleep 1
        ((counter--))
    done

    log_info "[!] pkg_mgr blocked"
}

validate_mde_version()
{
    if ! [[ "$MDE_VERSION" =~ ^101\.[0-9]{1,5}\.[0-9]{4}$ ]]; then
        echo ""
        return 1
    fi

    local sep='_'
    local suffix='-1'
    local prefix='-'
    if [[ "$DISTRO_FAMILY" = "debian" ]]; then
        sep='-'
        suffix=''
        prefix='='
    fi
    local version
    if [[ "$CHANNEL" = "insiders-fast" ]]; then
        version="${MDE_VERSION}${sep}insiderfast${suffix}"
    elif [[ "$CHANNEL" = "insiders-slow" ]]; then
        version="${MDE_VERSION}${sep}external${suffix}"
    else
        version="$MDE_VERSION"
    fi

    local search_result=""

    # Version search logic - refactored to avoid eval
    if [[ "$PKG_MGR" = "apt" ]]; then
        if apt "${ASSUMEYES}" policy mdatp 2>/dev/null | grep -q "$version"; then
            search_result="found"
        fi
    elif [[ "$PKG_MGR" = "yum" ]]; then
        # Check if yum supports --showduplicates
        if yum --help 2>/dev/null | grep -q '\-\-showduplicates'; then
            if yum "${ASSUMEYES}" -v list mdatp --showduplicates 2>/dev/null | grep -q "$version"; then
                search_result="found"
            fi
        else
            # Older yum without --showduplicates, assume version exists
            search_result="found"
        fi
    elif [[ "$PKG_MGR" = "dnf" ]]; then
        if dnf "${ASSUMEYES}" search --showduplicates mdatp -y 2>/dev/null | grep -q "$version"; then
            search_result="found"
        fi
    elif [[ "$PKG_MGR" = "zypper" ]]; then
        if zypper search -s mdatp "${ASSUMEYES}" 2>/dev/null | grep -q "$version"; then
            search_result="found"
        fi
    fi

    if [[ -n "$search_result" ]]; then
        echo "${prefix}${version}"
    else
        echo ""
    fi
}

create_sym_link()
{
    local source_path="$1"
    local target_path="$2"

    if [[ ! -d "$target_path" ]]; then
        log_error "[x] Error: $target_path does not exist"
        return 1
    fi

    ## Check if source path's parent exists
    if [[ ! -d "$(dirname "$source_path")" ]]; then
        log_error "[x] Error: Parent directory of $source_path does not exist"
        return 2
    fi

    if [[ -L "$source_path" ]]; then
        log_debug "[i] Symlink already exists at $source_path"
        # Check if symlink is pointing to correct path
        if [[ "$(readlink -f "$source_path")" == "$target_path" ]]; then
            log_warning "[!] Warning: Symlink is already pointing to correct path"
            return 0
        else
            log_error "[x] Error: Symlink is not pointing to correct path"
            return 3
        fi
    fi

    if ! ln -sf "$target_path" "$source_path"; then
        log_error "[x] Error: Failed to create symlink at $target_path"
        return 4
    fi

    return 0
}

delete_sym_link()
{
    local source_path="$1"

    if [[ -L "$source_path" ]]; then
        if ! rm -f "$source_path"; then
            log_error "[!] Error: Failed to delete symlink $source_path"
            return 1
        fi
    fi

    return 0
}

validate_custom_path_installation_version()
{
    # Custom Path installation is available from version 101.25062.0003
    requested_version="$1"
    if [[ -n "$requested_version" ]] && [[ -n "$MDE_VERSION" ]]; then
        # Split version into major, minor, patch
        IFS='.' read -r major minor patch <<< "$MDE_VERSION"
        # Custom path install supported from 101.25062.0003
        if (( major < 101 )) || (( major == 101 && minor < 25062 )) || (( major == 101 && minor == 25062 && patch < 3 )); then
            return 1
        fi
    fi
    return 0
}

handle_custom_installation() 
{
    # Check that the directory exists and has the right access permission
    if [[ ! -d "$INSTALL_PATH" ]]; then
        log_info "[>] INSTALL_PATH=$INSTALL_PATH does not exist, creating it."
        mkdir -p "$INSTALL_PATH" || script_exit "Failed to create directory $INSTALL_PATH" $ERR_INSTALL_PATH_SETUP
    fi
    
    local installation_path="$INSTALL_PATH/microsoft_mdatp"
    mkdir -p "$installation_path" || script_exit "Failed to create directory $installation_path" $ERR_INSTALL_PATH_SETUP
    chmod 755 "$installation_path" || script_exit "Failed to set permissions on $installation_path" $ERR_INSTALL_PATH_PERMISSIONS
    local mde_config_dir="/etc/opt/microsoft/mdatp"
    local mde_config_path="$mde_config_dir/mde_path.json"
    mkdir -p "$mde_config_dir" || script_exit "Failed to create directory mde_config_dir" $ERR_INSTALL_PATH_SETUP

    # Create a JSON file to set the installation path
    echo "{\"path\": \"$installation_path\"}" > "$mde_config_path" || script_exit "Failed to write installation path to JSON file" $ERR_INSTALL_PATH_SETUP
    chmod 644 "$mde_config_path" || script_exit "Failed to set permissions for JSON file" $ERR_INSTALL_PATH_PERMISSIONS

    # Create a symlink to the installation path
    local src_path="/opt/microsoft/mdatp"
    local target_path="$installation_path/opt/microsoft/mdatp"
    mkdir -p "$(dirname "$src_path")" || script_exit "Failed to create directory for symlink source path" $ERR_INSTALL_PATH_SETUP
    mkdir -p "$target_path" || script_exit "Failed to create directory for symlink target path" $ERR_INSTALL_PATH_SETUP
    create_sym_link "$src_path" "$target_path" || script_exit "Failed to create symlink from $src_path to $target_path" $ERR_INSTALL_PATH_SETUP
}

install_on_debian()
{
    local packages=()
    local pkg_version=

    if [[ -z "$SKIP_PMC_SETUP" ]]; then 
        packages=(curl apt-transport-https gnupg)

        install_required_pkgs "${packages[@]}"

        ### Configure the repository ###
        log_info "[>] configuring the repository"

        rm -f microsoft.list > /dev/null
        run_quietly "curl -s -o microsoft.list $PMC_URL/$DISTRO/$SCALED_VERSION/$CHANNEL.list" "unable to fetch repo list" $ERR_FAILED_REPO_SETUP
        
        # Use Intune-compatible repo file naming: microsoft-$DISTRO-$CODENAME-$CHANNEL.list
        local codename
        codename=$(lsb_release -cs 2>/dev/null || echo "$SCALED_VERSION")
        local repo_list_file="/etc/apt/sources.list.d/microsoft-${DISTRO}-${codename}-${CHANNEL}.list"
        run_quietly "mv ./microsoft.list $repo_list_file" "unable to copy repo to location" $ERR_FAILED_REPO_SETUP

        ### Fetch the gpg key with fingerprint verification (SEC-007) ###
		
		local gpg_key_file="/usr/share/keyrings/microsoft-prod.gpg"
        # Use new GPG key format for Ubuntu 24.04+, Debian 12+
        if { [[ "$DISTRO" == "ubuntu" ]] && [[ "$VERSION" == "24.04" || "$VERSION" == "25.04" || "$VERSION" == "25.10" ]]; } || { [[ "$DISTRO" == "debian" ]] && [[ "$VERSION" == "12" ]]; }; then    
            if [[ ! -f "$gpg_key_file" ]]; then
                download_and_verify_gpg_key "https://packages.microsoft.com/keys/microsoft.asc" "$gpg_key_file" "$MICROSOFT_GPG_FINGERPRINT" || script_exit "GPG key verification failed" $ERR_FAILED_REPO_SETUP
            fi
		# Use 2025 GPG key for Debian 13+
		elif { [[ "$DISTRO" == "debian" ]] && [[ "$VERSION" == "13" ]]; }; then
			if [[ -f "$gpg_key_file" ]]; then
				run_quietly "rm -f $gpg_key_file" "unable to remove existing microsoft-prod.gpg" $ERR_FAILED_REPO_SETUP
            fi
			download_and_verify_gpg_key "https://packages.microsoft.com/keys/microsoft-2025.asc" "$gpg_key_file" "$MICROSOFT_2025_GPG_FINGERPRINT" || script_exit "GPG key verification failed" $ERR_FAILED_REPO_SETUP
        else
            # Legacy systems: still use apt-key but with verification (SEC-008 partial)
            local temp_key
            temp_key=$(create_secure_temp_file) || script_exit "Failed to create temp file" $ERR_FAILED_REPO_SETUP
            run_quietly "curl -fsSL https://packages.microsoft.com/keys/microsoft.asc -o $temp_key" "unable to fetch the gpg key" $ERR_FAILED_REPO_SETUP
            # Verify fingerprint before adding
            local temp_gpg
            temp_gpg=$(create_secure_temp_file) || { rm -f "$temp_key"; script_exit "Failed to create temp file" $ERR_FAILED_REPO_SETUP; }
            gpg --dearmor -o "$temp_gpg" < "$temp_key" 2>/dev/null || { rm -f "$temp_key" "$temp_gpg"; script_exit "Failed to dearmor GPG key" $ERR_FAILED_REPO_SETUP; }
            verify_gpg_key_fingerprint "$temp_gpg" "$MICROSOFT_GPG_FINGERPRINT" || { rm -f "$temp_key" "$temp_gpg"; script_exit "GPG key verification failed" $ERR_FAILED_REPO_SETUP; }
            run_quietly "apt-key add $temp_key" "unable to add the gpg key" $ERR_FAILED_REPO_SETUP
            rm -f "$temp_key" "$temp_gpg"
        fi
    else
        # Try to install/find curl, don't exit the script if it fails.
        packages=(curl)
        install_required_pkgs --no-exit "${packages[@]}"
    fi
    run_quietly "apt-get update" "[!] unable to refresh the repos properly"

    local version=""
    if [[ -n "$MDE_VERSION" ]]; then
        version=$(validate_mde_version)
        if [[ -z "$version" ]]; then
            script_exit "Couldn't find the version $MDE_VERSION for channel $CHANNEL. Aborting installion" $ERR_INSTALLATION_FAILED
        fi
    fi

    if [[ -n "$INSTALL_PATH" ]]; then
		validate_custom_path_installation_version "$version"  || script_exit "Custom Path installation is not supported on version $version, Minimum expected version : 101.25062.0003" $ERR_INSTALLATION_FAILED
        handle_custom_installation
    fi

    ### Install MDE ###
    log_info "[>] installing MDE"
    if [[ -z "$CHANNEL" ]]; then
        run_quietly "$PKG_MGR_INVOKER install mdatp$version" "unable to install MDE ($?)" $ERR_INSTALLATION_FAILED
    elif [[ "$CHANNEL" == "prod" ]]; then
        if [[ -z "$VERSION_NAME" ]]; then
            run_quietly "$PKG_MGR_INVOKER install mdatp$version" "unable to install MDE ($?)" $ERR_INSTALLATION_FAILED
        else
            run_quietly "$PKG_MGR_INVOKER -t $VERSION_NAME install mdatp$version" "unable to install MDE ($?)" $ERR_INSTALLATION_FAILED
        fi
    else
        run_quietly "$PKG_MGR_INVOKER -t $CHANNEL install mdatp$version" "unable to install MDE ($?)" $ERR_INSTALLATION_FAILED
    fi

    sleep 5
    log_info "[v] Installation complete!"
}

install_on_mariner()
{
    local packages=()
    local pkg_version=
    local repo=

    if [[ -z "$SKIP_PMC_SETUP" ]]; then 
        # To use config-manager plugin, install dnf-plugins-core package
        run_quietly "$PKG_MGR_INVOKER install dnf-plugins-core" "failed to install dnf-plugins-core"

        ### Install MDE ###
        log_info "[>] installing MDE"
        if [[ "$CHANNEL" == "prod" ]]; then
            run_quietly "$PKG_MGR_INVOKER install mariner-repos-extras" "unable to install mariner-repos-extras"
            run_quietly "$PKG_MGR_INVOKER config-manager --enable mariner-official-extras" "unable to enable extras repo"
            run_quietly "$PKG_MGR_INVOKER config-manager --disable mariner-official-extras-preview" "unable to disable extras-preview repo"
        elif [[ "$CHANNEL" == "insiders-slow" ]]; then
            ### Add Preview Repo File ###
            run_quietly "$PKG_MGR_INVOKER install mariner-repos-extras-preview" "unable to install mariner-repos-extras-preview"
            run_quietly "$PKG_MGR_INVOKER config-manager --enable mariner-official-extras-preview" "unable to enable extras-preview repo"
        else
            # mariner is only supported on prod and insiders-slow channels
            script_exit "Invalid channel: $CHANNEL. Available channels for $DISTRO_FAMILY are prod and insiders-slow channel only." $ERR_INVALID_CHANNEL
        fi
    fi

    local version=""
    if [[ -n "$MDE_VERSION" ]]; then
        version=$(validate_mde_version)
        if [[ -z "$version" ]]; then
            script_exit "Couldn't find the version $MDE_VERSION for channel $CHANNEL. Aborting installion" $ERR_INSTALLATION_FAILED
        fi
    fi

    if [[ -n "$INSTALL_PATH" ]]; then
		validate_custom_path_installation_version "$version"  || script_exit "Custom Path installation is not supported on version $version, Minimum expected version : 101.25062.0003" $ERR_INSTALLATION_FAILED
        handle_custom_installation
    fi

    ### Install MDE ###
    log_info "[>] installing MDE"
    run_quietly "$PKG_MGR_INVOKER install mdatp$version" "unable to install MDE ($?)" $ERR_INSTALLATION_FAILED

    sleep 5
    log_info "[v] Installation complete!"
}

install_on_azurelinux()
{
    local packages=()
    local pkg_version=
    local repo=

    if [[ -z "$SKIP_PMC_SETUP" ]]; then 
        # To use config-manager plugin, install dnf-plugins-core package
        run_quietly "$PKG_MGR_INVOKER install dnf-plugins-core" "failed to install dnf-plugins-core"

        ### Configure the repository ###
        log_info "[>] configuring the repository"
        if [[ "$CHANNEL" == "prod" ]]; then
            run_quietly "$PKG_MGR_INVOKER install azurelinux-repos-ms-non-oss" "unable to install azurelinux-repos-ms-non-oss"
            run_quietly "$PKG_MGR_INVOKER config-manager --enable azurelinux-repos-ms-non-oss" "unable to enable extras repo"
            run_quietly "$PKG_MGR_INVOKER config-manager --disable azurelinux-repos-ms-non-oss-preview" "unable to disable extras-preview repo"
        else
            ### Add Preview Repo File ###
            run_quietly "$PKG_MGR_INVOKER install azurelinux-repos-ms-non-oss-preview" "unable to install azurelinux-repos-ms-non-oss-preview"
        fi
    fi

    local version=""
    if [[ -n "$MDE_VERSION" ]]; then
        version=$(validate_mde_version)
        if [[ -z "$version" ]]; then
            script_exit "Couldn't find the version $MDE_VERSION for channel $CHANNEL. Aborting installion" $ERR_INSTALLATION_FAILED
        fi
    fi

    if [[ -n "$INSTALL_PATH" ]]; then
		validate_custom_path_installation_version "$version"  || script_exit "Custom Path installation is not supported on version $version, Minimum expected version : 101.25062.0003" $ERR_INSTALLATION_FAILED
        handle_custom_installation
    fi

    ### Install MDE ###
    log_info "[>] installing MDE"
    run_quietly "$PKG_MGR_INVOKER install mdatp$version" "unable to install MDE ($?)" $ERR_INSTALLATION_FAILED

    sleep 5
    log_info "[v] Installation complete!"
}

install_on_fedora()
{
    local packages=()
    local pkg_version=
    local repo=packages-microsoft-com
    local effective_distro=

    # curl-minimal results into issues when present and trying to install curl, so skip installing
    # the curl over Amazon Linux 2023
    if ! ([[ "$VERSION" == "2023" ]] && [[ "$DISTRO" == "amzn" ]] && check_if_pkg_is_installed curl-minimal); then
        packages=(curl)
    fi

    if [[ -z "$SKIP_PMC_SETUP" ]]; then 
        packages=("${packages[@]}" yum-utils)

        if [[ $SCALED_VERSION == 7* ]] && [[ "$DISTRO" == "rhel" ]]; then
            packages=("${packages[@]}" deltarpm)
        fi

        install_required_pkgs "${packages[@]}"

        ### Configure the repository ###
        log_info "[>] configuring the repository"
        ### Configure the repo name from which package should be installed
        local repo_name=${repo}-${CHANNEL}

        if [[ $SCALED_VERSION == 7* ]] && [[ "$CHANNEL" != "prod" ]]; then
            repo_name=packages-microsoft-com-prod-${CHANNEL}
        fi

        if [[ "$CHANNEL" == "insiders-slow" ]] && [[ "$DISTRO" != "rocky" ]] && [[ "$DISTRO" != "almalinux" ]] && ! { [[ "$DISTRO" == "rhel" ]] && [[ "$SCALED_VERSION" == 9* ]]; }; then  # in case of insiders slow repo [except rocky and alma], the repo name is packages-microsoft-com-slow-prod
            #repo_name=${repo}-slow-prod
            repo_name="packages-microsoft-com-insiders-slow"
        fi

        if [[ "$DISTRO" == "ol" ]] || [[ "$DISTRO" == "fedora" ]]; then
            effective_distro="rhel"
        elif [[ "$DISTRO" == "almalinux" ]]; then
            effective_distro="alma"
        elif [[ "$DISTRO" == "amzn" ]]; then
            effective_distro="amazonlinux"
        else
            effective_distro="$DISTRO"
        fi

        # Configure repository if it does not exist
        yum -q repolist "$repo_name" | grep "$repo_name"
        found_repo=$?
        if [[ $found_repo -eq 0 ]]; then
            log_info "[i] repository already configured"
        else
            log_info "[>] configuring the repository"
            run_quietly "yum-config-manager --add-repo=$PMC_URL/$effective_distro/$SCALED_VERSION/$CHANNEL.repo" "Unable to fetch the repo ($?)" $ERR_FAILED_REPO_SETUP
        fi

        ### Fetch the gpg key ###
        run_quietly "curl https://packages.microsoft.com/keys/microsoft.asc > microsoft.asc" "unable to fetch gpg key $?" $ERR_FAILED_REPO_SETUP
        run_quietly "rpm $(get_rpm_proxy_params) --import microsoft.asc" "unable to import gpg key" $ERR_FAILED_REPO_SETUP
    else
        # Try to install/find packages, don't exit the script if it fails.
        install_required_pkgs --no-exit "${packages[@]}"
    fi

    local version=""
    if [[ -n "$MDE_VERSION" ]]; then
        version=$(validate_mde_version)
        if [[ -z "$version" ]]; then
            script_exit "Couldn't find the version $MDE_VERSION for channel $CHANNEL. Aborting installion" $ERR_INSTALLATION_FAILED
        fi
    fi

    if [[ -n "$INSTALL_PATH" ]]; then
		validate_custom_path_installation_version "$version"  || script_exit "Custom Path installation is not supported on version $version, Minimum expected version : 101.25062.0003" $ERR_INSTALLATION_FAILED
        handle_custom_installation
    fi

    ### Install MDE ###
    log_info "[>] installing MDE"

    if [[ "$ARCHITECTURE" == "aarch64" ]] || [[ -z "$repo_name" ]]; then
        run_quietly "$PKG_MGR_INVOKER install mdatp$version" "unable to install MDE ($?)" $ERR_INSTALLATION_FAILED
    else
        run_quietly "$PKG_MGR_INVOKER --enablerepo=$repo_name install mdatp$version" "unable to install MDE ($?)" $ERR_INSTALLATION_FAILED
    fi

    sleep 5
    log_info "[v] Installation complete!"
}

install_on_sles()
{
    local packages=()
    local pkg_version=
    local repo=packages-microsoft-com

    packages=(curl)
    if [[ -z "$SKIP_PMC_SETUP" ]]; then 
        install_required_pkgs "${packages[@]}"

        wait_for_package_manager_to_complete

        ### Configure the repository ###
        local repo_name=${repo}-${CHANNEL}
        if [[ "$CHANNEL" == "insiders-slow" ]]; then  # in case of insiders slow repo, the repo name is packages-microsoft-com-slow-prod
            repo_name=${repo}-slow-prod
        fi

        # add repository if it does not exist
        lines=$($PKG_MGR_INVOKER lr | grep "$repo_name" | wc -l)

        if [[ $lines -eq 0 ]]; then
            log_info "[>] configuring the repository"
            run_quietly "$PKG_MGR_INVOKER addrepo -c -f -n $repo_name https://packages.microsoft.com/config/$DISTRO/$SCALED_VERSION/$CHANNEL.repo" "unable to load repo" $ERR_FAILED_REPO_SETUP
        else
            log_info "[i] repository already configured"
        fi

        ### Fetch the gpg key ###
        run_quietly "rpm $(get_rpm_proxy_params) --import https://packages.microsoft.com/keys/microsoft.asc > microsoft.asc" "unable to fetch gpg key $?" $ERR_FAILED_REPO_SETUP

        wait_for_package_manager_to_complete
    else
        # Try to install/find packages, don't exit the script if it fails.
        install_required_pkgs --no-exit "${packages[@]}"
    fi

    local version=""
    if [[ -n "$MDE_VERSION" ]]; then
        version=$(validate_mde_version)
        if [[ -z "$version" ]]; then
            script_exit "Couldn't find the version $MDE_VERSION for channel $CHANNEL. Aborting installion" $ERR_INSTALLATION_FAILED
        fi
    fi

    if [[ -n "$INSTALL_PATH" ]]; then
		validate_custom_path_installation_version "$version"  || script_exit "Custom Path installation is not supported on version $version, Minimum expected version : 101.25062.0003" $ERR_INSTALLATION_FAILED
        handle_custom_installation
    fi

    ### Install MDE ###
    log_info "[>] installing MDE"

    if [[ -z "$repo_name" ]]; then
        run_quietly "$PKG_MGR_INVOKER install $ASSUMEYES mdatp$version" "[!] failed to install MDE (1/2)"
    else
        run_quietly "$PKG_MGR_INVOKER install $ASSUMEYES ${repo_name}:mdatp$version" "[!] failed to install MDE (1/2)"
    fi
    
    if ! check_if_pkg_is_installed mdatp; then
        log_warning "[r] retrying"
        sleep 2
        run_quietly "$PKG_MGR_INVOKER install $ASSUMEYES mdatp" "unable to install MDE 2/2 ($?)" $ERR_INSTALLATION_FAILED
    fi

    sleep 5
    log_info "[v] Installation complete!"
}

remove_repo()
{
    # Remove mdatp if installed
    if check_if_pkg_is_installed mdatp; then
        current_channel=$(get_mdatp_channel)
        if [[ "$CHANNEL" == "$current_channel" ]]; then
            log_info "[i] MDE is installed for $CHANNEL"
            remove_mdatp
        fi
    fi

    log_info "[>] Removing repo for $CHANNEL"

    local cmd_status
    # Remove configured packages.microsoft.com repository
    if [[ "$DISTRO" == "sles" ]] || [[ "$DISTRO" == "sle-hpc" ]]; then
        local repo=packages-microsoft-com
        local repo_name=${repo}-${CHANNEL}
        if [[ "$CHANNEL" == "insiders-slow" ]]; then  # in case of insiders slow repo, the repo name is packages-microsoft-com-slow-prod
            repo_name=${repo}-slow-prod
        fi
        run_quietly "$PKG_MGR_INVOKER removerepo $repo_name" "failed to remove repo"
    
    elif [[ "$DISTRO_FAMILY" == "fedora" ]]; then
        local repo=packages-microsoft-com
        local repo_name="$repo-$CHANNEL"

        if [[ "$CHANNEL" == "insiders-slow" ]]; then  # in case of insiders slow repo, the repo name is packages-microsoft-com-slow-prod
            repo_name=${repo}-slow-prod
        fi

        if [[ $SCALED_VERSION == 7* ]] && [[ "$CHANNEL" != "prod" ]]; then
            repo_name=${repo}-prod
        fi

        yum -q repolist $repo_name | grep "$repo_name" &> /dev/null
        cmd_status=$?
        if [[ $cmd_status -eq 0 ]]; then
            run_quietly "yum-config-manager --disable $repo_name" "Unable to disable the repo ($?)" $ERR_FAILED_REPO_CLEANUP
            run_quietly "find /etc/yum.repos.d -exec grep -lqR \"\[$repo_name\]\" '{}' \; -delete" "Unable to remove repo ($?)" $ERR_FAILED_REPO_CLEANUP
        else
            log_info "[i] nothing to clean up"
        fi
    
    elif [[ "$DISTRO_FAMILY" == "debian" ]]; then
        # Clean up both old and new naming conventions
        local codename
        codename=$(lsb_release -cs 2>/dev/null || echo "unknown")
        local old_repo_file="/etc/apt/sources.list.d/microsoft-$CHANNEL.list"
        local new_repo_file="/etc/apt/sources.list.d/microsoft-${DISTRO}-${codename}-${CHANNEL}.list"
        
        if [[ -f "$old_repo_file" ]]; then
            run_quietly "rm -f '$old_repo_file'" "unable to remove repo list ($?)" $ERR_FAILED_REPO_CLEANUP
        fi
        if [[ -f "$new_repo_file" ]]; then
            run_quietly "rm -f '$new_repo_file'" "unable to remove repo list ($?)" $ERR_FAILED_REPO_CLEANUP
        fi
    elif [[ "$DISTRO_FAMILY" == "mariner" ]]; then # in case of mariner, do not remove the repo
        log_info "[i] nothing to clean up"
        return
    else
        script_exit "unsupported distro for remove repo $DISTRO" $ERR_UNSUPPORTED_DISTRO
    fi

    log_info "[v] Repo removed for $CHANNEL"
}

upgrade_mdatp()
{
    if [[ -z "$1" ]]; then
        script_exit "INTERNAL ERROR. upgrade_mdatp requires an argument (the upgrade command)" $ERR_INTERNAL
    fi

    exit_if_mde_not_installed

    local VERSION_BEFORE_UPDATE VERSION_AFTER_UPDATE version current_version requested_version
    VERSION_BEFORE_UPDATE=$(get_mdatp_version)
    log_info "[i] Current $VERSION_BEFORE_UPDATE"

    version=""
    if [[ -n "$MDE_VERSION" ]]; then
        version=$(validate_mde_version)
        if [[ -z "$version" ]]; then
            script_exit "Couldn't find the version $MDE_VERSION for channel $CHANNEL. Aborting upgrade" $ERR_INSTALLATION_FAILED
        fi
    fi

    current_version=$(echo "$VERSION_BEFORE_UPDATE" | sed 's/^[ \t\n]*//;s/[ \t\n]*$//' | awk '{print $NF}' | awk -F. '{ printf("%d%05d%05d\n", $1,$2,$3); }')
    requested_version=$(echo "$MDE_VERSION" | awk -F. '{ printf("%d%05d%05d\n", $1,$2,$3); }')

    if [[ "$INSTALL_MODE" == "d" && "$current_version" -lt "$requested_version" ]]; then
        script_exit "For downgrade the requested version[$MDE_VERSION] should be older than current version[$VERSION_BEFORE_UPDATE]"
    elif [[ "$INSTALL_MODE" == "u" && -n "$MDE_VERSION" && "$current_version" -gt "$requested_version" ]]; then
        script_exit "For upgrade the requested version[$MDE_VERSION] should be newer than current version[$VERSION_BEFORE_UPDATE]. If you want to move to an older version instead, retry with --downgrade flag"
    fi

    run_quietly "$PKG_MGR_INVOKER $1 mdatp$version" "Unable to upgrade MDE $?" $ERR_INSTALLATION_FAILED

    VERSION_AFTER_UPDATE=$(get_mdatp_version)
    if [[ "$VERSION_BEFORE_UPDATE" == "$VERSION_AFTER_UPDATE" ]]; then
        log_info "[i] MDE is already up to date."
    else
        log_info "[v] Upgrade successful!" 
    fi
}

remove_mdatp()
{
    exit_if_mde_not_installed

    log_info "[>] Removing MDE" 

    run_quietly "$PKG_MGR_INVOKER remove mdatp" "unable to remove MDE $?" $ERR_UNINSTALLATION_FAILED
}

rhel6_supported_version()
{
    local SUPPORTED_RHEL6_VERSIONS=("6.7" "6.8" "6.9" "6.10")
    for version in "${SUPPORTED_RHEL6_VERSIONS[@]}"; do
        if [[ "$1" == "$version" ]]; then 
            return 0
        fi
    done
    return 1    
}

scale_version_id()
{
    ### We dont have pmc repos for rhel versions > 7.4. Generalizing all the 7* repos to 7 and 8* repos to 8
    if [[ "$DISTRO_FAMILY" == "fedora" ]]; then
        if [[ $VERSION == 6* ]]; then
            if rhel6_supported_version $VERSION; then # support versions 6.7+
                if [[ "$DISTRO" == "centos" ]] || [[ "$DISTRO" == "rhel" ]]; then
                    SCALED_VERSION=6
                else
                    script_exit "unsupported version: $DISTRO $VERSION" $ERR_UNSUPPORTED_VERSION
                fi
            else
               script_exit "unsupported version: $DISTRO $VERSION" $ERR_UNSUPPORTED_VERSION
            fi

        elif [[ $VERSION == 7* ]]; then
            SCALED_VERSION=7
        elif [[ $VERSION == 8* ]] || [[ "$DISTRO" == "fedora" ]]; then
            SCALED_VERSION=8
        elif [[ $VERSION == 9* ]]; then
            if [[ $DISTRO == "almalinux" || $DISTRO == "rocky" || $DISTRO == "ol" ]]; then
                SCALED_VERSION=9
            else
                SCALED_VERSION=9.0
            fi
		elif [[ "$VERSION" == 10* ]] && [[ "$DISTRO" == "centos" || "$DISTRO" == "rhel" || "$DISTRO" == "ol" || "$DISTRO" == "rocky" ]]; then
			SCALED_VERSION=10
        elif [[ $DISTRO == "amzn" ]] &&  [[ $VERSION == "2" || $VERSION == "2023" ]]; then # For Amazon Linux the scaled version is 2023 or 2
            SCALED_VERSION=$VERSION
        else
            script_exit "unsupported version: $DISTRO $VERSION" $ERR_UNSUPPORTED_VERSION
        fi
    elif [[ "$DISTRO_FAMILY" == "mariner" ]]; then
        if [[ $VERSION == 2* ]]; then
            SCALED_VERSION=2
        else
            script_exit "unsupported version: $DISTRO $VERSION" $ERR_UNSUPPORTED_VERSION
        fi
    elif [[ "$DISTRO_FAMILY" == "azurelinux" ]]; then
        if [[ $VERSION == 3* ]]; then
            SCALED_VERSION=3
        else
            script_exit "unsupported version: $DISTRO $VERSION" $ERR_UNSUPPORTED_VERSION
        fi
    elif [[ "$DISTRO_FAMILY" == "sles" ]]; then
        if [[ $VERSION == 12* ]]; then
            SCALED_VERSION=12
        elif [[ $VERSION == 15* ]]; then
            SCALED_VERSION=15
        else
            script_exit "unsupported version: $DISTRO $VERSION" $ERR_UNSUPPORTED_VERSION
        fi
    elif [[ $DISTRO == "ubuntu" ]] && [[ $VERSION != "16.04" ]] && [[ $VERSION != "18.04" ]] && [[ $VERSION != "20.04" ]] && [[ $VERSION != "22.04" ]] && [[ $VERSION != "24.04" ]] && [[ $VERSION != "25.04" ]] && [[ $VERSION != "25.10" ]]; then
        SCALED_VERSION=18.04
    else
        # no problems with 
        SCALED_VERSION=$VERSION
    fi
    log_info "[v] scaled: $SCALED_VERSION"
}

onboard_device()
{
    log_info "[>] onboarding script: $ONBOARDING_SCRIPT"

    exit_if_mde_not_installed

    if check_if_device_is_onboarded; then
        log_info "[i] MDE already onboarded"
        return
    fi

    if [[ ! -f "$ONBOARDING_SCRIPT" ]]; then
        script_exit "error: onboarding script not found." $ERR_ONBOARDING_NOT_FOUND
    fi

    if [[ $ONBOARDING_SCRIPT == *.py ]]; then
        # Make sure python is installed
        PYTHON=$(command -v python 2>/dev/null || command -v python3 2>/dev/null)

        if [[ -z "$PYTHON" ]]; then
            script_exit "error: could not locate python." $ERR_FAILED_DEPENDENCY
        fi

        #remove mdatp_offboard.json if present
        mdatp_offboard_file=/etc/opt/microsoft/mdatp/mdatp_offboard.json
        if [[ -f "$mdatp_offboard_file" ]]; then
            echo "found mdatp_offboard file"
            run_quietly "rm -f \"$mdatp_offboard_file\"" "error: failed to remove offboarding blob" $ERR_ONBOARDING_FAILED
            if [[ ! -f "$mdatp_offboard_file" ]]; then
                echo "removed mdatp_offboard file"
            else
                echo "failed to remove mdatp_offboard file"
            fi
        fi

        # Run onboarding script
        sleep 1
        run_quietly "\"$PYTHON\" \"$ONBOARDING_SCRIPT\"" "error: python onboarding failed" $ERR_ONBOARDING_FAILED

    elif [[ $ONBOARDING_SCRIPT == *.sh ]]; then        
        shebang_line=$(head -n 1 "$ONBOARDING_SCRIPT")
        if [[ "$shebang_line" == \#!* ]]; then
            interpreter_path=${shebang_line:2}
            run_quietly "\"$interpreter_path\" \"$ONBOARDING_SCRIPT\"" "error: $interpreter_path onboarding failed" $ERR_ONBOARDING_FAILED
        else
            run_quietly "sh \"$ONBOARDING_SCRIPT\"" "error: sh onboarding failed" $ERR_ONBOARDING_FAILED
        fi

    elif [[ $ONBOARDING_SCRIPT == *.json ]]; then
        local onboarding_dir=/etc/opt/microsoft/mdatp/
        if [[ -d "$onboarding_dir" ]]; then
            run_quietly "cp \"$ONBOARDING_SCRIPT\" \"$onboarding_dir/mdatp_onboard.json\"" "error: JSON onboarding failed" $ERR_ONBOARDING_FAILED
        else
            script_exit "error: JSON onboarding failed. mdatp is not installed or installation failed." $ERR_ONBOARDING_FAILED
        fi
    else
        script_exit "error: unknown onboarding script type." $ERR_ONBOARDING_FAILED
    fi

    # validate onboarding
    local license_found
    license_found=false

    for ((i = 1; i <= 8; i++)); do
        sleep 10 # Delay for 10 seconds before checking the license status

        # Check if licensed field is true
        if check_if_device_is_onboarded; then
            license_found=true
            break
        fi
    done

    if [[ "$license_found" == "false" ]]; then
        script_exit "onboarding failed" $ERR_ONBOARDING_FAILED
    fi

    log_info "[v] Onboarded"
}

offboard_device()
{
    log_info "[>] offboarding script: $OFFBOARDING_SCRIPT"

    exit_if_mde_not_installed

    if ! check_if_device_is_onboarded; then
        log_info "[i] MDE already offboarded"
        return
    fi

    if [[ ! -f "$OFFBOARDING_SCRIPT" ]]; then
        script_exit "error: offboarding script not found." $ERR_OFFBOARDING_NOT_FOUND
    fi
    local cmd_status
    if [[ $OFFBOARDING_SCRIPT == *.py ]]; then
        # Make sure python is installed
        PYTHON=$(command -v python 2>/dev/null || command -v python3 2>/dev/null)

        if [[ -z "$PYTHON" ]]; then
            script_exit "error: could not locate python." $ERR_FAILED_DEPENDENCY
        fi

        # Run offboarding script
        sleep 1
        run_quietly "\"$PYTHON\" \"$OFFBOARDING_SCRIPT\"" "error: python offboarding failed" $ERR_OFFBOARDING_FAILED

    elif [[ $OFFBOARDING_SCRIPT == *.sh ]]; then        
        run_quietly "sh \"$OFFBOARDING_SCRIPT\"" "error: bash offboarding failed" $ERR_OFFBOARDING_FAILED

    else
        script_exit "error: unknown offboarding script type." $ERR_OFFBOARDING_FAILED
    fi

    # validate offboarding
    local license_found
    license_found=true
    for ((i = 1; i <= 15; i++)); do
        sleep 10 # Delay for 10 seconds before checking the license status

        # Check if licensed field is false
        if ! check_if_device_is_onboarded; then
            license_found=false
            break
        fi
    done

    if [[ "$license_found" == "true" ]]; then
        script_exit "offboarding failed" $ERR_OFFBOARDING_FAILED "offboarding_failed"
    fi

    log_info "[v] Offboarded"
}

set_epp_to_passive_mode()
{
    exit_if_mde_not_installed

    if [[ $(get_health_field passive_mode_enabled) == "false" ]]; then
        log_info "[>] setting MDE/EPP to passive mode"
        retry_quietly 3 "mdatp config passive-mode --value enabled" "failed to set MDE to passive-mode" $ERR_PARAMETER_SET_FAILED
    else
        log_info "[i] MDE/EPP already in passive mode"
        return
    fi
    
    log_info "[v] passive mode set"
}

set_epp_to_rtp_mode()
{
    exit_if_mde_not_installed

    if [[ $(get_health_field real_time_protection_enabled) == "false" ]]; then
        log_info "[>] setting MDE/EPP to real time protection mode"
        retry_quietly 3 "mdatp config real-time-protection --value enabled" "failed to set MDE to rtp-mode" $ERR_PARAMETER_SET_FAILED
    else
        log_info "[i] MDE/EPP already in real time protection mode"
        return
    fi

    log_info "[v] real time protection mode set"
}

set_device_tags()
{
    for tag_key in "${!tags[@]}"; do
        tag_value="${tags[$tag_key]}"

        local set_tags tag_exists result value
        if [[ "$tag_key" == "GROUP" ]] || [[ "$tag_key" == "SecurityWorkspaceId" ]] || [[ "$tag_key" == "AzureResourceId" ]] || [[ "$tag_key" == "SecurityAgentId" ]]; then
            set_tags=$(get_health_field edr_device_tags)
            tag_exists=0

            result=$(echo "$set_tags" | grep -q "\"key\":\"$tag_key\""; echo "$?")
            if [[ $result -eq 0 ]]; then
                value=$(echo "$set_tags" | grep -o "\"key\":\"$tag_key\".*\"" | cut -d '"' -f 8)
                if [[ "$value" == "$tag_value" ]]; then
                    log_warning "[i] tag $tag_key already set to value $tag_value"
                    tag_exists=1
                fi
            fi

            if [[ $tag_exists -eq 0 ]]; then
                log_debug "[>] setting tag: ($tag_key, $tag_value)"
                retry_quietly 2 "mdatp edr tag set --name $tag_key --value $tag_value" "failed to set tag" $ERR_PARAMETER_SET_FAILED
            fi
        else
            script_exit "invalid tag name: $tag_key. supported tags: GROUP, SecurityWorkspaceId, AzureResourceId and SecurityAgentId" $ERR_TAG_NOT_SUPPORTED
        fi
    done
    log_info "[v] tags set."   
}

usage()
{
    echo "mde_installer.sh v$SCRIPT_VERSION"
    echo "usage: $1 [OPTIONS]"
    echo "Options:"
    echo " -c|--channel         specify the channel(insiders-fast / insiders-slow / prod) from which you want to install. Default: prod"
    echo " -i|--install         install the product"
    echo " -r|--remove          uninstall the product"
    echo " -u|--upgrade         upgrade the existing product to a newer version if available"
    echo " -l|--downgrade       downgrade the existing product to a older version if available"
    echo " -o|--onboard         onboard the product with <onboarding_script>"
    echo " -f|--offboard        offboard the product with <offboarding_script>"
    echo " -p|--passive-mode    set real time protection to passive mode"
    echo " -a|--rtp-mode        set real time protection to active mode. passive-mode and rtp-mode are mutually exclusive"
    echo " -t|--tag             set a tag by declaring <name> and <value>, e.g: -t GROUP Coders"
    echo " -m|--min_req         enforce minimum requirements"
    echo " -x|--skip_conflict   skip conflicting application verification"
    echo " -w|--clean           remove repo from package manager for a specific channel"
    echo " -y|--yes             assume yes for all mid-process prompts (default, depracated)"
    echo " -n|--no              remove assume yes sign"
    echo " -s|--verbose         verbose output"
    echo " -v|--version         print out script version"
    echo " -d|--debug           set debug mode"
    echo " --log-path <PATH>    also log output to PATH"
    echo " --http-proxy <URL>   set http proxy"
    echo " --https-proxy <URL>  set https proxy"
    echo " --ftp-proxy <URL>    set ftp proxy"
    echo " --mdatp              specific version of mde to be installed. will use the latest if not provided"
    echo " --use-local-repo     this will skip the MDE repo setup and use the already configured repo instead"
    echo " -b|--install-path    specify the installation and configuration path for MDE. Default: /"
    echo " -h|--help            display help"
}

if [[ $# -eq 0 ]]; then
    usage
    script_exit "no arguments were provided. specify --help for details" $ERR_INVALID_ARGUMENTS
fi

while [[ $# -ne 0 ]];
do
    case "$1" in
        -c|--channel)
            if [[ -z "$2" ]]; then
                script_exit "$1 option requires an argument" $ERR_INVALID_ARGUMENTS
            fi
            CHANNEL=$2
            verify_channel
            shift 2
            ;;
        -i|--install)
            INSTALL_MODE="i"
            verify_privileges "install"
            shift 1
            ;;
        -u|--upgrade|--update)
            INSTALL_MODE="u"
            verify_privileges "upgrade"
            shift 1
            ;;
        -l|--downgrade)
            INSTALL_MODE="d"
            verify_privileges "downgrade"
            shift 1
            ;;
        -r|--remove)
            INSTALL_MODE="r"
            verify_privileges "remove"
            shift 1
            ;;
        -o|--onboard)
            if [[ -z "$2" ]]; then
                script_exit "$1 option requires an argument" $ERR_INVALID_ARGUMENTS
            fi
            ONBOARDING_SCRIPT=$(validate_script_path "$2" "onboarding") || script_exit "Invalid onboarding script path" $ERR_INVALID_ARGUMENTS
            verify_privileges "onboard"
            shift 2
            ;;
        -f|--offboard)
            if [[ -z "$2" ]]; then
                script_exit "$1 option requires an argument" $ERR_INVALID_ARGUMENTS
            fi        
            OFFBOARDING_SCRIPT=$(validate_script_path "$2" "offboarding") || script_exit "Invalid offboarding script path" $ERR_INVALID_ARGUMENTS
            verify_privileges "offboard"
            shift 2
            ;;
        -m|--min_req)
            MIN_REQUIREMENTS=1
            shift 1
            ;;
        -x|--skip_conflict)
            SKIP_CONFLICTING_APPS=1
            shift 1
            ;;
        -p|--passive-mode)
            verify_privileges "passive-mode"
            PASSIVE_MODE=1
            shift 1
            ;;
        -a|--rtp-mode)
            verify_privileges "rtp-mode"
            RTP_MODE=1
            shift 1
            ;;
        -t|--tag)
            if [[ -z "$2" || -z "$3" ]]; then
                script_exit "$1 option requires two arguments" $ERR_INVALID_ARGUMENTS
            fi
            verify_privileges "set-tag"
            tags["$2"]="$3"
            shift 3
            ;;
        -w|--clean)
            INSTALL_MODE='c'
            verify_privileges "clean"
            shift 1
            ;;
        -h|--help)
            usage "basename $0" >&2
            exit 0
            ;;
        -y|--yes)
            ASSUMEYES=-y
            shift 1
            ;;
        -n|--no)
            ASSUMEYES=
            shift 1
            ;;            
        -s|--verbose)
            VERBOSE=1
            shift 1
            ;;
        -v|--version)
            script_exit "$SCRIPT_VERSION" $SUCCESS
            ;;
        -d|--debug)
            DEBUG=1
            shift 1
            ;;
        --http-proxy)
            if [[ -z "$2" ]]; then
                script_exit "$1 option requires two arguments" $ERR_INVALID_ARGUMENTS
            fi
            export http_proxy=$2
            shift 2
            ;;
        --https-proxy)
            if [[ -z "$2" ]]; then
                script_exit "$1 option requires two arguments" $ERR_INVALID_ARGUMENTS
            fi
            export https_proxy=$2
            shift 2
            ;;
        --ftp-proxy)
            if [[ -z "$2" ]]; then
                script_exit "$1 option requires two arguments" $ERR_INVALID_ARGUMENTS
            fi
            export ftp_proxy=$2
            shift 2
            ;;
        --log-path)
            if [[ -z "$2" ]]; then
                script_exit "$1 option requires two arguments" $ERR_INVALID_ARGUMENTS
            fi
            export log_path=$2
            shift 2
            ;;
        --mdatp)
            if [[ -z "$2" ]]; then
                script_exit "$1 option requires two arguments" $ERR_INVALID_ARGUMENTS
            fi
            export MDE_VERSION=$2
            shift 2
            ;;
        --use-local-repo)
            SKIP_PMC_SETUP=1
            shift 1
            ;;
        -b|--install-path)
            if [[ -z "$2" ]]; then
                script_exit "$1 option requires two arguments" $ERR_INVALID_ARGUMENTS
            else
                INSTALL_PATH=$(validate_install_path "$2") || script_exit "Invalid installation path" $ERR_INVALID_ARGUMENTS
                INSTALL_PATH="${INSTALL_PATH%/}"
            fi
            shift 2
            ;;
        *)
            echo "use -h or --help for details"
            script_exit "unknown argument $1" $ERR_INVALID_ARGUMENTS
            ;;
    esac
done

if command -v mdatp >/dev/null 2>&1; then 
    INSTALLED_MDE_CHANNEL=$(get_mdatp_channel)
    if [[ "$INSTALLED_MDE_CHANNEL" != "$CHANNEL" ]] && [[ "$INSTALL_MODE" != 'c' ]]; then
        if [[ -n "$CHANNEL" ]]; then
            echo "[i] MDE Installed with $INSTALLED_MDE_CHANNEL. Cannot switch channel to $CHANNEL. Channel is being set to $INSTALLED_MDE_CHANNEL. To update chanel remove and re-install MDE with $CHANNEL"
        fi
        CHANNEL=$INSTALLED_MDE_CHANNEL
    fi
fi

if [[ -z "${INSTALL_MODE}" && -z "${ONBOARDING_SCRIPT}" && -z "${OFFBOARDING_SCRIPT}" && -z "${PASSIVE_MODE}" && -z "${RTP_MODE}" && ${#tags[@]} -eq 0 ]]; then
    script_exit "no installation mode specified. Specify --help for help" $ERR_INVALID_ARGUMENTS
fi

# Check for mutually exclusive options
if [[ -n "$PASSIVE_MODE" ]] && [[ -n "$RTP_MODE" ]]; then
    echo "Options --passive-mode and --rtp-mode are mutually exclusive."
    usage
    exit 1
fi

if [[ -n "$SKIP_PMC_SETUP" ]]; then
    if [[ "$INSTALL_MODE" == 'c' ]]; then
        script_exit "--clean repo option is not supported with --use-local-repo" $ERR_INVALID_ARGUMENTS
    fi

    if [[ -n "$CHANNEL" ]]; then
        script_exit "--use-local-repo option is not supported with --channel" $ERR_INVALID_ARGUMENTS
    fi
else
    if [[ -z "$CHANNEL" ]]; then
        if [[ "$INSTALL_MODE" == 'i' ]]; then
            log_info "[i] Specify the install channel using \"--channel\" argument. If not provided, mde will be installed for prod by default. Expected channel values: prod, insiders-slow, insiders-fast."
        elif [[ "$INSTALL_MODE" == 'c' ]]; then
            log_info "[i] Specify the cleanup channel using \"--channel\" argument. If not provided, prod repo will be cleaned up by default. Expected channel values: prod, insiders-slow, insiders-fast."
        fi
        CHANNEL=prod
    fi
fi

if [[ "$INSTALL_MODE" == 'd' && -z "$MDE_VERSION" ]]; then
    script_exit "Specify the mdatp version using --mdatp argument when using --downgrade option" $ERR_INVALID_ARGUMENTS
fi

if [[ -n "$INSTALL_PATH" && "$INSTALL_MODE" != 'i' ]]; then
    script_exit "install path is only supported for installation" $ERR_INVALID_ARGUMENTS
fi

if [[ -z "$MDE_VERSION" && ( "$INSTALL_MODE" == 'i' || "$INSTALL_MODE" == 'u' ) ]]; then
    log_info "[i] Specify the version to be installed using \"--mdatp\" argument. If not provided, latest mde will be installed by default."
fi


# echo "--- mde_installer.sh v$SCRIPT_VERSION ---"
log_info "--- mde_installer.sh v$SCRIPT_VERSION ---"

### Validate mininum requirements ###
if [[ -n "$MIN_REQUIREMENTS" ]]; then
    verify_min_requirements
fi

## Detect the architecture type
detect_arch

### Detect the distro and version number ###
detect_distro

### Scale the version number according to repos avaiable on pmc ###
scale_version_id

### Set package manager ###
set_package_manager

### Act according to arguments ###
if [[ "$INSTALL_MODE" == "i" ]]; then

    if ! skip_if_mde_installed; then

        if [[ -z "$SKIP_CONFLICTING_APPS" ]]; then
            verify_conflicting_applications
        fi

        if [[ "$DISTRO_FAMILY" == "debian" ]]; then
            install_on_debian
        elif [[ "$DISTRO_FAMILY" == "fedora" ]]; then
            install_on_fedora
        elif [[ "$DISTRO_FAMILY" == "mariner" ]]; then
            install_on_mariner
        elif [[ "$DISTRO_FAMILY" == "azurelinux" ]]; then
            install_on_azurelinux
        elif [[ "$DISTRO_FAMILY" == "sles" ]]; then
            install_on_sles
        else
            script_exit "unsupported distro $DISTRO $VERSION" $ERR_UNSUPPORTED_DISTRO
        fi
    fi

elif [[ "$INSTALL_MODE" == "u" ]]; then

    if [[ "$DISTRO_FAMILY" == "debian" ]]; then
        upgrade_mdatp "$ASSUMEYES install --only-upgrade"
    elif [[ "$DISTRO_FAMILY" == "fedora" ]]; then
        upgrade_mdatp "$ASSUMEYES update"
    elif [[ "$DISTRO_FAMILY" == "mariner" ]]; then
        upgrade_mdatp "$ASSUMEYES update"
    elif [[ "$DISTRO_FAMILY" == "azurelinux" ]]; then
        upgrade_mdatp "$ASSUMEYES update"
    elif [[ "$DISTRO_FAMILY" == "sles" ]]; then
        upgrade_mdatp "up $ASSUMEYES"
    else    
        script_exit "unsupported distro $DISTRO $VERSION" $ERR_UNSUPPORTED_DISTRO
    fi

elif [[ "$INSTALL_MODE" == "d" ]]; then

    if [[ "$DISTRO_FAMILY" == "debian" ]]; then
        upgrade_mdatp "$ASSUMEYES install --allow-downgrades"
    elif [[ "$DISTRO_FAMILY" == "fedora" ]]; then
        upgrade_mdatp "$ASSUMEYES downgrade"
    elif [[ "$DISTRO_FAMILY" == "mariner" ]]; then
        upgrade_mdatp "$ASSUMEYES downgrade"
    elif [[ "$DISTRO_FAMILY" == "azurelinux" ]]; then
        upgrade_mdatp "$ASSUMEYES downgrade"
    elif [[ "$DISTRO_FAMILY" == "sles" ]]; then
        upgrade_mdatp "install --oldpackage $ASSUMEYES"
    else
        script_exit "unsupported distro $DISTRO $VERSION" $ERR_UNSUPPORTED_DISTRO
    fi

elif [[ "$INSTALL_MODE" == "r" ]]; then
    if remove_mdatp; then
        script_exit "removed MDE" $SUCCESS
    fi

elif [[ "$INSTALL_MODE" == "c" ]]; then
    if remove_repo; then
        script_exit "removed repo" $SUCCESS
    fi
fi

if [[ -n "$PASSIVE_MODE" ]]; then
    set_epp_to_passive_mode
elif [[ -n "$RTP_MODE" ]]; then
    set_epp_to_rtp_mode
fi

if [[ -n "$ONBOARDING_SCRIPT" ]]; then
    onboard_device
fi

if [[ -n "$OFFBOARDING_SCRIPT" ]]; then
    offboard_device
fi

if [[ ${#tags[@]} -gt 0 ]]; then
    set_device_tags
fi

script_exit "--- mde_installer.sh ended. ---" $SUCCESS
