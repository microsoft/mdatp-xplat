#!/bin/bash

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

SCRIPT_VERSION="1.2.0" # MDE installer version set this to track the changes in the script used by tools like ansible, MDC etc.
ASSUMEYES=-y
CHANNEL=
MDE_VERSION=
#Dont use this variable directly
ALL_MDE_VERSIONS=
SUPPORTED_LAST_N_VERSIONS=9
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
PRE_REQ_CHECK=
SKIP_CONFLICTING_APPS=
PASSIVE_MODE=
RTP_MODE=
MIN_MEM_MB=1024
MIN_DISK_SPACE_MB=2048
MIN_GLIBC_VERSION="2.17"
MINIMUM_REQUIRED_KERNEL="3.10.0-327"
CURRENT_KERNEL=
SUPPORTED_FILESYSTEMS=("btrfs" "ecryptfs" "ext2" "ext3" "ext4" "fuse" "fuseblk" "jfs" "nfs"
    "overlay" "ramfs" "reiserfs" "tmpfs" "udf" "vfat" "xfs" "Efs" "S3fs" "Blobfuse" "Lustr"
    "glustrefs" "Afs" "sshfs" "cifs" "smb" "gcsfuse" "sysfs")

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

_log() {
    level="$1"
    dest="$2"
    msg="${*:3}"
    ts=$(date -u +"%Y-%m-%dT%H:%M:%S")

    if [ "$dest" = "stdout" ]; then
       echo "$msg"
    elif [ "$dest" = "stderr" ]; then
       >&2 echo "$msg"
    fi

    if [ -n "$log_path" ]; then
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
    if [ -z "$1" ]; then
        log_error "[!] INTERNAL ERROR. script_exit requires an argument"
        exit $ERR_INTERNAL
    fi

    if [ "$DEBUG" != "0" ]; then
        print_state
    fi

    if [ "$2" = "0" ]; then
        log_info "[v] $1"
    else
	    log_error "[x] $1"
    fi

    if [ -z "$2" ]; then
        exit $ERR_INTERNAL
    elif ! [ "$2" -eq "$2" ] 2> /dev/null; then #check error is number
        exit $ERR_INTERNAL
    else
        log_info "[*] exiting ($2)"
        cleanup $2
        exit $2
    fi
}

