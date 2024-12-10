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

SCRIPT_VERSION="0.7.0" # MDE installer version set this to track the changes in the script used by tools like ansible, MDC etc.
ASSUMEYES=-y
CHANNEL=
MDE_VERSION=
DISTRO=
DISTRO_FAMILY=
ARCHITECTURE=
PKG_MGR=
INSTALL_MODE=
DEBUG=
VERBOSE=
MDE_VERSION_CMD="mdatp health --field app_version"
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
declare -a tags

# Error codes
SUCCESS=0
ERR_INTERNAL=1
ERR_INVALID_ARGUMENTS=2
ERR_INSUFFICIENT_PRIVILAGES=3
ERR_NO_INTERNET_CONNECTIVITY=4
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
ERR_UNSUPPORTED_ARCH=45

# Predefined values
export DEBIAN_FRONTEND=noninteractive

_log() {
    level="$1"
    dest="$2"
    msg="${@:3}"
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

    if [ -n $DEBUG ]; then
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
	    exit $2
    fi
}

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
   cat <<EOF | /usr/bin/env $(get_python)
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

run_quietly()
{
    # run_quietly <command> <error_msg> [<error_code>]
    # use error_code for script_exit

    if [ $# -lt 2 ] || [ $# -gt 3 ]; then
        log_error "[!] INTERNAL ERROR. run_quietly requires 2 or 3 arguments"
        exit 1
    fi

    local out=$(eval $1 2>&1; echo "$?")
    local exit_code=$(echo "$out" | tail -n1)

    if [ -n "$VERBOSE" ]; then
        log_info "$out"
    fi
    
    if [ "$exit_code" -ne 0 ]; then
        if [ -n $DEBUG ]; then             
            log_debug "[>] Running command: $1"
            log_debug "[>] Command output: $out"
            log_debug "[>] Command exit_code: $exit_code"
        fi

        if [ $# -eq 2 ]; then
            log_error $2
        else
            script_exit "$2" "$3"
        fi
    fi

    return $exit_code
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

print_state()
{
    if [ -z $(which mdatp) ]; then
        log_warning "[S] MDE not installed."
    else
        log_info "[S] MDE installed."
        if run_quietly "mdatp health" "[S] Could not connect to the daemon -- MDE is not ready to connect yet."; then
            log_info "[S] Version: $($MDE_VERSION_CMD)"
            log_info "[S] Onboarded: $(mdatp health --field licensed)"
            log_info "[S] Passive mode: $(mdatp health --field passive_mode_enabled)"
            log_info "[S] Device tags: $(mdatp health --field edr_device_tags)"
            log_info "[S] Subsystem: $(mdatp health --field real_time_protection_subsystem)"
            log_info "[S] Conflicting applications: $(mdatp health --field conflicting_applications)"
        fi
    fi
}

detect_arch()
{
    arch=$(uname -m)
    ARCHITECTURE=$arch
    log_info "[>] detected: $ARCHITECTURE architecture"
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
    if [ "$DISTRO" == "linuxmint" ]; then
        DISTRO="ubuntu"
    fi

    if [ "$DISTRO" == "debian" ] || [ "$DISTRO" == "ubuntu" ]; then
        DISTRO_FAMILY="debian"
    elif [ "$DISTRO" == "rhel" ] || [ "$DISTRO" == "centos" ] || [ "$DISTRO" == "ol" ] || [ "$DISTRO" == "fedora" ] || [ "$DISTRO" == "amzn" ] || [ "$DISTRO" == "almalinux" ] || [ "$DISTRO" == "rocky" ]; then
        DISTRO_FAMILY="fedora"
    elif [ "$DISTRO" == "mariner" ]; then
        DISTRO_FAMILY="mariner"
    elif [ "$DISTRO" == "sles" ] || [ "$DISTRO" == "sle-hpc" ] || [ "$DISTRO" == "sles_sap" ]; then
        DISTRO_FAMILY="sles"
    else
        script_exit "unsupported distro $DISTRO $VERSION" $ERR_UNSUPPORTED_DISTRO
    fi

    log_info "[>] detected: $DISTRO $VERSION $VERSION_NAME ($DISTRO_FAMILY)"
}

check_arm_distro_support()
{
    FILE="/etc/mde.arm.d/mde.conf"
    if [ -f $FILE ]; then
        . "$FILE"
    fi
    log_info "[>] OPT_FOR_MDE_ARM_PREVIEW: $OPT_FOR_MDE_ARM_PREVIEW"
    if [ "$ARCHITECTURE" == "aarch64" ]; then
        if [ "$DISTRO" != "ubuntu" ] && [ "$DISTRO" != "amzn" ]; then
            script_exit "ARM architecture is not supported on $DISTRO" $ERR_UNSUPPORTED_ARCH
        elif [ "$DISTRO" == "ubuntu" ] && [ "$VERSION" != "20.04" ] && [ "$VERSION" != "22.04" ]; then
            script_exit "ARM architecture is not supported on Ubuntu versions other than 20.04 or 22.04" $ERR_UNSUPPORTED_ARCH
        elif [ "$DISTRO" == "amzn" ] && [ "$VERSION" != "2" ] && [ "$VERSION" != "2023" ]; then
            script_exit "ARM architecture is not supported on Amazon Linux versions other than 2 or 2023" $ERR_UNSUPPORTED_ARCH
        fi
    fi

    ### ARM is released only on insiders slow channel channel
    if [ "$OPT_FOR_MDE_ARM_PREVIEW" == "true" ] || [ "$OPT_FOR_MDE_ARM_PREVIEW" == "1" ]; then
        CHANNEL="insiders-slow"
        log_info "[>] Your distribution is supported by MDE for ARM Linux"
    elif [ "$CHANNEL" == "insiders-slow" ]; then
        log_info "[>] Your distribution is supported by MDE for ARM Linux"
    else
        script_exit "ARM architecture is not supported on $DISTRO" $ERR_UNSUPPORTED_ARCH
    fi

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

    if [ $(id -u) -ne 0 ]; then
        script_exit "root privileges required to perform $1 operation" $ERR_INSUFFICIENT_PRIVILAGES
    fi
}

verify_min_requirements()
{
    # echo "[>] verifying minimal reuirements: $MIN_CORES cores, $MIN_MEM_MB MB RAM, $MIN_DISK_SPACE_MB MB disk space"
    
    local cores=$(nproc --all)
    if [ $cores -lt $MIN_CORES ]; then
        script_exit "MDE requires $MIN_CORES cores or more to run, found $cores." $ERR_INSUFFICIENT_REQUIREMENTS
    fi

    local mem_mb=$(free -m | grep Mem | awk '{print $2}')
    if [ $mem_mb -lt $MIN_MEM_MB ]; then
        script_exit "MDE requires at least $MIN_MEM_MB MB of RAM to run. found $mem_mb MB." $ERR_INSUFFICIENT_REQUIREMENTS
    fi

    local disk_space_mb=$(df -m . | tail -1 | awk '{print $4}')
    if [ $disk_space_mb -lt $MIN_DISK_SPACE_MB ]; then
        script_exit "MDE requires at least $MIN_DISK_SPACE_MB MB of free disk space for installation. found $disk_space_mb MB." $ERR_INSUFFICIENT_REQUIREMENTS
    fi

    log_info "[v] minimal requirements met"
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
        check_missing_license=$(mdatp health --field health_issues | grep "missing license" -c)
        onboard_file=/etc/opt/microsoft/mdatp/mdatp_onboard.json
        if ([ $check_missing_license -gt 0 ]) || ([ ! -f "$onboard_file" ]); then
            log_info "[i] MDE already installed but not onboarded. Please use --onboard command to onboard the product."
        else
            current_mdatp_version=$($MDE_VERSION_CMD | tail -1)
            org_id=$(mdatp health --field org_id | tail -1)           
            if [ ! -z "$MDE_VERSION" ]; then
                local current_version=$(echo "$current_mdatp_version" | sed 's/"//' | awk '{print $NF}' | awk -F. '{ printf("%d%05d%05d\n", $1,$2,$3); }')
                local requested_version=$(echo "$MDE_VERSION" | awk -F. '{ printf("%d%05d%05d\n", $1,$2,$3); }')
                echo "[$current_mdatp_version]"
                echo "[$current_version]"
                echo "[$requested_version]"

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
    # echo "[>] identifying conflicting applications (fanotify mounts)"

    # find applications that are using fanotify
    local conflicting_apps=$(timeout 5m find /proc/*/fdinfo/ -type f -print0 2>/dev/null | xargs -r0 grep -Fl "fanotify mnt_id" 2>/dev/null | xargs -I {} -r sh -c 'cat "$(dirname {})/../cmdline"')
    
    if [ ! -z $conflicting_apps ]; then

        if [ $conflicting_apps == "/opt/microsoft/mdatp/sbin/wdavdaemon" ]; then
            verify_mdatp_installed 
        else
            script_exit "found conflicting applications: [$conflicting_apps], aborting" $ERR_CONFLICTING_APPS
        fi

    fi

    # find known security services
    # | Vendor      | Service       |
    # |-------------|---------------|
    # | CrowdStrike | falcon-sensor |
    # | CarbonBlack | cbsensor      |
    # | McAfee      | MFEcma        |
    # | Trend Micro | ds_agent      |

    local conflicting_services=('ds_agent' 'falcon-sensor' 'cbsensor' 'MFEcma')
    for t in "${conflicting_services[@]}"
    do
        set -- $t
        # echo "[>] locating service: $1"
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
        PKG_MGR_INVOKER="apt $ASSUMEYES"
    elif [ "$DISTRO_FAMILY" = "fedora" ]; then
        PKG_MGR=yum
        PKG_MGR_INVOKER="yum $ASSUMEYES"
    elif [ "$DISTRO_FAMILY" = "mariner" ]; then
        PKG_MGR=dnf
        PKG_MGR_INVOKER="dnf $ASSUMEYES"
    elif [ "$DISTRO_FAMILY" = "sles" ]; then
        DISTRO="sles"
        PKG_MGR="zypper"
        PKG_MGR_INVOKER="zypper --non-interactive"
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
        rpm --quiet --query $(get_rpm_proxy_params) $1
    fi

    return $?
}

get_mdatp_version()
{
    local PKG_VERSION=""

    if [ "$DISTRO_FAMILY" = "debian" ]; then
        PKG_VERSION=$(dpkg -s mdatp | grep -i version)
    else
        PKG_VERSION=$(rpm -qi mdatp | grep -i version)
    fi

    echo $PKG_VERSION
}

install_required_pkgs()
{
    local packages=
    local pkgs_to_be_installed=

    if [ -z "$1" ]; then
        script_exit "INTERNAL ERROR. install_required_pkgs requires an argument" $ERR_INTERNAL
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
        run_quietly "$PKG_MGR_INVOKER install $pkgs_to_be_installed" "Unable to install the required packages ($?)" $ERR_FAILED_DEPENDENCY 
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
        search_command='apt $ASSUMEYES policy mdatp 2>/dev/null | grep "$version" &> /dev/null'
    elif [ "$PKG_MGR" = "yum" ]; then
        check_option="yum --help | grep '\-\-showduplicates' &> /dev/null"
        eval $check_option
        if [ $? -eq 0 ]; then
            search_command='yum $ASSUMEYES -v list mdatp --showduplicates 2>/dev/null | grep "$version"  &> /dev/null'
        else
            search_command='echo &>/dev/null'
        fi
    elif [ "$PKG_MGR" = "dnf" ]; then
        search_command='dnf $ASSUMEYES search --showduplicates mdatp -y 2>/dev/null | grep "$version"  &> /dev/null'
    elif [ "$PKG_MGR" = "zypper" ]; then
        search_command='zypper search -s mdatp $ASSUMEYES 2>/dev/null | grep "$version"  &> /dev/null'
    fi

    eval $search_command
    if [ $? -eq 0 ]; then
        echo "${prefix}${version}"
    else
        echo ""
    fi
}

install_on_debian()
{
    local packages=
    local pkg_version=
    local success=

    if check_if_pkg_is_installed mdatp; then
        pkg_version=$($MDE_VERSION_CMD) || script_exit "unable to fetch the app version. please upgrade to latest version $?" $ERR_INTERNAL
        log_info "[i] MDE already installed ($pkg_version)."
        return
    fi

    packages=(curl apt-transport-https gnupg)

    install_required_pkgs ${packages[@]}

    ### Configure the repository ###
    rm -f microsoft.list > /dev/null
    run_quietly "curl -s -o microsoft.list $PMC_URL/$DISTRO/$SCALED_VERSION/$CHANNEL.list" "unable to fetch repo list" $ERR_FAILED_REPO_SETUP
    run_quietly "mv ./microsoft.list /etc/apt/sources.list.d/microsoft-$CHANNEL.list" "unable to copy repo to location" $ERR_FAILED_REPO_SETUP

    ### Fetch the gpg key ###
    run_quietly "curl -s https://packages.microsoft.com/keys/microsoft.asc | apt-key add -" "unable to fetch the gpg key" $ERR_FAILED_REPO_SETUP
    run_quietly "apt-get update" "[!] unable to refresh the repos properly"

    local version=""
    if [ ! -z "$MDE_VERSION" ]; then
        version=$(validate_mde_version)
        if [ -z "$version" ]; then
            script_exit "Couldn't find the version $MDE_VERSION for channel $CHANNEL. Aborting installion" $ERR_INSTALLATION_FAILED
        fi
    fi

    ### Install MDE ###
    log_info "[>] installing MDE"
    if [ "$CHANNEL" = "prod" ]; then
        if [[ -z "$VERSION_NAME" ]]; then
            run_quietly "$PKG_MGR_INVOKER install mdatp$version" "unable to install MDE ($?)" $ERR_INSTALLATION_FAILED
        else
            run_quietly "$PKG_MGR_INVOKER -t $VERSION_NAME install mdatp$version" "unable to install MDE ($?)" $ERR_INSTALLATION_FAILED
        fi
    else
        run_quietly "$PKG_MGR_INVOKER -t $CHANNEL install mdatp$version" "unable to install MDE ($?)" $ERR_INSTALLATION_FAILED
    fi

    sleep 5
    log_info "[v] installed"
}

install_on_mariner()
{
    local packages=
    local pkg_version=
    local repo=
    local effective_distro=

    if check_if_pkg_is_installed mdatp; then
        pkg_version=$($MDE_VERSION_CMD) || script_exit "Unable to fetch the app version. Please upgrade to latest version $?" $ERR_INSTALLATION_FAILED
        log_info "[i] MDE already installed ($pkg_version)"
        return
    fi

    # To use config-manager plugin, install dnf-plugins-core package
    run_quietly "$PKG_MGR_INVOKER install dnf-plugins-core" "failed to install dnf-plugins-core"

    ### Install MDE ###
    log_info "[>] installing MDE"
    if [ "$CHANNEL" = "prod" ]; then
        run_quietly "$PKG_MGR_INVOKER install mariner-repos-extras" "unable to install mariner-repos-extras"
        run_quietly "$PKG_MGR_INVOKER config-manager --enable mariner-official-extras" "unable to enable extras repo"
        run_quietly "$PKG_MGR_INVOKER config-manager --disable mariner-official-extras-preview" "unable to disable extras-preview repo"
    else
        ### Add Preview Repo File ###
        run_quietly "$PKG_MGR_INVOKER install mariner-repos-extras-preview" "unable to install mariner-repos-extras-preview"
        run_quietly "$PKG_MGR_INVOKER config-manager --enable mariner-official-extras-preview" "unable to enable extras-preview repo"
    fi

    local version=""
    if [ ! -z "$MDE_VERSION" ]; then
        version=$(validate_mde_version)
        if [ -z "$version" ]; then
            script_exit "Couldn't find the version $MDE_VERSION for channel $CHANNEL. Aborting installion" $ERR_INSTALLATION_FAILED
        fi
    fi
    run_quietly "$PKG_MGR_INVOKER install mdatp$version" "unable to install MDE ($?)" $ERR_INSTALLATION_FAILED

    sleep 5
    log_info "[v] installed"
}

install_on_fedora()
{
    local packages=
    local pkg_version=
    local repo=packages-microsoft-com
    local effective_distro=

    if check_if_pkg_is_installed mdatp; then
        pkg_version=$($MDE_VERSION_CMD) || script_exit "Unable to fetch the app version. Please upgrade to latest version $?" $ERR_INSTALLATION_FAILED
        log_info "[i] MDE already installed ($pkg_version)"
        return
    fi

    # curl-minimal results into issues when present and trying to install curl, so skip installing
    # the curl over Amazon Linux 2023
    if [[ "$VERSION" == "2023" ]] && [[ "$DISTRO" == "amzn" ]] && $(check_if_pkg_is_installed curl-minimal); then
        packages=(yum-utils)
    else
        packages=(curl yum-utils)
    fi

    if [[ $SCALED_VERSION == 7* ]] && [ "$DISTRO" == "rhel" ]; then
        packages=($packages deltarpm)
    fi

    install_required_pkgs ${packages[@]}

    ### Configure the repo name from which package should be installed
    local repo_name=${repo}-${CHANNEL}

    if [[ $SCALED_VERSION == 7* ]] && [[ "$CHANNEL" != "prod" ]]; then
        repo_name=packages-microsoft-com-prod-${CHANNEL}
    fi

    if [ "$CHANNEL" == "insiders-slow" ] && [ "$DISTRO" != "rocky" ] && [ "$DISTRO" != "almalinux" ] && ! { [ "$DISTRO" == "rhel" ] && [[ "$SCALED_VERSION" == 9* ]]; }; then  # in case of insiders slow repo [except rocky and alma], the repo name is packages-microsoft-com-slow-prod
        #repo_name=${repo}-slow-prod
        repo_name=packages-microsoft-com-insiders-slow
    fi

    if [ "$DISTRO" == "ol" ] || [ "$DISTRO" == "fedora" ] || [ "$DISTRO" == "amzn" ]; then
        effective_distro="rhel"
    elif [ "$DISTRO" == "almalinux" ]; then
        effective_distro="alma"
    else
        effective_distro="$DISTRO"
    fi

    if [ "$ARCHITECTURE" == "aarch64" ]; then
        if [ "$DISTRO" == "amzn" ]; then
            effective_distro="amazonlinux"
            SCALED_VERSION=$VERSION
        fi
        log_info "[i] configuring the repository for ARM architecture"
        run_quietly "yum-config-manager --add-repo=$PMC_URL/$effective_distro/$SCALED_VERSION/$CHANNEL.repo" "Unable to fetch the repo ($?)" $ERR_FAILED_REPO_SETUP

        ### Fetch the gpg key ###
        run_quietly "curl https://packages.microsoft.com/keys/microsoft.asc > microsoft.asc" "unable to fetch gpg key $?" $ERR_FAILED_REPO_SETUP
        run_quietly "rpm $(get_rpm_proxy_params) --import microsoft.asc" "unable to import gpg key" $ERR_FAILED_REPO_SETUP
    else

        # Configure repository if it does not exist
        yum -q repolist $repo_name | grep "$repo_name"
        found_repo=$?
        if [ $found_repo -eq 0 ]; then
            log_info "[i] repository already configured"
        else
            log_info "[i] configuring the repository"
            run_quietly "yum-config-manager --add-repo=$PMC_URL/$effective_distro/$SCALED_VERSION/$CHANNEL.repo" "Unable to fetch the repo ($?)" $ERR_FAILED_REPO_SETUP
        fi

        ### Fetch the gpg key ###
        run_quietly "curl https://packages.microsoft.com/keys/microsoft.asc > microsoft.asc" "unable to fetch gpg key $?" $ERR_FAILED_REPO_SETUP
        run_quietly "rpm $(get_rpm_proxy_params) --import microsoft.asc" "unable to import gpg key" $ERR_FAILED_REPO_SETUP
    fi

    local version=""
    if [ ! -z "$MDE_VERSION" ]; then
        version=$(validate_mde_version)
        if [ -z "$version" ]; then
            script_exit "Couldn't find the version $MDE_VERSION for channel $CHANNEL. Aborting installion" $ERR_INSTALLATION_FAILED
        fi
    fi

    ### Install MDE ###
    log_info "[>] installing MDE"

    if [ "$ARCHITECTURE" == "aarch64" ]; then
        run_quietly "$PKG_MGR_INVOKER install mdatp$version" "unable to install MDE ($?)" $ERR_INSTALLATION_FAILED
    else
        run_quietly "$PKG_MGR_INVOKER --enablerepo=$repo_name install mdatp$version" "unable to install MDE ($?)" $ERR_INSTALLATION_FAILED
    fi

    sleep 5
    log_info "[v] installed"
}

install_on_sles()
{
    local packages=
    local pkg_version=
    local repo=packages-microsoft-com

    if check_if_pkg_is_installed mdatp; then
        pkg_version=$($MDE_VERSION_CMD) || script_exit "unable to fetch the app version. please upgrade to latest version $?" $ERR_INTERNAL
        log_info "[i] MDE already installed ($pkg_version)"
        return
    fi

    packages=(curl)

    install_required_pkgs ${packages[@]}

    wait_for_package_manager_to_complete

    ### Configure the repository ###
    local repo_name=${repo}-${CHANNEL}
    if [ "$CHANNEL" == "insiders-slow" ]; then  # in case of insiders slow repo, the repo name is packages-microsoft-com-slow-prod
        repo_name=${repo}-slow-prod
    fi
    
    # add repository if it does not exist
    lines=$($PKG_MGR_INVOKER lr | grep "$repo_name" | wc -l)

    if [ $lines -eq 0 ]; then
        log_info "[i] configuring the repository"
        run_quietly "$PKG_MGR_INVOKER addrepo -c -f -n microsoft-$CHANNEL https://packages.microsoft.com/config/$DISTRO/$SCALED_VERSION/$CHANNEL.repo" "unable to load repo" $ERR_FAILED_REPO_SETUP
    else
        log_info "[i] repository already configured"
    fi

    ### Fetch the gpg key ###
    run_quietly "rpm $(get_rpm_proxy_params) --import https://packages.microsoft.com/keys/microsoft.asc > microsoft.asc" "unable to fetch gpg key $?" $ERR_FAILED_REPO_SETUP
    
    wait_for_package_manager_to_complete

    ### Install MDE ###
    log_info "[>] installing MDE"

    local version=""
    if [ ! -z "$MDE_VERSION" ]; then
        version=$(validate_mde_version)
        if [ -z "$version" ]; then
            script_exit "Couldn't find the version $MDE_VERSION for channel $CHANNEL. Aborting installion" $ERR_INSTALLATION_FAILED
        fi
    fi

    run_quietly "$PKG_MGR_INVOKER install $ASSUMEYES ${repo_name}:mdatp$version" "[!] failed to install MDE (1/2)"
    
    if ! check_if_pkg_is_installed mdatp; then
        log_warning "[r] retrying"
        sleep 2
        run_quietly "$PKG_MGR_INVOKER install $ASSUMEYES mdatp" "unable to install MDE 2/2 ($?)" $ERR_INSTALLATION_FAILED
    fi

    sleep 5
    log_info "[v] installed."
}

remove_repo()
{
    # Remove mdatp if installed
    if check_if_pkg_is_installed mdatp; then
        remove_mdatp
    fi

    # Remove configured packages.microsoft.com repository
    if [ $DISTRO == 'sles' ] || [ "$DISTRO" = "sle-hpc" ]; then
        local repo=packages-microsoft-com
        local repo_name=${repo}-${CHANNEL}
        if [ "$CHANNEL" == "insiders-slow" ]; then  # in case of insiders slow repo, the repo name is packages-microsoft-com-slow-prod
            repo_name=${repo}-slow-prod
        fi
        run_quietly "$PKG_MGR_INVOKER removerepo $repo_name" "failed to remove repo"
    
    elif [ "$DISTRO_FAMILY" == "fedora" ]; then
        local repo=packages-microsoft-com
        local repo_name="$repo-$CHANNEL"

        if [ "$CHANNEL" == "insiders-slow" ]; then  # in case of insiders slow repo, the repo name is packages-microsoft-com-slow-prod
            repo_name=${repo}-slow-prod
        fi

        if [[ $SCALED_VERSION == 7* ]] && [[ "$CHANNEL" != "prod" ]]; then
            repo_name=${repo}-prod
        fi

        yum -q repolist $repo_name | grep "$repo_name" &> /dev/null
        if [ $? -eq 0 ]; then
            run_quietly "yum-config-manager --disable $repo_name" "Unable to disable the repo ($?)" $ERR_FAILED_REPO_CLEANUP
            run_quietly "find /etc/yum.repos.d -exec grep -lqR \"\[$repo_name\]\" '{}' \; -delete" "Unable to remove repo ($?)" $ERR_FAILED_REPO_CLEANUP
        else
            log_info "[i] nothing to clean up"
        fi
    
    elif [ "$DISTRO_FAMILY" == "debian" ]; then
        if [ -f "/etc/apt/sources.list.d/microsoft-$CHANNEL.list" ]; then
            run_quietly "rm -f '/etc/apt/sources.list.d/microsoft-$CHANNEL.list'" "unable to remove repo list ($?)" $ERR_FAILED_REPO_CLEANUP
        fi
    else
        script_exit "unsupported distro for remove repo $DISTRO" $ERR_UNSUPPORTED_DISTRO
    fi

    log_info "[v] clean-up done."
}

upgrade_mdatp()
{
    if [ -z "$1" ]; then
        script_exit "INTERNAL ERROR. upgrade_mdatp requires an argument (the upgrade command)" $ERR_INTERNAL
    fi

    if ! check_if_pkg_is_installed mdatp; then
        script_exit "MDE package is not installed. Please install it first" $ERR_MDE_NOT_INSTALLED
    fi

    local VERSION_BEFORE_UPDATE=$(get_mdatp_version)
    log_info "[>] Current $VERSION_BEFORE_UPDATE"

    local version=""
    if [ ! -z "$MDE_VERSION" ]; then
        version=$(validate_mde_version)
        if [ -z "$version" ]; then
            script_exit "Couldn't find the version $MDE_VERSION for channel $CHANNEL. Aborting upgrade" $ERR_INSTALLATION_FAILED
        fi
    fi

    local current_version=$(echo "$VERSION_BEFORE_UPDATE" | sed 's/^[ \t\n]*//;s/[ \t\n]*$//' | awk '{print $NF}' | awk -F. '{ printf("%d%05d%05d\n", $1,$2,$3); }')
    local requested_version=$(echo "$MDE_VERSION" | awk -F. '{ printf("%d%05d%05d\n", $1,$2,$3); }')

    if [[ "$INSTALL_MODE" == "d" && "$current_version" -lt "$requested_version" ]]; then
        script_exit "For downgrade the requested version[$MDE_VERSION] should be older than current version[$VERSION_BEFORE_UPDATE]"
    elif [[ "$INSTALL_MODE" == "u" && ! -z "$MDE_VERSION" && "$current_version" -gt "$requested_version" ]]; then
        script_exit "For upgrade the requested version[$MDE_VERSION] should be newer than current version[$VERSION_BEFORE_UPDATE]. If you want to move to an older version instead, retry with --downgrade flag"
    fi

    run_quietly "$PKG_MGR_INVOKER $1 mdatp$version" "Unable to upgrade MDE $?" $ERR_INSTALLATION_FAILED

    local VERSION_AFTER_UPDATE=$(get_mdatp_version)
    if [ "$VERSION_BEFORE_UPDATE" == "$VERSION_AFTER_UPDATE" ]; then
        log_info "[>] MDE is already up to date."
    else
        log_info "[v] upgraded"
    fi
}

remove_mdatp()
{
    if ! check_if_pkg_is_installed mdatp; then
        script_exit "MDE package is not installed. Please install it first" $ERR_MDE_NOT_INSTALLED
    fi

    run_quietly "$PKG_MGR_INVOKER remove mdatp" "unable to remove MDE $?" $ERR_UNINSTALLATION_FAILED
}

rhel6_supported_version()
{
    local SUPPORTED_RHEL6_VERSIONS=("6.7" "6.8" "6.9" "6.10")
    for version in ${SUPPORTED_RHEL6_VERSIONS[@]}; do
        if [[ "$1" == "$version" ]]; then 
            return 0
        fi
    done
    return 1    
}

scale_version_id()
{
    ### We dont have pmc repos for rhel versions > 7.4. Generalizing all the 7* repos to 7 and 8* repos to 8
    if [ "$DISTRO_FAMILY" == "fedora" ]; then
        if [[ $VERSION == 6* ]]; then
            if rhel6_supported_version $VERSION; then # support versions 6.7+
                if [ "$DISTRO" == "centos" ] || [ "$DISTRO" == "rhel" ]; then
                    SCALED_VERSION=6
                else
                    script_exit "unsupported version: $DISTRO $VERSION" $ERR_UNSUPPORTED_VERSION
                fi
            else
               script_exit "unsupported version: $DISTRO $VERSION" $ERR_UNSUPPORTED_VERSION
            fi

        elif [[ $VERSION == 7* ]] || [ "$DISTRO" == "amzn" ]; then
            SCALED_VERSION=7
        elif [[ $VERSION == 8* ]] || [ "$DISTRO" == "fedora" ]; then
            SCALED_VERSION=8
        elif [[ $VERSION == 9* ]]; then
            if [[ $DISTRO == "almalinux" || $DISTRO == "rocky" ]]; then
                SCALED_VERSION=9
            else
                SCALED_VERSION=9.0
            fi
        else
            script_exit "unsupported version: $DISTRO $VERSION" $ERR_UNSUPPORTED_VERSION
        fi
    elif [ "$DISTRO_FAMILY" == "mariner" ]; then
        if [[ $VERSION == 2* ]]; then
            SCALED_VERSION=2
        else
            script_exit "unsupported version: $DISTRO $VERSION" $ERR_UNSUPPORTED_VERSION
        fi
    elif [ "$DISTRO_FAMILY" == "sles" ]; then
        if [[ $VERSION == 12* ]]; then
            SCALED_VERSION=12
        elif [[ $VERSION == 15* ]]; then
            SCALED_VERSION=15
        else
            script_exit "unsupported version: $DISTRO $VERSION" $ERR_UNSUPPORTED_VERSION
        fi
    elif [ $DISTRO == "ubuntu" ] && [[ $VERSION != "16.04" ]] && [[ $VERSION != "18.04" ]] && [[ $VERSION != "20.04" ]] && [[ $VERSION != "22.04" ]]; then
        SCALED_VERSION=18.04
    else
        # no problems with 
        SCALED_VERSION=$VERSION
    fi
    log_info "[>] scaled: $SCALED_VERSION"
}

onboard_device()
{
    log_info "[>] onboarding script: $ONBOARDING_SCRIPT"

    if ! check_if_pkg_is_installed mdatp; then
        script_exit "MDE package is not installed. Please install it first" $ERR_MDE_NOT_INSTALLED
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
        # echo "[>] running onboarding script..."
        sleep 1
        run_quietly "$PYTHON $ONBOARDING_SCRIPT" "error: python onboarding failed" $ERR_ONBOARDING_FAILED

    elif [[ $ONBOARDING_SCRIPT == *.sh ]]; then        
        run_quietly "sh $ONBOARDING_SCRIPT" "error: bash onboarding failed" $ERR_ONBOARDING_FAILED

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
    license_found=false

    for ((i = 1; i <= 10; i++)); do
        sleep 15 # Delay for 15 seconds before checking the license status

        # Check if "No license found" is present in the output of the mdatp health command
        if [[ $(mdatp health --field org_id | grep "No license found" -c) -gt 0 ]]; then
        # If "No license found" is present, set the license_found variable to false
            license_found=false
        else
        # If "No license found" is not present, exit the loop
            license_found=true
            break
        fi
    done

    if [[ $license_found == false ]]; then
        script_exit "onboarding failed" $ERR_ONBOARDING_FAILED
    fi

    log_info "[v] onboarded"
}

offboard_device()
{
    log_info "[>] offboarding script: $OFFBOARDING_SCRIPT"

    if ! check_if_pkg_is_installed mdatp; then
        script_exit "MDE package is not installed. Please install it first" $ERR_MDE_NOT_INSTALLED
    fi

    if [ ! -f $OFFBOARDING_SCRIPT ]; then
        script_exit "error: offboarding script not found." $ERR_OFFBOARDING_NOT_FOUND
    fi

    if [[ $OFFBOARDING_SCRIPT == *.py ]]; then
        # Make sure python is installed
        PYTHON=$(which python || which python3)

        if [ $? -ne 0 ]; then
            script_exit "error: cound not locate python." $ERR_FAILED_DEPENDENCY
        fi

        # Run offboarding script
        # echo "[>] running offboarding script..."
        sleep 1
        run_quietly "$PYTHON $OFFBOARDING_SCRIPT" "error: python offboarding failed" $ERR_OFFBOARDING_FAILED

    elif [[ $OFFBOARDING_SCRIPT == *.sh ]]; then        
        run_quietly "sh $OFFBOARDING_SCRIPT" "error: bash offboarding failed" $ERR_OFFBOARDING_FAILED

    else
        script_exit "error: unknown offboarding script type." $ERR_OFFBOARDING_FAILED
    fi

    # validate offboarding
    sleep 3
    if [[ $(mdatp health --field org_id | grep "No license found" -c) -eq 0 ]]; then
        script_exit "offboarding failed" $ERR_OFFBOARDING_FAILED
    fi
    log_info "[v] offboarded"
}

set_epp_to_passive_mode()
{
    if ! check_if_pkg_is_installed mdatp; then
        script_exit "MDE package is not installed. Please install it first" $ERR_MDE_NOT_INSTALLED
    fi

    if [[ $(mdatp health --field passive_mode_enabled | tail -1) == "false" ]]; then
        log_info "[>] setting MDE/EPP to passive mode"
        retry_quietly 3 "mdatp config passive-mode --value enabled" "failed to set MDE to passive-mode" $ERR_PARAMETER_SET_FAILED
    else
        log_info "[>] MDE/EPP already in passive mode"
    fi
    
    log_info "[v] passive mode set"
}

set_epp_to_rtp_mode()
{
    if ! check_if_pkg_is_installed mdatp; then
        script_exit "MDE package is not installed. Please install it first" $ERR_MDE_NOT_INSTALLED
    fi

    if [[ $(mdatp health --field real_time_protection_enabled | tail -1) == "false" ]]; then
        log_info "[>] setting MDE/EPP to real time protection mode"
        retry_quietly 3 "mdatp config real-time-protection --value enabled" "failed to set MDE to rtp-mode" $ERR_PARAMETER_SET_FAILED
    else
        log_info "[>] MDE/EPP already in real time protection mode"
    fi

    log_info "[v] real time protection mode set"
}

set_device_tags()
{
    for t in "${tags[@]}"
    do
        set -- $t
        if [ "$1" == "GROUP" ] || [ "$1" == "SecurityWorkspaceId" ] || [ "$1" == "AzureResourceId" ] || [ "$1" == "SecurityAgentId" ]; then
            local set_tags=$(mdatp health --field edr_device_tags)
            local tag_exists=0

            local result=$(echo "$set_tags" | grep -q "\"key\":\"$1\""; echo "$?")
            if [ $result -eq 0 ]; then
                local value=$(echo "$set_tags" | grep -o "\"key\":\"$1\".*\"" | cut -d '"' -f 8)
                if [ "$value" == "$2" ]; then
                    log_warning "[>] tag $1 already set to value $2."
                    tag_exists=1
                fi
            fi

            if [ $tag_exists -eq 0 ]; then
                # echo "[>] setting tag: ($1, $2)"
                retry_quietly 2 "mdatp edr tag set --name $1 --value $2" "failed to set tag" $ERR_PARAMETER_SET_FAILED
            fi
        else
            script_exit "invalid tag name: $1. supported tags: GROUP, SecurityWorkspaceId, AzureResourceId and SecurityAgentId" $ERR_TAG_NOT_SUPPORTED
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
    echo " -h|--help            display help"
}

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
        --rtp-mode)
            verify_privileges "rtp-mode"
            RTP_MODE=1
            shift 1
            ;;
        -t|--tag)
            if [[ -z "$2" || -z "$3" ]]; then
                script_exit "$1 option requires two arguments" $ERR_INVALID_ARGUMENTS
            fi
            verify_privileges "set-tag"
            tags+=("$2 $3")
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
        *)
            echo "use -h or --help for details"
            script_exit "unknown argument" $ERR_INVALID_ARGUMENTS
            ;;
    esac
done

if [[ -z "${INSTALL_MODE}" && -z "${ONBOARDING_SCRIPT}" && -z "${OFFBOARDING_SCRIPT}" && -z "${PASSIVE_MODE}" && -z "${RTP_MODE}" && ${#tags[@]} -eq 0 ]]; then
    script_exit "no installation mode specified. Specify --help for help" $ERR_INVALID_ARGUMENTS
fi

# Check for mutually exclusive options
if [ ! -z "$PASSIVE_MODE" ] && [ ! -z "$RTP_MODE" ]; then
    echo "Options -p and --rtp-mode are mutually exclusive."
    usage
    exit 1
fi

if [[ "$INSTALL_MODE" == 'i' && -z "$CHANNEL" ]]; then
    log_info "[i] Specify the install channel using "--channel" argument. If not provided, mde will be installed for prod by default. Expected channel values: prod, insiders-slow, insiders-fast."
    CHANNEL=prod
fi

if [[ "$INSTALL_MODE" == 'c' && -z "$CHANNEL" ]]; then
    log_info "[i] Specify the cleanup channel using "--channel" argument. If not provided, prod repo will be cleaned up by default. Expected channel values: prod, insiders-slow, insiders-fast."
    CHANNEL=prod
fi

if [[ "$INSTALL_MODE" == 'd' && -z "$MDE_VERSION" ]]; then
    script_exit "Specify the mdatp version using --mdatp argument when using --downgrade option" $ERR_INVALID_ARGUMENTS
fi

if [[ -z "$MDE_VERSION" && ( "$INSTALL_MODE" == 'i' || "$INSTALL_MODE" == 'u' ) ]]; then
    log_info "[i] Specify the version to be installed using "--mdatp" argument. If not provided, latest mde will be installed by default."
fi


# echo "--- mde_installer.sh v$SCRIPT_VERSION ---"
log_info "--- mde_installer.sh v$SCRIPT_VERSION ---"

### Validate mininum requirements ###
if [ $MIN_REQUIREMENTS ]; then
    verify_min_requirements
fi

## Detect the architecture type
detect_arch

### Detect the distro and version number ###
detect_distro

### Check for ARM preview
if [ "$ARCHITECTURE" == "aarch64" ]; then
    check_arm_distro_support
fi

### Scale the version number according to repos avaiable on pmc ###
scale_version_id

### Set package manager ###
set_package_manager

### Act according to arguments ###
if [ "$INSTALL_MODE" == "i" ]; then

    if [ -z $SKIP_CONFLICTING_APPS ]; then
        verify_conflicting_applications
    fi
    
    if [ "$DISTRO_FAMILY" == "debian" ]; then
        install_on_debian
    elif [ "$DISTRO_FAMILY" == "fedora" ]; then
        install_on_fedora
    elif [ "$DISTRO_FAMILY" == "mariner" ]; then
        install_on_mariner
    elif [ "$DISTRO_FAMILY" = "sles" ]; then
        install_on_sles
    else
        script_exit "unsupported distro $DISTRO $VERSION" $ERR_UNSUPPORTED_DISTRO
    fi

elif [ "$INSTALL_MODE" == "u" ]; then

    if [ "$DISTRO_FAMILY" == "debian" ]; then
        upgrade_mdatp "$ASSUMEYES install --only-upgrade"
    elif [ "$DISTRO_FAMILY" == "fedora" ]; then
        upgrade_mdatp "$ASSUMEYES update"
    elif [ "$DISTRO_FAMILY" == "mariner" ]; then
        upgrade_mdatp "$ASSUMEYES update"
    elif [ "$DISTRO_FAMILY" == "sles" ]; then
        upgrade_mdatp "up $ASSUMEYES"
    else    
        script_exit "unsupported distro $DISTRO $VERSION" $ERR_UNSUPPORTED_DISTRO
    fi

elif [ "$INSTALL_MODE" == "d" ]; then

    if [ "$DISTRO_FAMILY" == "debian" ]; then
        upgrade_mdatp "$ASSUMEYES install --allow-downgrades"
    elif [ "$DISTRO_FAMILY" == "fedora" ]; then
        upgrade_mdatp "$ASSUMEYES downgrade"
    elif [ "$DISTRO_FAMILY" == "mariner" ]; then
        upgrade_mdatp "$ASSUMEYES downgrade"
    elif [ "$DISTRO_FAMILY" == "sles" ]; then
        upgrade_mdatp "install --oldpackage $ASSUMEYES"
    else
        script_exit "unsupported distro $DISTRO $VERSION" $ERR_UNSUPPORTED_DISTRO
    fi

elif [ "$INSTALL_MODE" = "r" ]; then
    if remove_mdatp; then
        script_exit "[v] removed MDE" $SUCCESS
    fi

elif [ "$INSTALL_MODE" == "c" ]; then
    if remove_repo; then
        script_exit "[v] removed repo" $SUCCESS
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