# Centralized proxy configuration function
get_python() {
   if which python3 &> /dev/null; then
      echo "python3"
   elif which python2 &> /dev/null; then
      echo "python2"
   else
      echo "python"
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

get_rpm_proxy_params() 
{
    local proxy_params=""
    local proxy_host proxy_port
    
    if [ -n "$http_proxy" ]; then
        proxy_host=$(parse_uri "$http_proxy" | sed -n '2p')
        if [ -n "$proxy_host" ];then
           proxy_params="$proxy_params --httpproxy $proxy_host"
        fi

        proxy_port=$(parse_uri "$http_proxy" | sed -n '3p')
        if [ -n "$proxy_port" ]; then
           proxy_params="$proxy_params --httpport $proxy_port"
        fi
    fi
    if [ -n "$ftp_proxy" ];then
       proxy_host=$(parse_uri "$ftp_proxy" | sed -n '2p')
       if [ -n "$proxy_host" ];then
          proxy_params="$proxy_params --ftpproxy $proxy_host"
       fi

       proxy_port=$(parse_uri "$ftp_proxy" | sed -n '3p')
       if [ -n "$proxy_port" ]; then
          proxy_params="$proxy_params --ftpport $proxy_port"
       fi
    fi
    echo $proxy_params
}

# Get APT proxy configuration
get_apt_proxy_params() 
{
    local apt_proxy_conf=""
    
    if [[ -n "$http_proxy" ]]; then
        apt_proxy_conf="${apt_proxy_conf} -o Acquire::http::Proxy=\"$http_proxy\""
    fi

    if [[ -n "$https_proxy" ]]; then
        apt_proxy_conf="${apt_proxy_conf} -o Acquire::https::Proxy=\"$https_proxy\""
    fi

    if [[ -n "$ftp_proxy" ]]; then
        apt_proxy_conf="${apt_proxy_conf} -o Acquire::ftp::Proxy=\"$ftp_proxy\""
    fi

    echo "$apt_proxy_conf"
}

# Get DNF/YUM proxy parameters
get_dnf_yum_proxy_params() 
{
    # DNF/YUM support proxy via command-line parameter
    # Generate --setopt=proxy=... parameter if http_proxy is set
    # DNF/YUM supports authentication in proxy URL (http://user:pass@host:port)

    local dnf_yum_proxy_params=""
    if [[ -n "$http_proxy" ]]; then
        dnf_yum_proxy_params="--setopt=proxy=$http_proxy"
    fi
    echo "$dnf_yum_proxy_params"
}


# Get ZYPPER proxy parameters
get_zypper_proxy_params() 
{
    local zypper_proxy_params=""

    # ZYPPER only supports one proxy, prioritize HTTP over HTTPS
    if [[ -n "$http_proxy" ]]; then
        zypper_proxy_params="--proxy $http_proxy"
    elif [[ -n "$https_proxy" ]]; then
        zypper_proxy_params="--proxy $https_proxy"
    fi

    echo "$zypper_proxy_params"
}

cleanup()
{
    # If installation failed in case of custom installation, delete symlink
    if [ "$1" = "$ERR_INSTALLATION_FAILED" ] && [ -n "$INSTALL_PATH" ]; then
        local mdatp_symlink="/opt/microsoft/mdatp"
        delete_sym_link "$mdatp_symlink"
    fi
}

run_quietly()
{
    # run_quietly <command> <error_msg> [<error_code>]
    # use error_code for script_exit

    if [ $# -lt 2 ] || [ $# -gt 3 ]; then
        log_error "[!] INTERNAL ERROR. run_quietly requires 2 or 3 arguments"
        exit 1
    fi

    local out exit_code 

    if [ "$DEBUG" != "0" ]; then
        log_debug "[>] Running command: $1"
    fi

    out=$(eval $1 2>&1; echo "$?")
    exit_code=$(echo "$out" | tail -n1)

    if [ -n "$VERBOSE" ]; then
        log_info "$out"
    fi

    if [ "$exit_code" != "0" ]; then
        if [ "$DEBUG" != "0" ]; then
            log_debug "[>] Command output: $out"
            log_debug "[>] Command exit_code: $exit_code"
        fi

        if [ $# -eq 2 ]; then
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

    if [ $# -lt 3 ] || [ $# -gt 4 ]; then
        log_error "[!] INTERNAL ERROR. retry_quietly requires 3 or 4 arguments"
        exit 1
    fi

    local exit_code=
    local retries=$1

    while [ $retries -gt 0 ]
    do

        if run_quietly "$2" "$3"; then
            exit_code=0
        else
            exit_code=1
        fi
        
        if [ $exit_code -ne 0 ]; then
            sleep 1
            ((retries--))
            log_info "[r] $(($1-$retries))/$1"
        else
            retries=0
        fi
    done

    if [ $# -eq 4 ] && [ $exit_code -ne 0 ]; then
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
    if [ $cmd_status -ne 0 ]; then
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
    if [ -f /etc/os-release ] || [ -f /etc/mariner-release ]; then
        . /etc/os-release
        DISTRO=$ID
        VERSION=$VERSION_ID
        VERSION_NAME=$VERSION_CODENAME
    elif [ -f /etc/redhat-release ]; then
        if [ -f /etc/oracle-release ]; then
            DISTRO="ol"
        elif [[ $(grep -o -i "Red\ Hat" /etc/redhat-release) ]]; then
            DISTRO="rhel"
        elif [[ $(grep -o -i "Centos" /etc/redhat-release) ]]; then
            DISTRO="centos"
        fi
        VERSION=$(grep -o "release .*" /etc/redhat-release | cut -d ' ' -f2)
    else
        script_exit "unable to detect distro" $ERR_UNSUPPORTED_DISTRO
    fi

    # change distro to ubuntu for linux mint support
    if [ "$DISTRO" = "linuxmint" ]; then
        DISTRO="ubuntu"
    fi

    if [ "$DISTRO" = "debian" ] || [ "$DISTRO" = "ubuntu" ]; then
        DISTRO_FAMILY="debian"
    elif [ "$DISTRO" = "rhel" ] || [ "$DISTRO" = "centos" ] || [ "$DISTRO" = "ol" ] || [ "$DISTRO" = "fedora" ] || [ "$DISTRO" = "amzn" ] || [ "$DISTRO" = "almalinux" ] || [ "$DISTRO" = "rocky" ]; then
        DISTRO_FAMILY="fedora"
    elif [ "$DISTRO" = "mariner" ]; then
        DISTRO_FAMILY="mariner"
    elif [ "$DISTRO" = "azurelinux" ]; then
        DISTRO_FAMILY="azurelinux"
    elif [ "$DISTRO" = "sles" ] || [ "$DISTRO" = "sle-hpc" ] || [ "$DISTRO" = "sles_sap" ]; then
        DISTRO_FAMILY="sles"
    else
        script_exit "unsupported distro $DISTRO $VERSION" $ERR_UNSUPPORTED_DISTRO
    fi

    log_info "[v] detected: $DISTRO $VERSION $VERSION_NAME ($DISTRO_FAMILY)"
}

verify_channel()
{
    if [ "$CHANNEL" != "prod" ] && [ "$CHANNEL" != "insiders-fast" ] && [ "$CHANNEL" != "insiders-slow" ]; then
        script_exit "Invalid channel: $CHANNEL. Please provide valid channel. Available channels are prod, insiders-fast, insiders-slow" $ERR_INVALID_CHANNEL
    fi
}

verify_privileges()
{
    if [ -z "$1" ]; then
        script_exit "Internal error. verify_privileges require a parameter" $ERR_INTERNAL
    fi

    if [ "$(id -u)" -ne 0 ]; then
        script_exit "root privileges required to perform $1 operation" $ERR_INSUFFICIENT_PRIVILAGES
    fi
}

join_string()
{
    local sep="$1"
    shift
    local result=""
    local val

    for val in "$@"; do
        if [ -n "$val" ]; then
            if [ -n "$result" ]; then
                result+=" $sep "
            fi
            result+="$val"
        fi
    done

    echo "$result"
}

#Blocking
verify_disk_space()
{
    local i_path=/opt
    if [ -n "$INSTALL_PATH" ]; then
        i_path=$(dirname "$INSTALL_PATH")
    fi
    disk_space_mb=$(df -m $i_path | tail -1 | awk '{print $4}')
    if [ "$disk_space_mb" -lt $MIN_DISK_SPACE_MB ]; then
        log_error "[x] Error: MDE requires at least $MIN_DISK_SPACE_MB MB of free disk space for installation. found $disk_space_mb MB."
        return 1
    fi
    return 0
}

#Blocking
verify_total_memory()
{
    mem_mb=$(free -m | grep Mem | awk '{print $2}')
    if [ "$mem_mb" -lt $MIN_MEM_MB ]; then
        log_error "[x] Error: MDE requires at least $MIN_MEM_MB MB of RAM to run. found $mem_mb MB."
        return 1
    fi
    return 0
}

verify_system_specifications()
{
    # verifying minimal reuirements: $MIN_MEM_MB MB RAM, $MIN_DISK_SPACE_MB MB disk disk_space_mb

    disk_error_message=$(verify_disk_space)
    local prereqs_passed=$?

    memory_error_message=$(verify_total_memory)
    (( prereqs_passed |= $? ))

    join_string "|" "$disk_error_message" "$memory_error_message"

    return $prereqs_passed
}

# Split and sanitize extra version
sanitize_extra_version()
{
    local input="$1"
    IFS='.' read -ra tokens <<< "$input"
    local output=()
    for token in "${tokens[@]}"; do
        if [[ "$token" =~ ^[0-9]+$ ]]; then
            output+=("$token")
        else
            break
        fi
    done
    # Pad to length 3
    while [ "${#output[@]}" -lt 3 ]; do output+=("0"); done
    echo "${output[@]}"
}

is_newer_kernel()
{
    if [ "$DEBUG" != "0" ]; then
        log_debug "[>] Comparing kernel versions: [$1] (current) >= [$2] (minimum required)"
    fi
    local current_kernel="$1"
    local minimum_kernel="$2"

    # Split on "-" into main and extra version
    IFS='-' read -r current_main current_extra <<< "$current_kernel"
    IFS='-' read -r minimum_main minimum_extra <<< "$minimum_kernel"

    # Convert main parts to arrays
    IFS='.' read -ra current_parts <<< "$current_main"
    IFS='.' read -ra minimum_parts <<< "$minimum_main"

    # Pad to length 3
    while [ "${#current_parts[@]}" -lt 3 ]; do current_parts+=("0"); done
    while [ "${#minimum_parts[@]}" -lt 3 ]; do minimum_parts+=("0"); done

    # Compare main version numbers
    for (( i=0; i<=2; i++ )); do
        if (( current_parts[i] < minimum_parts[i] )); then
            return 1  # current < minimum
        elif (( current_parts[i] > minimum_parts[i] )); then
            return 0  # current > minimum
        fi
    done

    # If current is an RC, treat it as older
    if [[ "$current_extra" == rc* ]]; then
        return 1
    fi
    if [[ "$minimum_extra" == rc* ]]; then
        return 0
    fi

    # Inline sanitize_extra_version logic to avoid command substitution issues
    # Process current_extra
    local current_extra_cleaned
    current_extra_cleaned=$(echo "$current_extra" | sed 's/[^0-9.]//g')
    IFS='.' read -ra current_tokens <<< "$current_extra_cleaned"
    local current_extra_major="${current_tokens[0]:-0}"
    local current_extra_minor="${current_tokens[1]:-0}"
    local current_extra_patch="${current_tokens[2]:-0}"
    
    # Validate that each part is numeric
    if ! [[ "$current_extra_major" =~ ^[0-9]+$ ]]; then current_extra_major=0; fi
    if ! [[ "$current_extra_minor" =~ ^[0-9]+$ ]]; then current_extra_minor=0; fi
    if ! [[ "$current_extra_patch" =~ ^[0-9]+$ ]]; then current_extra_patch=0; fi
    
    # Process minimum_extra
    local minimum_extra_cleaned
    minimum_extra_cleaned=$(echo "$minimum_extra" | sed 's/[^0-9.]//g')
    IFS='.' read -ra minimum_tokens <<< "$minimum_extra_cleaned"
    local minimum_extra_major="${minimum_tokens[0]:-0}"
    local minimum_extra_minor="${minimum_tokens[1]:-0}"
    local minimum_extra_patch="${minimum_tokens[2]:-0}"
    
    # Validate that each part is numeric
    if ! [[ "$minimum_extra_major" =~ ^[0-9]+$ ]]; then minimum_extra_major=0; fi
    if ! [[ "$minimum_extra_minor" =~ ^[0-9]+$ ]]; then minimum_extra_minor=0; fi
    if ! [[ "$minimum_extra_patch" =~ ^[0-9]+$ ]]; then minimum_extra_patch=0; fi

    # Compare each part individually
    if (( current_extra_major < minimum_extra_major )); then
        return 1
    elif (( current_extra_major > minimum_extra_major )); then
        return 0
    fi
    
    if (( current_extra_minor < minimum_extra_minor )); then
        return 1
    elif (( current_extra_minor > minimum_extra_minor )); then
        return 0
    fi
    
    if (( current_extra_patch < minimum_extra_patch )); then
        return 1
    elif (( current_extra_patch > minimum_extra_patch )); then
        return 0
    fi

    return 0  # versions are equal
}

#Non-Blocking
verify_kernel_version()
{
    if [[ -z "$CURRENT_KERNEL" ]]; then
        log_warning "[!] Warning: Failed to get kernel version."
        return 0
    fi

    is_newer_kernel $CURRENT_KERNEL "$MINIMUM_REQUIRED_KERNEL"
    local result=$?
    if [ "$result" -ne 0 ]; then
        local msg="MDE requires kernel version $MINIMUM_REQUIRED_KERNEL or later but found $CURRENT_KERNEL."
        log_warning "[!] Warning: $msg"
        echo "$msg"
    fi
    return 0
}

is_fs_supported()
{
    for fs in "${SUPPORTED_FILESYSTEMS[@]}"; do
        if [[ "$1" == "$fs" ]]; then
            return 0
        fi
    done
    return 1
}

#Non-Blocking
verify_filesystem_support()
{
    # Extract mount points and fs types
    local mount_info
    mount_info=$(cut -d' ' -f2,3 /proc/mounts)
    if [[ $? -ne 0 ]]; then
        log_warning "[!] Warning: Failed to read /proc/mounts"
        return 0
    fi

    # Loop over each mount and check for unsupported filesystems
    local is_any_fs_supported=false
    unsupported_filesystems=()
    while IFS=' ' read -r mount_point fs_type; do
        if ! is_fs_supported "$fs_type"; then
            unsupported_filesystems+=( "${mount_point}:${fs_type}" )
        else
            is_any_fs_supported=true
        fi
    done <<< "$mount_info"

    if $is_any_fs_supported; then
        return 0
    else
        log_warning "[!] Warning: No supported filesystem found"
        echo "No supported filesystem found"
        return 0
    fi
}

verify_ebpf_support()
{
    local ebpf_minimum_required_kernel=$1

    if [[ -z "$CURRENT_KERNEL" ]]; then
        log_warning "[!] Warning: Failed to get kernel version. Won't be able to verify eBPF support."
        return 0
    fi

    is_newer_kernel $CURRENT_KERNEL "$ebpf_minimum_required_kernel"
    local result=$?
    if [ "$result" -ne 0 ]; then
        local msg="MDE with eBPF requires kernel version $ebpf_minimum_required_kernel or later but found $CURRENT_KERNEL."
        log_warning "[!] Warning: $msg"
    fi
    return $result
}

#Non blocking
verify_supported_distros()
{
    if [[ "$VERSION" == *.* ]]; then
      local major="${VERSION%%.*}"
      local minor="${VERSION#*.}"
    else
      local major="$VERSION"
      local minor="0"
    fi

	local arm_arch='^(aarch64|arm64)'
    local is_arm=false
    [[ "$ARCHITECTURE" =~ $arm_arch ]] && is_arm=true

    local os_not_supported_msg="[!] Warning: The OS $DISTRO $VERSION ($ARCHITECTURE) is not officially supported."

	case "$DISTRO" in
        debian)
            ( $is_arm && [[ "$VERSION" =~ ^(11|12)$ ]] ) || (! $is_arm && (( major >= 9 && major <= 12 )) ) || log_warning "$os_not_supported_msg"
            ;;
        ubuntu)
            [[ "$VERSION" =~ ^(20.04|22.04|24.04)$ ]] || (! $is_arm && [[ "$VERSION" =~ ^(16.04|18.04)$ ]] ) || log_warning "$os_not_supported_msg"
            ;;
        rhel|ol)
            [[ "$major" =~ ^(8|9|10)$ ]] || ( ! $is_arm && (( major >= 7 && minor >= 2 )) ) || log_warning "$os_not_supported_msg"
            ;;
        centos)
            $is_arm && log_warning "$os_not_supported_msg" || [[ "$major" == 8 || ( "$major" == 7 && "$minor" -ge 2 ) ]] || log_warning "$os_not_supported_msg"
            ;;
        sles|sle-hpc|sles_sap)
            [[ "$major" =~ ^(15)$ ]] || (! $is_arm && [[ "$major" =~ ^(12)$ ]] ) || log_warning "$os_not_supported_msg"
            ;;
        amzn)
            [[ "$VERSION" == 2 || "$VERSION" == 2023 ]] || log_warning "$os_not_supported_msg"
            ;;
        fedora)
            $is_arm && log_warning "$os_not_supported_msg" || (( VERSION >= 33 && VERSION <= 38 )) || log_warning "$os_not_supported_msg"
            ;;
        almalinux)
            $is_arm && log_warning "$os_not_supported_msg" || [[ "$major" == 8 && "$minor" -ge 4 || "$major" == 9 && "$minor" -ge 2 ]] || log_warning "$os_not_supported_msg"
            ;;
        rocky)
            $is_arm && log_warning "$os_not_supported_msg" || [[ "$major" == 8 && "$minor" -ge 7 || "$major" == 9 && "$minor" -ge 2 ]] || log_warning "$os_not_supported_msg"
            ;;
        mariner)
            $is_arm && log_warning "$os_not_supported_msg" || [[ "$VERSION" == 2 ]] || log_warning "$os_not_supported_msg"
            ;;
        *)
            log_warning "[!] Warning: unsupported distro $DISTRO $VERSION"
            ;;
    esac

    if is_newer_kernel "$CURRENT_KERNEL" "4.15"; then
        :
    elif [[ "$CURRENT_KERNEL" =~ ^3\.10\.0 ]] && is_newer_kernel "$CURRENT_KERNEL" "3.10.0-957.10"; then
        :
    else
        log_warning "[!] Warning: MDE with eBPF requires kernel version 4.15 or later but found $CURRENT_KERNEL."
    fi

    return 0
}

#Non-blocking
verify_fanotify_kernel_flags()
{
    # Will checks for the following flags:
    # CONFIG_FANOTIFY -> this flag controls support for the fanotify file access notification system in the Linux kernel
    # CONFIG_FANOTIFY_ACCESS_PERMISSIONS -> If enabled, fanotify can be run in blocking mode.
    # These are kernel flags and can't be changed during runtime.

    if [[ -z "$CURRENT_KERNEL" ]]; then
        log_warning "[!] Warning: Failed to get kernel version. Won't be able to get FANOTIFY kernel flags."
        return 0
    fi

    local kernel_config_file="/boot/config-${CURRENT_KERNEL}"

    if [[ ! -f "$kernel_config_file" ]]; then
        log_warning "[!] Warning: Kernel config file not found: $kernel_config_file"
        return 0
    fi

    declare -A fanotify_flags

    while IFS='=' read -r key value; do
        if [[ "$key" == *FANOTIFY* ]]; then
            fanotify_flags["$key"]="$value"
        fi
    done < "$kernel_config_file"

    # Check for required kernel options
    if [[ "${fanotify_flags[CONFIG_FANOTIFY]}" != "y" ]]; then
        log_warning "[!] Warning: Fanotify(CONFIG_FANOTIFY) is not enabled"
        echo "Fanotify(CONFIG_FANOTIFY) is not enabled"
        return 0
    fi

    if [[ "${fanotify_flags[CONFIG_FANOTIFY_ACCESS_PERMISSIONS]}" != "y" ]]; then
        log_warning "[!] Warning: CONFIG_FANOTIFY_ACCESS_PERMISSIONS is not enabled. Fanotify can't run in blocking mode."
    fi

    return 0
}

#Blocking
verify_glibc_version()
{
    # Check if ldd command is available (most common way to check glibc version)
    if ! command -v ldd >/dev/null 2>&1; then
        log_warning "[!] Warning: ldd command not found. Cannot verify glibc version."
        return 0
    fi
    
    # Get glibc version using ldd --version
    local glibc_version_output
    glibc_version_output=$(ldd --version 2>/dev/null | head -n1)
    
    if [ -z "$glibc_version_output" ]; then
        log_warning "[!] Warning: Failed to get glibc version."
        return 0
    fi
    
    # Extract version number from output (format: "ldd (GNU libc) 2.17" or similar)
    local current_glibc_version
    current_glibc_version=$(echo "$glibc_version_output" | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -n1)
    
    if [ -z "$current_glibc_version" ]; then
        log_warning "[!] Warning: Could not parse glibc version from: $glibc_version_output"
        return 0
    fi
    
    # Compare versions using version comparison
    if ! is_version_greater_or_equal "$current_glibc_version" "$MIN_GLIBC_VERSION"; then
        local msg="MDE requires glibc version $MIN_GLIBC_VERSION or later but found $current_glibc_version."
        log_error "[x] Error: $msg"
        echo "$msg"
        return 1
    fi
    
    return 0
}

# Helper function to compare version numbers
is_version_greater_or_equal()
{
    local current_version="$1"
    local required_version="$2"

    # Split versions into arrays
    IFS='.' read -ra current_parts <<< "$current_version"
    IFS='.' read -ra required_parts <<< "$required_version"

    # Pad arrays to same length
    local max_length=${#current_parts[@]}
    if [ ${#required_parts[@]} -gt $max_length ]; then
        max_length=${#required_parts[@]}
    fi
    
    while [ ${#current_parts[@]} -lt $max_length ]; do
        current_parts+=("0")
    done
    
    while [ ${#required_parts[@]} -lt $max_length ]; do
        required_parts+=("0")
    done
    
    # Compare each part
    for i in $(seq 0 $((max_length - 1))); do
        if [ "${current_parts[i]}" -lt "${required_parts[i]}" ]; then
            return 1  # current < required
        elif [ "${current_parts[i]}" -gt "${required_parts[i]}" ]; then
            return 0  # current > required
        fi
    done
    
    return 0  # versions are equal
}

verify_min_requirements()
{
    verify_system_specifications
    prereqs_passed=$?

    CURRENT_KERNEL=$(uname -r)

    verify_kernel_version
    (( prereqs_passed |= $? ))

    verify_glibc_version
    (( prereqs_passed |= $? ))

    verify_fanotify_kernel_flags
    (( prereqs_passed |= $? ))

    verify_filesystem_support
    (( prereqs_passed |= $? ))

    verify_supported_distros
    (( prereqs_passed |= $? ))

    if [ "$prereqs_passed" -ne 0 ]; then
        script_exit "Prerequisite check failed" "$ERR_INSUFFICIENT_REQUIREMENTS"
    else
        log_info "[v] All prerequisite passed"
    fi
}

find_service()
{
    if [ -z "$1" ]; then
        script_exit "INTERNAL ERROR. find_service requires an argument" $ERR_INTERNAL
    fi

	lines=$(systemctl status $1 2>&1 | grep "Active: active" | wc -l)
	
    if [ $lines -eq 0 ]; then
		return 1
	fi

	return 0
}

verify_mdatp_installed()
{
    op=$(command -v mdatp)
            #make sure mdatp is installed
    if [ ! -z $op ]; then
        #check if mdatp is onboarded or not
        check_missing_license=$(get_health_field "health_issues" | grep "missing license" -c)
        onboard_file=/etc/opt/microsoft/mdatp/mdatp_onboard.json
        if [ "$check_missing_license" -gt 0 ] || [ ! -f "$onboard_file" ]; then
            log_info "[i] MDE already installed but not onboarded. Please use --onboard command to onboard the product."
        else
            current_mdatp_version=$(get_health_field "app_version")
            org_id=$(get_health_field "org_id")          
            if [ ! -z "$MDE_VERSION" ]; then
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

    if [ ! -z "$conflicting_apps" ]; then
        if [ "$conflicting_apps" = "/opt/microsoft/mdatp/sbin/wdavdaemon" ]; then
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
    if [ "$DISTRO_FAMILY" = "debian" ]; then
        PKG_MGR=apt
        PKG_MGR_INVOKER="apt $(get_apt_proxy_params) $ASSUMEYES"
    elif [ "$DISTRO_FAMILY" = "fedora" ]; then
        # Check if dnf is available (used in RHEL 8+, CentOS 8+, Fedora, Oracle Linux 8+)
        if command -v dnf >/dev/null 2>&1; then
            PKG_MGR=dnf
            PKG_MGR_INVOKER="dnf $(get_dnf_yum_proxy_params) $ASSUMEYES"
        elif command -v yum >/dev/null 2>&1; then
            PKG_MGR=yum
            PKG_MGR_INVOKER="yum $(get_dnf_yum_proxy_params) $ASSUMEYES"
        fi
    elif [ "$DISTRO_FAMILY" = "mariner" ] || [ "$DISTRO_FAMILY" = "azurelinux" ]; then
        PKG_MGR=dnf
        PKG_MGR_INVOKER="dnf $(get_dnf_yum_proxy_params) $ASSUMEYES"
    elif [ "$DISTRO_FAMILY" = "sles" ]; then
        DISTRO="sles"
        PKG_MGR="zypper"
        PKG_MGR_INVOKER="zypper $(get_zypper_proxy_params) --non-interactive"
    else
        script_exit "unsupported distro", $ERR_UNSUPPORTED_DISTRO
    fi

    log_info "[v] set package manager: $PKG_MGR"
}

check_if_pkg_is_installed()
{
    if [ -z "$1" ]; then
        script_exit "INTERNAL ERROR. check_if_pkg_is_installed requires an argument" $ERR_INTERNAL
    fi

    if [ "$PKG_MGR" = "apt" ]; then
        dpkg -s $1 2> /dev/null | grep Status | grep "install ok installed" 1> /dev/null
    else
        # shellcheck disable=SC2046
        rpm --quiet --query $(get_rpm_proxy_params) $1
    fi

    return $?
}

check_if_device_is_onboarded()
{
    local onboarded
    onboarded=$(get_health_field "licensed")
    if [ "$onboarded" = "true" ]; then
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

    if [ "$DISTRO_FAMILY" = "debian" ]; then
        PKG_VERSION=$(dpkg -s mdatp | grep -i version)
    else
        PKG_VERSION=$(rpm -qi mdatp | grep -i version)
    fi

    if [ -z "$PKG_VERSION" ] && command -v mdatp >/dev/null 2>&1; then
        PKG_VERSION=$(get_health_field "app_version")
    fi

    echo $PKG_VERSION
}

get_mdatp_channel()
{
    local release_ring=""
    release_ring=$(mdatp health --field release_ring)
    local mdatp_exit_code=$?
    if [ "$mdatp_exit_code" = "0" ] && [ -n "$release_ring" ]; then
        release_ring=$(echo "$release_ring" | tail -n 1 | awk -F'"' '{print $2}')
    else
        install_log=/var/log/microsoft/mdatp/install.log
        if [ -e "$install_log" ]; then
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

    echo $channel
}

install_required_pkgs()
{
    local packages=()
    local pkgs_to_be_installed=
    local exit_on_failure=1  # Default: exit on failure

    if [ -z "$1" ]; then
        script_exit "INTERNAL ERROR. install_required_pkgs requires an argument" $ERR_INTERNAL
    fi

    if [[ "$1" == "--no-exit" ]]; then
        exit_on_failure=0
        shift 1  # Remove the flag from arguments
    fi

    packages=("$@")
    for pkg in "${packages[@]}"
    do
        if  ! check_if_pkg_is_installed $pkg; then
            pkgs_to_be_installed="$pkgs_to_be_installed $pkg"
        fi
    done

    if [ ! -z "$pkgs_to_be_installed" ]; then
        log_info "[>] installing $pkgs_to_be_installed"

        if [ "$exit_on_failure" -eq 1 ]; then
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

    while [ $counter -gt 0 ]
    do
        lines=$(ps axo pid,comm | grep "$PKG_MGR" | grep -v grep -c)
        if [ "$lines" -eq 0 ]; then
            log_debug "[>] package manager freed, resuming installation"
            return
        fi
        sleep 1
        ((counter--))
    done

    log_warning "[!] pkg_mgr blocked"
}

get_all_mde_version_from_channel()
{
    if [ -n "$ALL_MDE_VERSIONS" ]; then
        echo "$ALL_MDE_VERSIONS"
        return 0
    fi

    local search_command
    local cmd_status
    if [ "$PKG_MGR" = "apt" ]; then
        search_command='apt $(get_apt_proxy_params) $ASSUMEYES policy mdatp 2>/dev/null'
    elif [ "$PKG_MGR" = "yum" ]; then
        check_option="yum --help | grep '\-\-showduplicates' &> /dev/null"
        eval $check_option
        cmd_status=$?
        if [ $cmd_status -eq 0 ]; then
            search_command='yum $(get_dnf_yum_proxy_params) $ASSUMEYES -v list mdatp --showduplicates 2>/dev/null'
        else
            search_command='echo &>/dev/null'
        fi
    elif [ "$PKG_MGR" = "dnf" ]; then
        search_command='dnf $(get_dnf_yum_proxy_params) $ASSUMEYES search --showduplicates mdatp 2>/dev/null'
    elif [ "$PKG_MGR" = "zypper" ]; then
        search_command='zypper $(get_zypper_proxy_params) search -s mdatp 2>/dev/null'
    fi

    local channel_filter=""
    if [ "$1" = "insiders-fast" ]; then
        channel_filter="insiderfast"
    elif [ "$1" = "insiders-slow" ]; then
        channel_filter="external"
    fi

    local search_output
    search_output=$(eval $search_command 2>/dev/null)
    cmd_status=$?
    if [ "$cmd_status" -ne 0 ]; then
        ALL_MDE_VERSIONS=""
        echo ""
        return 1
    fi

    local versions
    if [ -n "$channel_filter" ]; then
        versions=$(echo "$search_output" | grep "$channel_filter" | grep -oP "101\.[0-9]{1,5}\.[0-9]{4}")
    else
        versions=$(echo "$search_output" | grep -vE "insiderfast|external" | grep -oP "101\.[0-9]{1,5}\.[0-9]{4}")
    fi

    if [ -z "$versions" ]; then
        ALL_MDE_VERSIONS=""
        echo ""
        return 1
    fi
    ALL_MDE_VERSIONS="$versions"
    echo "$ALL_MDE_VERSIONS"
    return 0
}

get_latest_versions_by_group() {
    local versions="$1"
    declare -A latest_versions

    # Process each version
    while IFS= read -r version; do
        local major minor patch
        # shellcheck disable=SC2034
        IFS='.' read -r major minor patch <<< "$version"
        local key="$major.$minor"

        # Update if it's the first time or patch is greater
        #if [[ -z "${latest_versions[$key]}" ]] || [[ "${version##*.}" -gt "${latest_versions[$key]##*.}" ]]; then
        if [[ -z "${latest_versions[$key]}" ]] || (( 10#${version##*.} > 10#${latest_versions[$key]##*.} )); then
            latest_versions[$key]="$version"
        fi
    done <<< "$versions"

    # Print sorted result
    for v in "${latest_versions[@]}"; do
        echo "$v"
    done | sort -V
}

get_nth_latest_mde_version_from_channel()
{
    local nth="$1"
    local all_versions
    all_versions=$(get_all_mde_version_from_channel "$2")
    if [ $? -ne "0" ]; then
        echo ""
        return 1
    fi

    local all_unique_versions
    all_unique_versions=$(get_latest_versions_by_group "$all_versions")
    if [ $? -ne "0" ] || [ -z "$all_unique_versions" ]; then
        echo ""
        return 1
    fi
    local nth_version
    nth_version=$(echo "$all_unique_versions" | sort -V | tail -n "$nth" | head -n 1)

    if [ -z "$nth_version" ]; then
        echo ""
        return 1
    fi

    echo "$nth_version"
}

get_latest_mde_version()
{
    local latest_version
    latest_version=$(get_nth_latest_mde_version_from_channel "1" "$CHANNEL")
    local ret=$?
    echo "$latest_version"
    return $ret
}

check_if_version_too_old()
{
    local requested_version="$1"

    # Get the 9th latest version
    local latest_nth_version
    latest_nth_version=$(get_nth_latest_mde_version_from_channel "$SUPPORTED_LAST_N_VERSIONS" "$CHANNEL") || return 0

    # Extract month from version (e.g., from 101.202405.0001 → 202405)
    local latest_nth_month
    latest_nth_month=$(echo "$latest_nth_version" | grep -oE '101\.[0-9]{1,5}\.[0-9]{4}' | cut -d '.' -f2)

    local requested_version_month
    requested_version_month=$(echo "$requested_version" | cut -d '.' -f2)

    # Ensure both are valid numbers
    if ! [[ "$latest_nth_month" =~ ^[0-9]+$ ]] || ! [[ "$requested_version_month" =~ ^[0-9]+$ ]]; then
        log_warning "[!] Warning: Failed to extract numeric month parts from version strings."
        return 0
    fi

    # Compare months
    if [ "$requested_version_month" -lt "$latest_nth_month" ]; then
        echo "$latest_nth_version"
        return 1
    fi

    return 0
}

exit_if_version_is_older()
{
    oldest_supported_version=$(check_if_version_too_old "$1")
    if [ $? -ne 0 ]; then
        script_exit "The requested MDE version is older than the oldest version [$oldest_supported_version] available within support window. Use newer MDE" $ERR_UNSUPPORTED_VERSION
    fi
}

validate_mde_version()
{
    if ! [[ "$MDE_VERSION" =~ ^101\.[0-9]{1,5}\.[0-9]{4}$ ]]; then
        echo ""
        return 1
    fi

    if [ -z "$SKIP_MDE_SUPPORT_WINDOW_CHECK" ] && [ -n "$PRE_REQ_CHECK" ]; then #Set as env variable
        exit_if_version_is_older "$MDE_VERSION"
    fi

    local sep='_'
    local suffix='-1'
    local prefix='-'
    if [ "$DISTRO_FAMILY" = "debian" ]; then
        sep='-'
        suffix=''
        prefix='='
    fi
    local version
    if [ "$CHANNEL" = "insiders-fast" ]; then
        version="${MDE_VERSION}${sep}insiderfast${suffix}"
    elif [ "$CHANNEL" = "insiders-slow" ]; then
        version="${MDE_VERSION}${sep}external${suffix}"
    else
        version="$MDE_VERSION"
    fi

    local search_command
    if [ "$PKG_MGR" = "apt" ]; then
        search_command='apt $(get_apt_proxy_params) $ASSUMEYES policy mdatp 2>/dev/null | grep "$version" &> /dev/null'
    elif [ "$PKG_MGR" = "yum" ]; then
        check_option="yum --help | grep '\-\-showduplicates' &> /dev/null"
        eval $check_option
        cmd_status=$?
        if [ $cmd_status -eq 0 ]; then
            search_command='yum $(get_dnf_yum_proxy_params) $ASSUMEYES -v list mdatp --showduplicates 2>/dev/null | grep "$version"  &> /dev/null'
        else
            search_command='echo &>/dev/null'
        fi
    elif [ "$PKG_MGR" = "dnf" ]; then
        search_command='dnf $(get_dnf_yum_proxy_params) $ASSUMEYES search --showduplicates mdatp -y 2>/dev/null | grep "$version"  &> /dev/null'
    elif [ "$PKG_MGR" = "zypper" ]; then
        search_command='zypper $(get_zypper_proxy_params) search -s mdatp 2>/dev/null | grep "$version"  &> /dev/null'
    fi

    eval $search_command
    if [ $? -eq 0 ]; then
        echo "${prefix}${version}"
    else
        echo ""
    fi
}

create_sym_link()
{
    local source_path="$1"
    local target_path="$2"

    if ! [ -d "$target_path" ]; then
        log_error "[x] Error: $target_path does not exist"
        return 1
    fi

    ## Check if source path's parent exists
    if ! [ -d "$(dirname "$source_path")" ]; then
        log_error "[x] Error: Parent directory of $source_path does not exist"
        return 2
    fi

    if [ -L "$source_path" ]; then
        log_debug "[i] Symlink already exists at $source_path"
        # Check if symlink is pointing to correct path
        if [ "$(readlink -f "$source_path")" = "$target_path" ]; then
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

    if [ -L "$source_path" ]; then
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
    if [ -n "$requested_version" ] && [ -n "$MDE_VERSION" ]; then
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
    if [ ! -d "$INSTALL_PATH" ]; then
        log_info "[>] INSTALL_PATH=$INSTALL_PATH does not exist, creating it."
        mkdir -p "$INSTALL_PATH" || script_exit "Failed to create directory $INSTALL_PATH" $ERR_INSTALL_PATH_SETUP
    fi
    
    local installation_path="$INSTALL_PATH/microsoft_mdatp"
    mkdir -p $installation_path || script_exit "Failed to create directory $installation_path" $ERR_INSTALL_PATH_SETUP
    chmod 755 "$installation_path" || script_exit "Failed to set permissions on $installation_path" $ERR_INSTALL_PATH_PERMISSIONS
    local mde_config_dir="/etc/opt/microsoft/mdatp"
    local mde_config_path="$mde_config_dir/mde_path.json"
    mkdir -p $mde_config_dir || script_exit "Failed to create directory mde_config_dir" $ERR_INSTALL_PATH_SETUP

    # Create a JSON file to set the installation path
    echo "{\"path\": \"$installation_path\"}" > $mde_config_path || script_exit "Failed to write installation path to JSON file" $ERR_INSTALL_PATH_SETUP
    chmod 644 $mde_config_path || script_exit "Failed to set permissions for JSON file" $ERR_INSTALL_PATH_PERMISSIONS

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

    run_quietly "apt-get $(get_apt_proxy_params) update" "[!] unable to refresh the repos properly"

    if [ -z "$SKIP_PMC_SETUP" ]; then 
        packages=(curl apt-transport-https gnupg)

        install_required_pkgs "${packages[@]}"

        ### Configure the repository ###
        log_info "[>] configuring the repository"

        rm -f microsoft.list > /dev/null
        run_quietly "curl -s -o microsoft.list $PMC_URL/$DISTRO/$SCALED_VERSION/$CHANNEL.list" "unable to fetch repo list" $ERR_FAILED_REPO_SETUP
        run_quietly "mv ./microsoft.list /etc/apt/sources.list.d/microsoft-$CHANNEL.list" "unable to copy repo to location" $ERR_FAILED_REPO_SETUP

        ### Fetch the gpg key ###

        if { [ "$DISTRO" = "ubuntu" ] && [ "$VERSION" = "24.04" ]; } || { [ "$DISTRO" = "debian" ] && [ "$VERSION" = "12" ]; }; then
            if [ ! -f /usr/share/keyrings/microsoft-prod.gpg ]; then
                run_quietly "curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | sudo gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg" "unable to fetch the gpg key" $ERR_FAILED_REPO_SETUP
            fi
        else
            run_quietly "curl -s https://packages.microsoft.com/keys/microsoft.asc | apt-key add -" "unable to fetch the gpg key" $ERR_FAILED_REPO_SETUP
        fi
        run_quietly "apt-get $(get_apt_proxy_params) update" "[!] unable to refresh the repos properly"
    else
        # Try to install/find curl, don't exit the script if it fails.
        packages=(curl)
        install_required_pkgs --no-exit "${packages[@]}"
    fi

    local version=""
    if [ ! -z "$MDE_VERSION" ]; then
        version=$(validate_mde_version)
        if [ -z "$version" ]; then
            script_exit "Couldn't find the version $MDE_VERSION for channel $CHANNEL. Aborting installion" $ERR_INSTALLATION_FAILED
        fi
    fi

    if [ -n "$INSTALL_PATH" ]; then
        validate_custom_path_installation_version $version  || script_exit "Custom Path installation is not supported on version $version, Minimum expected version : 101.25062.0003" $ERR_INSTALLATION_FAILED
        handle_custom_installation
    fi

    ### Install MDE ###
    log_info "[>] installing MDE"

    if [ -z "$CHANNEL" ]; then
        run_quietly "$PKG_MGR_INVOKER install mdatp$version" "unable to install MDE ($?)" $ERR_INSTALLATION_FAILED
    elif [ "$CHANNEL" = "prod" ]; then
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

    run_quietly "dnf $(get_dnf_yum_proxy_params) -y makecache" "[!] unable to refresh the repos properly"

    if [ -z "$SKIP_PMC_SETUP" ]; then 
        # To use config-manager plugin, install dnf-plugins-core package
        run_quietly "$PKG_MGR_INVOKER install dnf-plugins-core" "failed to install dnf-plugins-core"

        ### Configure the repository ###
        log_info "[>] configuring the repository"

        if [ "$CHANNEL" = "prod" ]; then
            run_quietly "$PKG_MGR_INVOKER install mariner-repos-extras" "unable to install mariner-repos-extras"
            run_quietly "$PKG_MGR_INVOKER config-manager --enable mariner-official-extras" "unable to enable extras repo"
            run_quietly "$PKG_MGR_INVOKER config-manager --disable mariner-official-extras-preview" "unable to disable extras-preview repo"
        elif [ "$CHANNEL" = "insiders-slow" ]; then
            ### Add Preview Repo File ###
            run_quietly "$PKG_MGR_INVOKER install mariner-repos-extras-preview" "unable to install mariner-repos-extras-preview"
            run_quietly "$PKG_MGR_INVOKER config-manager --enable mariner-official-extras-preview" "unable to enable extras-preview repo"
        else
            # mariner is only supported on prod and insiders-slow channels
            script_exit "Invalid channel: $CHANNEL. Available channels for $DISTRO_FAMILY are prod and insiders-slow channel only." $ERR_INVALID_CHANNEL
        fi
        run_quietly "dnf $(get_dnf_yum_proxy_params) -y makecache" "[!] unable to refresh the repos properly"
    fi

    local version=""
    if [ ! -z "$MDE_VERSION" ]; then
        version=$(validate_mde_version)
        if [ -z "$version" ]; then
            script_exit "Couldn't find the version $MDE_VERSION for channel $CHANNEL. Aborting installion" $ERR_INSTALLATION_FAILED
        fi
    fi

    if [ -n "$INSTALL_PATH" ]; then
        validate_custom_path_installation_version $version  || script_exit "Custom Path installation is not supported on version $version, Minimum expected version : 101.25062.0003" $ERR_INSTALLATION_FAILED
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

    run_quietly "dnf $(get_dnf_yum_proxy_params) -y makecache" "[!] unable to refresh the repos properly"

    if [ -z "$SKIP_PMC_SETUP" ]; then 
        # To use config-manager plugin, install dnf-plugins-core package
        run_quietly "$PKG_MGR_INVOKER install dnf-plugins-core" "failed to install dnf-plugins-core"

        ### Configure the repository ###
        log_info "[>] configuring the repository"

        if [ "$CHANNEL" = "prod" ]; then
            run_quietly "$PKG_MGR_INVOKER install azurelinux-repos-ms-non-oss" "unable to install azurelinux-repos-ms-non-oss"
            run_quietly "$PKG_MGR_INVOKER config-manager --enable azurelinux-repos-ms-non-oss" "unable to enable extras repo"
            run_quietly "$PKG_MGR_INVOKER config-manager --disable azurelinux-repos-ms-non-oss-preview" "unable to disable extras-preview repo"
        else
            ### Add Preview Repo File ###
            run_quietly "$PKG_MGR_INVOKER install azurelinux-repos-ms-non-oss-preview" "unable to install azurelinux-repos-ms-non-oss-preview"
        fi
        run_quietly "dnf $(get_dnf_yum_proxy_params) -y makecache" "[!] unable to refresh the repos properly"
    fi

    local version=""
    if [ ! -z "$MDE_VERSION" ]; then
        version=$(validate_mde_version)
        if [ -z "$version" ]; then
            script_exit "Couldn't find the version $MDE_VERSION for channel $CHANNEL. Aborting installion" $ERR_INSTALLATION_FAILED
        fi
    fi

    if [ -n "$INSTALL_PATH" ]; then
        validate_custom_path_installation_version $version  || script_exit "Custom Path installation is not supported on version $version, Minimum expected version : 101.25062.0003" $ERR_INSTALLATION_FAILED
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

    run_quietly "$PKG_MGR -y makecache" "[!] unable to refresh the repos properly"

    # curl-minimal results into issues when present and trying to install curl, so skip installing
    # the curl over Amazon Linux 2023
    if ! ([[ "$VERSION" == "2023" ]] && [[ "$DISTRO" == "amzn" ]] && check_if_pkg_is_installed curl-minimal); then
        packages=(curl)
    fi

    if [ -z "$SKIP_PMC_SETUP" ]; then
        if [ "$PKG_MGR" = "dnf" ]; then
            packages=("${packages[@]}" dnf-plugins-core)
        else
            packages=("${packages[@]}" yum-utils)
        fi

        if [[ $SCALED_VERSION == 7* ]] && [[ "$DISTRO" == "rhel" ]]; then
            packages=("${packages[@]}" deltarpm)
        fi

        install_required_pkgs "${packages[@]}"

        ### Configure the repo name from which package should be installed
        local repo_name=${repo}-${CHANNEL}
        local repo_channel="${CHANNEL#insiders-}"  
        case "$DISTRO:$SCALED_VERSION:$CHANNEL" in
            centos:8:insiders-slow | centos:8:insiders-fast)
                repo_name="packages-microsoft-com-${repo_channel}-prod"
                ;;
            rhel:7.2:insiders-slow | rhel:7.2:insiders-fast)
                repo_name="packages-microsoft-com-${repo_channel}-prod"
                ;;
            rhel:7.4:insiders-slow)
                repo_name="packages-microsoft-com-slow-prod"
                ;;
        esac

        if [ "$DISTRO" = "ol" ] || [ "$DISTRO" = "fedora" ]; then
            effective_distro="rhel"
        elif [ "$DISTRO" = "almalinux" ]; then
            effective_distro="alma"
        elif [ "$DISTRO" = "amzn" ]; then
            effective_distro="amazonlinux"
        else
            effective_distro="$DISTRO"
        fi

        # Configure repository if it does not exist
        $PKG_MGR -q repolist "$repo_name" | grep "$repo_name"
        found_repo=$?
        if [ $found_repo -eq 0 ]; then
            log_info "[i] repository already configured"
        else
            log_info "[>] configuring the repository"

            # Use appropriate config manager based on package manager
            if [ "$PKG_MGR" = "dnf" ]; then
                run_quietly "dnf $(get_dnf_yum_proxy_params) config-manager --add-repo=$PMC_URL/$effective_distro/$SCALED_VERSION/$CHANNEL.repo" "Unable to fetch the repo ($?)" $ERR_FAILED_REPO_SETUP
            else
                run_quietly "yum-config-manager --add-repo=$PMC_URL/$effective_distro/$SCALED_VERSION/$CHANNEL.repo" "Unable to fetch the repo ($?)" $ERR_FAILED_REPO_SETUP
            fi

            ### Fetch the gpg key ###
            run_quietly "curl https://packages.microsoft.com/keys/microsoft.asc > microsoft.asc" "unable to fetch gpg key $?" $ERR_FAILED_REPO_SETUP
            run_quietly "rpm $(get_rpm_proxy_params) --import microsoft.asc" "unable to import gpg key" $ERR_FAILED_REPO_SETUP
        fi

        run_quietly "$PKG_MGR $(get_dnf_yum_proxy_params) -y makecache" "[!] unable to refresh the repos properly"
    else
        # Try to install/find packages, don't exit the script if it fails.
        install_required_pkgs --no-exit "${packages[@]}"
    fi

    local version=""
    if [ ! -z "$MDE_VERSION" ]; then
        version=$(validate_mde_version)
        if [ -z "$version" ]; then
            script_exit "Couldn't find the version $MDE_VERSION for channel $CHANNEL. Aborting installion" $ERR_INSTALLATION_FAILED
        fi
    fi

    if [ -n "$INSTALL_PATH" ]; then
        validate_custom_path_installation_version $version  || script_exit "Custom Path installation is not supported on version $version, Minimum expected version : 101.25062.0003" $ERR_INSTALLATION_FAILED
        handle_custom_installation
    fi

    ### Install MDE ###
    log_info "[>] installing MDE"

    if [ "$ARCHITECTURE" = "aarch64" ] || [ -z "$repo_name" ]; then
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

    run_quietly "zypper $(get_zypper_proxy_params) --non-interactive refresh" "[!] unable to refresh the repos properly"

    packages=(curl)
    if [ -z "$SKIP_PMC_SETUP" ]; then 
        install_required_pkgs "${packages[@]}"

        wait_for_package_manager_to_complete

        ### Configure the repository ###
        local repo_name=${repo}-${CHANNEL}

        # add repository if it does not exist
        lines=$($PKG_MGR_INVOKER lr | grep "$repo_name" | wc -l)

        if [ $lines -eq 0 ]; then
            log_info "[>] configuring the repository"
            run_quietly "$PKG_MGR_INVOKER addrepo -c -f -n $repo_name https://packages.microsoft.com/config/$DISTRO/$SCALED_VERSION/$CHANNEL.repo" "unable to load repo" $ERR_FAILED_REPO_SETUP

            ### Fetch the gpg key ###
            run_quietly "rpm $(get_rpm_proxy_params) --import https://packages.microsoft.com/keys/microsoft.asc > microsoft.asc" "unable to fetch gpg key $?" $ERR_FAILED_REPO_SETUP
        else
            log_info "[i] repository already configured"
        fi

        run_quietly "zypper $(get_zypper_proxy_params) --non-interactive refresh" "[!] unable to refresh the repos properly"
    else
        # Try to install/find packages, don't exit the script if it fails.
        install_required_pkgs --no-exit "${packages[@]}"
        wait_for_package_manager_to_complete
    fi

    local version=""
    if [ ! -z "$MDE_VERSION" ]; then
        version=$(validate_mde_version)
        if [ -z "$version" ]; then
            script_exit "Couldn't find the version $MDE_VERSION for channel $CHANNEL. Aborting installion" $ERR_INSTALLATION_FAILED
        fi
    fi

    if [ ! -z "$INSTALL_PATH" ]; then
        validate_custom_path_installation_version $version  || script_exit "Custom Path installation is not supported on version $version, Minimum expected version : 101.25062.0003" $ERR_INSTALLATION_FAILED
        handle_custom_installation
    fi

    ### Install MDE ###
    log_info "[>] installing MDE"

    if [ -z "$repo_name" ]; then
        run_quietly "$PKG_MGR_INVOKER install $ASSUMEYES mdatp$version" "[!] failed to install MDE" $ERR_INSTALLATION_FAILED
    else
        run_quietly "$PKG_MGR_INVOKER install $ASSUMEYES ${repo_name}:mdatp$version" "[!] failed to install MDE" $ERR_INSTALLATION_FAILED
    fi

    sleep 5
    log_info "[v] Installation complete!"
}

remove_repo()
{
    # Remove mdatp if installed
    if check_if_pkg_is_installed mdatp; then
        current_channel=$(get_mdatp_channel)
        if [ "$CHANNEL" = "$current_channel" ]; then
            log_info "[i] MDE is installed for $CHANNEL"
            remove_mdatp
        fi
    fi

    log_info "[>] Removing repo for $CHANNEL"

    local cmd_status
    # Remove configured packages.microsoft.com repository
    if [ "$DISTRO" = "sles" ] || [ "$DISTRO" = "sle-hpc" ]; then
        local repo=packages-microsoft-com
        local repo_name=${repo}-${CHANNEL}

        run_quietly "$PKG_MGR_INVOKER removerepo $repo_name" "failed to remove repo"
    
    elif [ "$DISTRO_FAMILY" = "fedora" ]; then
        local repo=packages-microsoft-com
        local repo_name=${repo}-${CHANNEL}
        local repo_channel="${CHANNEL#insiders-}"  
        case "$DISTRO:$SCALED_VERSION:$CHANNEL" in
            centos:8:insiders-slow | centos:8:insiders-fast)
                repo_name="packages-microsoft-com-${repo_channel}-prod"
                ;;
            rhel:7.2:insiders-slow | rhel:7.2:insiders-fast)
                repo_name="packages-microsoft-com-${repo_channel}-prod"
                ;;
            rhel:7.4:insiders-slow)
                repo_name="packages-microsoft-com-slow-prod"
                ;;
        esac

        $PKG_MGR -q repolist $repo_name | grep "$repo_name" &> /dev/null
        cmd_status=$?
        if [ $cmd_status -eq 0 ]; then
            # Use appropriate config manager based on package manager
            if [ "$PKG_MGR" = "dnf" ]; then
                run_quietly "dnf config-manager --disable $repo_name" "Unable to disable the repo ($?)" $ERR_FAILED_REPO_CLEANUP
            else
                run_quietly "yum-config-manager --disable $repo_name" "Unable to disable the repo ($?)" $ERR_FAILED_REPO_CLEANUP
            fi
            run_quietly "find /etc/yum.repos.d -exec grep -lqR \"\[$repo_name\]\" '{}' \; -delete" "Unable to remove repo ($?)" $ERR_FAILED_REPO_CLEANUP
        else
            log_info "[i] nothing to clean up"
        fi
    
    elif [ "$DISTRO_FAMILY" = "debian" ]; then
        if [ -f "/etc/apt/sources.list.d/microsoft-$CHANNEL.list" ]; then
            run_quietly "rm -f '/etc/apt/sources.list.d/microsoft-$CHANNEL.list'" "unable to remove repo list ($?)" $ERR_FAILED_REPO_CLEANUP
        fi
    elif [ "$DISTRO_FAMILY" = "mariner" ]; then # in case of mariner, do not remove the repo
        log_info "[i] nothing to clean up"
        return
    else
        script_exit "unsupported distro for remove repo $DISTRO" $ERR_UNSUPPORTED_DISTRO
    fi

    log_info "[v] Repo removed for $CHANNEL"
}

upgrade_mdatp()
{
    if [ -z "$1" ]; then
        script_exit "INTERNAL ERROR. upgrade_mdatp requires an argument (the upgrade command)" $ERR_INTERNAL
    fi

    exit_if_mde_not_installed

    local VERSION_BEFORE_UPDATE VERSION_AFTER_UPDATE version current_version requested_version
    VERSION_BEFORE_UPDATE=$(get_mdatp_version)
    log_info "[i] Current $VERSION_BEFORE_UPDATE"

    local version=""
    if [ ! -z "$MDE_VERSION" ]; then
        version=$(validate_mde_version)
        if [ -z "$version" ]; then
            script_exit "Couldn't find the version $MDE_VERSION for channel $CHANNEL. Aborting upgrade" $ERR_INSTALLATION_FAILED
        fi
    fi

    current_version=$(echo "$VERSION_BEFORE_UPDATE" | sed 's/^[ \t\n]*//;s/[ \t\n]*$//' | awk '{print $NF}' | awk -F. '{ printf("%d%05d%05d\n", $1,$2,$3); }')
    requested_version=$(echo "$MDE_VERSION" | awk -F. '{ printf("%d%05d%05d\n", $1,$2,$3); }')

    if [[ "$INSTALL_MODE" == "d" && "$current_version" -lt "$requested_version" ]]; then
        script_exit "For downgrade the requested version[$MDE_VERSION] should be older than current version[$VERSION_BEFORE_UPDATE]"
    elif [[ "$INSTALL_MODE" == "u" && ! -z "$MDE_VERSION" && "$current_version" -gt "$requested_version" ]]; then
        script_exit "For upgrade the requested version[$MDE_VERSION] should be newer than current version[$VERSION_BEFORE_UPDATE]. If you want to move to an older version instead, retry with --downgrade flag"
    fi

    run_quietly "$PKG_MGR_INVOKER $1 mdatp$version" "Unable to upgrade MDE $?" $ERR_INSTALLATION_FAILED

    VERSION_AFTER_UPDATE=$(get_mdatp_version)
    if [ "$VERSION_BEFORE_UPDATE" = "$VERSION_AFTER_UPDATE" ]; then
        log_info "[i] MDE is already up to date."
    else
        # check install mode and log appropriate message
        if [[ "$INSTALL_MODE" == "d" ]]; then
            log_info "[v] downgrade successful!"
        else
            log_info "[v] upgrade successful!"
        fi
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
    if [ "$DISTRO_FAMILY" = "fedora" ]; then
        if [[ $VERSION == 6* ]]; then
            if rhel6_supported_version $VERSION; then # support versions 6.7+
                if [ "$DISTRO" = "centos" ] || [ "$DISTRO" = "rhel" ]; then
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
            if [[ $DISTRO == "almalinux" || $DISTRO == "rocky" ]]; then
                SCALED_VERSION=9
            else
                SCALED_VERSION=9.0
            fi
        elif [[ "$VERSION" == 10* ]] && [[ "$DISTRO" == "centos" || "$DISTRO" == "rhel" ]]; then
            SCALED_VERSION=10
        elif [[ $DISTRO == "amzn" ]] &&  [[ $VERSION == "2" || $VERSION == "2023" ]]; then # For Amazon Linux the scaled version is 2023 or 2
            SCALED_VERSION=$VERSION
        else
            script_exit "unsupported version: $DISTRO $VERSION" $ERR_UNSUPPORTED_VERSION
        fi
    elif [ "$DISTRO_FAMILY" = "mariner" ]; then
        if [[ $VERSION == 2* ]]; then
            SCALED_VERSION=2
        else
            script_exit "unsupported version: $DISTRO $VERSION" $ERR_UNSUPPORTED_VERSION
        fi
    elif [ "$DISTRO_FAMILY" = "azurelinux" ]; then
        if [[ $VERSION == 3* ]]; then
            SCALED_VERSION=3
        else
            script_exit "unsupported version: $DISTRO $VERSION" $ERR_UNSUPPORTED_VERSION
        fi
    elif [ "$DISTRO_FAMILY" = "sles" ]; then
        if [[ $VERSION == 12* ]]; then
            SCALED_VERSION=12
        elif [[ $VERSION == 15* ]]; then
            SCALED_VERSION=15
        else
            script_exit "unsupported version: $DISTRO $VERSION" $ERR_UNSUPPORTED_VERSION
        fi
    elif [[ $DISTRO == "ubuntu" ]] && [[ $VERSION != "16.04" ]] && [[ $VERSION != "18.04" ]] && [[ $VERSION != "20.04" ]] && [[ $VERSION != "22.04" ]] && [[ $VERSION != "24.04" ]]; then
        SCALED_VERSION=18.04
    else
        # no problems with 
        SCALED_VERSION=$VERSION
    fi
    log_info "[v] scaled: $SCALED_VERSION"
}

onboard_device()
{
    exit_if_mde_not_installed

    if check_if_device_is_onboarded; then
        log_info "[i] MDE already onboarded"
        return
    fi

    if [ ! -f $ONBOARDING_SCRIPT ]; then
        script_exit "error: onboarding script not found." $ERR_ONBOARDING_NOT_FOUND
    fi

    if [[ $ONBOARDING_SCRIPT == *.py ]]; then
        # Make sure python is installed
        PYTHON=$(which python 2>/dev/null || which python3 2>/dev/null)

        if [ $? -ne 0 ]; then
            script_exit "error: cound not locate python." $ERR_FAILED_DEPENDENCY
        fi

        #remove mdatp_offboard.json if present
        mdatp_offboard_file=/etc/opt/microsoft/mdatp/mdatp_offboard.json
        if [ -f "$mdatp_offboard_file" ]; then
            echo "found mdatp_offboard file"
            run_quietly "rm -f $mdatp_offboard_file" "error: failed to remove offboarding blob" $ERR_ONBOARDING_FAILED
            if [ ! -f "$mdatp_offboard_file" ]; then
                echo "removed mdatp_offboard file"
            else
                echo "failed to remove mdatp_offboard file"
            fi
        fi

        # Run onboarding script
        sleep 1
        run_quietly "$PYTHON $ONBOARDING_SCRIPT" "error: python onboarding failed" $ERR_ONBOARDING_FAILED

    elif [[ $ONBOARDING_SCRIPT == *.sh ]]; then        
        shebang_line=$(head -n 1 "$ONBOARDING_SCRIPT")
        if [[ "$shebang_line" == \#!* ]]; then
            interpreter_path=${shebang_line:2}
            run_quietly "$interpreter_path $ONBOARDING_SCRIPT" "error: $interpreter_path onboarding failed" $ERR_ONBOARDING_FAILED
        else
            run_quietly "sh $ONBOARDING_SCRIPT" "error: sh onboarding failed" $ERR_ONBOARDING_FAILED
        fi

    elif [[ $ONBOARDING_SCRIPT == *.json ]]; then
        local onboarding_dir=/etc/opt/microsoft/mdatp/
        if [ -d "$onboarding_dir" ]; then
            run_quietly "cp $ONBOARDING_SCRIPT $onboarding_dir/mdatp_onboard.json" "error: JSON onboarding failed" $ERR_ONBOARDING_FAILED
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

    if [ "$license_found" = "false" ]; then
        script_exit "onboarding failed" $ERR_ONBOARDING_FAILED
    fi

    log_info "[v] Onboarded"
}

offboard_device()
{
    exit_if_mde_not_installed

    if ! check_if_device_is_onboarded; then
        log_info "[i] MDE already offboarded"
        return
    fi

    if [ ! -f $OFFBOARDING_SCRIPT ]; then
        script_exit "error: offboarding script not found." $ERR_OFFBOARDING_NOT_FOUND
    fi
    local cmd_status
    if [[ $OFFBOARDING_SCRIPT == *.py ]]; then
        # Make sure python is installed
        PYTHON=$(which python || which python3)

        cmd_status=$?
        if [ $cmd_status -ne 0 ]; then
            script_exit "error: cound not locate python." $ERR_FAILED_DEPENDENCY
        fi

        # Run offboarding script
        sleep 1
        run_quietly "$PYTHON $OFFBOARDING_SCRIPT" "error: python offboarding failed" $ERR_OFFBOARDING_FAILED

    elif [[ $OFFBOARDING_SCRIPT == *.sh ]]; then        
        run_quietly "sh $OFFBOARDING_SCRIPT" "error: bash offboarding failed" $ERR_OFFBOARDING_FAILED

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

    if [ "$license_found" = "true" ]; then
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
        if [ "$tag_key" = "GROUP" ] || [ "$tag_key" = "SecurityWorkspaceId" ] || [ "$tag_key" = "AzureResourceId" ] || [ "$tag_key" = "SecurityAgentId" ]; then
            set_tags=$(get_health_field edr_device_tags)
            tag_exists=0

            result=$(echo "$set_tags" | grep -q "\"key\":\"$tag_key\""; echo "$?")
            if [ $result -eq 0 ]; then
                value=$(echo "$set_tags" | grep -o "\"key\":\"$tag_key\".*\"" | cut -d '"' -f 8)
                if [ "$value" = "$tag_value" ]; then
                    log_warning "[i] tag $tag_key already set to value $tag_value"
                    tag_exists=1
                fi
            fi

            if [ $tag_exists -eq 0 ]; then
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
    echo " -m|--min_req(deprecated) enforce minimum requirements. Its enabled by default. Will be removed in future"
    echo " -q|--pre-req         enforce prerequsiste for MDE like memoery, disk, etc."
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

#__MAIN__

if [ $# -eq 0 ]; then
    usage
    script_exit "no arguments were provided. specify --help for details" $ERR_INVALID_ARGUMENTS
fi

while [ $# -ne 0 ];
do
    case "$1" in
        -c|--channel)
            if [ -z "$2" ]; then
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
            if [ -z "$2" ]; then
                script_exit "$1 option requires an argument" $ERR_INVALID_ARGUMENTS
            fi
            ONBOARDING_SCRIPT=$2
            verify_privileges "onboard"
            shift 2
            ;;
        -f|--offboard)
            if [ -z "$2" ]; then
                script_exit "$1 option requires an argument" $ERR_INVALID_ARGUMENTS
            fi        
            OFFBOARDING_SCRIPT=$2
            verify_privileges "offboard"
            shift 2
            ;;
        -m|--min_req) # Making this No-op argument as removing this may break exisiting users
            echo "[!] Warning: option <-m/--min_req> is deprecated. Use <-q/--pre-req>. Will be removed in future"
            shift 1
            ;;
        -q|--pre-req)
            PRE_REQ_CHECK=1
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
                INSTALL_PATH=$(realpath "$2") || script_exit "Failed to resolve absolute path for $2" $ERR_INVALID_ARGUMENTS
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
    if [ "$INSTALLED_MDE_CHANNEL" != "$CHANNEL" ] && [ "$INSTALL_MODE" != 'c' ]; then
        if [ ! -z "$CHANNEL" ]; then
            echo "[i] MDE Installed with $INSTALLED_MDE_CHANNEL. Cannot switch channel to $CHANNEL. Channel is being set to $INSTALLED_MDE_CHANNEL. To update chanel remove and re-install MDE with $CHANNEL"
        fi
        CHANNEL=$INSTALLED_MDE_CHANNEL
    fi
fi

if [[ -z "${INSTALL_MODE}" && -z "${ONBOARDING_SCRIPT}" && -z "${OFFBOARDING_SCRIPT}" && -z "${PASSIVE_MODE}" && -z "${RTP_MODE}" && ${#tags[@]} -eq 0 ]]; then
    script_exit "no installation mode specified. Specify --help for help" $ERR_INVALID_ARGUMENTS
fi

# Check for mutually exclusive options
if [ ! -z "$PASSIVE_MODE" ] && [ ! -z "$RTP_MODE" ]; then
    echo "Options --passive-mode and --rtp-mode are mutually exclusive."
    usage
    exit 1
fi

if [ ! -z "$SKIP_PMC_SETUP" ]; then
    if [ "$INSTALL_MODE" == 'c' ]; then
        script_exit "--clean repo option is not supported with --use-local-repo" $ERR_INVALID_ARGUMENTS
    fi

    if [ ! -z "$CHANNEL" ]; then
        script_exit "--use-local-repo option is not supported with --channel" $ERR_INVALID_ARGUMENTS
    fi
else
    if [ -z "$CHANNEL" ]; then
        if [ "$INSTALL_MODE" == 'i' ]; then
            log_info "[i] Specify the install channel using \"--channel\" argument. If not provided, mde will be installed for prod by default. Expected channel values: prod, insiders-slow, insiders-fast."
        elif [ "$INSTALL_MODE" == 'c' ]; then
            log_info "[i] Specify the cleanup channel using \"--channel\" argument. If not provided, prod repo will be cleaned up by default. Expected channel values: prod, insiders-slow, insiders-fast."
        fi
        CHANNEL=prod
    fi
fi

if [[ "$INSTALL_MODE" == 'd' && -z "$MDE_VERSION" ]]; then
    script_exit "Specify the mdatp version using --mdatp argument when using --downgrade option" $ERR_INVALID_ARGUMENTS
fi

if [[ ! -z "$INSTALL_PATH" && "$INSTALL_MODE" != 'i' ]]; then
    script_exit "install path is only supported for installation" $ERR_INVALID_ARGUMENTS
fi

if [[ -z "$MDE_VERSION" && ( "$INSTALL_MODE" == 'i' || "$INSTALL_MODE" == 'u' ) ]]; then
    log_info "[i] Specify the version to be installed using \"--mdatp\" argument. If not provided, latest mde will be installed by default."
fi


# echo "--- mde_installer.sh v$SCRIPT_VERSION ---"
log_info "--- mde_installer.sh v$SCRIPT_VERSION ---"

## Detect the architecture type
detect_arch

### Detect the distro and version number ###
detect_distro

### Scale the version number according to repos avaiable on pmc ###
scale_version_id

### Set package manager ###
set_package_manager

### Validate mininum requirements ###
if [ "$INSTALL_MODE" = "i" ] && [ -n "$PRE_REQ_CHECK" ]; then
    verify_min_requirements
fi

# Log proxy configuration if set
if [[ -n "$http_proxy" || -n "$https_proxy" ]]; then
    log_info "[v] Proxy configuration set"
fi

### Act according to arguments ###
if [ "$INSTALL_MODE" = "i" ]; then

    if ! skip_if_mde_installed; then

        if [ -z $SKIP_CONFLICTING_APPS ]; then
            verify_conflicting_applications
        fi

        if [ "$DISTRO_FAMILY" = "debian" ]; then
            install_on_debian
        elif [ "$DISTRO_FAMILY" = "fedora" ]; then
            install_on_fedora
        elif [ "$DISTRO_FAMILY" = "mariner" ]; then
            install_on_mariner
        elif [ "$DISTRO_FAMILY" = "azurelinux" ]; then
            install_on_azurelinux
        elif [ "$DISTRO_FAMILY" = "sles" ]; then
            install_on_sles
        else
            script_exit "unsupported distro $DISTRO $VERSION" $ERR_UNSUPPORTED_DISTRO
        fi
    fi

elif [ "$INSTALL_MODE" = "u" ]; then

    if [ "$DISTRO_FAMILY" = "debian" ]; then
        upgrade_mdatp "$ASSUMEYES install --only-upgrade"
    elif [ "$DISTRO_FAMILY" = "fedora" ]; then
        upgrade_mdatp "$ASSUMEYES update"
    elif [ "$DISTRO_FAMILY" = "mariner" ]; then
        upgrade_mdatp "$ASSUMEYES update"
    elif [ "$DISTRO_FAMILY" = "azurelinux" ]; then
        upgrade_mdatp "$ASSUMEYES update"
    elif [ "$DISTRO_FAMILY" = "sles" ]; then
        upgrade_mdatp "up $ASSUMEYES"
    else    
        script_exit "unsupported distro $DISTRO $VERSION" $ERR_UNSUPPORTED_DISTRO
    fi

elif [ "$INSTALL_MODE" = "d" ]; then

    if [ "$DISTRO_FAMILY" = "debian" ]; then
        upgrade_mdatp "$ASSUMEYES install --allow-downgrades"
    elif [ "$DISTRO_FAMILY" = "fedora" ]; then
        upgrade_mdatp "$ASSUMEYES downgrade"
    elif [ "$DISTRO_FAMILY" = "mariner" ]; then
        upgrade_mdatp "$ASSUMEYES downgrade"
    elif [ "$DISTRO_FAMILY" = "azurelinux" ]; then
        upgrade_mdatp "$ASSUMEYES downgrade"
    elif [ "$DISTRO_FAMILY" = "sles" ]; then
        upgrade_mdatp "install --oldpackage $ASSUMEYES"
    else
        script_exit "unsupported distro $DISTRO $VERSION" $ERR_UNSUPPORTED_DISTRO
    fi

elif [ "$INSTALL_MODE" = "r" ]; then
    if remove_mdatp; then
        script_exit "removed MDE" $SUCCESS
    fi

elif [ "$INSTALL_MODE" = "c" ]; then
    if remove_repo; then
        script_exit "removed repo" $SUCCESS
    fi
fi

if [ ! -z $PASSIVE_MODE ]; then
    set_epp_to_passive_mode
elif [ ! -z $RTP_MODE ]; then
    set_epp_to_rtp_mode
fi

if [ ! -z $ONBOARDING_SCRIPT ]; then
    onboard_device
fi

if [ ! -z $OFFBOARDING_SCRIPT ]; then
    offboard_device
fi

if [ ${#tags[@]} -gt 0 ]; then
    set_device_tags
fi

script_exit "--- mde_installer.sh ended. ---" $SUCCESS
