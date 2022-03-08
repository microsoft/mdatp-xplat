#!/bin/bash

#============================================================================
#
#  Copyright (c) 2021 Microsoft Corporation.  All rights reserved.
#
#  Abstract:
#    MDE installation script 
#    - Fingerprinting OS and manually installs MDE as described in the online documentation
#      https://docs.microsoft.com/en-us/microsoft-365/security/defender-endpoint/linux-install-manually?view=o365-worldwide
#    - Runs additional optional checks: minimal requirements, fanotify subscribers, etc.
#
#============================================================================

SCRIPT_VERSION="0.5.3"
ASSUMEYES=
CHANNEL=insiders-fast
DISTRO=
DISTRO_FAMILY=
PKG_MGR=
INSTALL_MODE=
DEBUG=
VERBOSE=
MDE_VERSION_CMD="mdatp health --field app_version"
PMC_URL=https://packages.microsoft.com/config
SCALED_VERSION=
VERSION=
ONBOARDING_SCRIPT=
MIN_REQUIREMENTS=
SKIP_CONFLICTING_APPS=
PASSIVE_MODE=
MIN_CORES=2
MIN_MEM_MB=2048
MIN_DISK_SPACE_MB=1280
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
ERR_MDE_NOT_INSTALLED=20
ERR_INSTALLATION_FAILED=21
ERR_UNINSTALLATION_FAILED=22
ERR_FAILED_DEPENDENCY=23
ERR_FAILED_REPO_SETUP=24
ERR_INVALID_CHANNEL=25
ERR_ONBOARDING_NOT_FOUND=30
ERR_ONBOARDING_FAILED=31
ERR_TAG_NOT_SUPPORTED=40
ERR_PARAMETER_SET_FAILED=41

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

print_state()
{
    if [ -z $(which mdatp) ]; then
        log_warning "[S] MDE not installed."
    else
        log_info "[S] MDE installed."
        log_info "[S] Version: $($MDE_VERSION_CMD)"
        log_info "[S] Onboarded: $(mdatp health --field licensed)"
        log_info "[S] Passive mode: $(mdatp health --field passive_mode_enabled)"
        log_info "[S] Device tags: $(mdatp health --field edr_device_tags)"
        log_info "[S] Subsystem: $(mdatp health --field real_time_protection_subsystem)"
        log_info "[S] Conflicting applications: $(mdatp health --field conflicting_applications)"
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


detect_distro()
{
    if [ -f /etc/os-release ]; then
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

    if [ "$DISTRO" == "debian" ] || [ "$DISTRO" == "ubuntu" ]; then
        DISTRO_FAMILY="debian"
    elif [ "$DISTRO" == "rhel" ] || [ "$DISTRO" == "centos" ] || [ "$DISTRO" == "ol" ] || [ "$DISTRO" == "fedora" ] || [ "$DISTRO" == "amzn" ]; then
        DISTRO_FAMILY="fedora"
    elif [ "$DISTRO" == "sles" ] || [ "$DISTRO" == "sle-hpc" ] || [ "$DISTRO" == "sles_sap" ]; then
        DISTRO_FAMILY="sles"
    else
        script_exit "unsupported distro $DISTRO $VERSION" $ERR_UNSUPPORTED_DISTRO
    fi

    log_info "[>] detected: $DISTRO $VERSION $VERSION_NAME ($DISTRO_FAMILY)"
}

verify_connectivity()
{
    if [ -z "$1" ]; then
        script_exit "Internal error. verify_connectivity require a parameter" $ERR_INTERNAL
    fi

    if which wget; then
        connect_command="wget -O - --quiet --no-verbose --timeout 2 https://cdn.x.cp.wd.microsoft.com/ping --no-check-certificate"
    elif which curl; then
        connect_command="curl --silent --connect-timeout 2 --insecure https://cdn.x.cp.wd.microsoft.com/ping"
    else
        script_exit "Unable to find wget/curl commands" $ERR_INTERNAL
    fi

    local connected=
    local counter=3

    while [ $counter -gt 0 ]
    do
        connected=$($connect_command)

        if [[ "$connected" != "OK" ]]; then
            sleep 1
            ((counter--))
        else
            counter=0
        fi
    done

    log_info "[final] connected=$connected"
    
    if [[ "$connected" != "OK" ]]; then
        script_exit "internet connectivity needed for $1" $ERR_NO_INTERNET_CONNECTIVITY
    fi
    log_info "[v] connected"
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

verify_conflicting_applications()
{
    # echo "[>] identifying conflicting applications (fanotify mounts)"

    # find applications that are using fanotify
    local conflicting_apps=$(timeout 5m find /proc/*/fdinfo/ -type f -exec sh -c 'lines=$(cat {} | grep "fanotify mnt_id" | wc -l); if [ $lines -gt 0 ]; then cat $(dirname {})/../cmdline; fi;' \; 2>/dev/null)
    
    if [ ! -z $conflicting_apps ]; then
        script_exit "found conflicting applications: [$conflicting_apps], aborting" $ERR_CONFLICTING_APPS
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

install_on_debian()
{
    local packages=
    local pkg_version=
    local success=

    if check_if_pkg_is_installed mdatp; then
        pkg_version=$($MDE_VERSION_CMD) || script_exit "unable to fetch the app version. please upgrade to latest version $?" $ERR_INTERNAL
        log_info "[i] MDE already installed ($pkg_version)"
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

    ### Install MDE ###
    log_info "[>] installing MDE"
    if [ "$CHANNEL" = "prod" ]; then
        if [[ -z "$VERSION_NAME" ]]; then
            run_quietly "$PKG_MGR_INVOKER install mdatp" "unable to install MDE ($?)" $ERR_INSTALLATION_FAILED
        else
            run_quietly "$PKG_MGR_INVOKER -t $VERSION_NAME install mdatp" "unable to install MDE ($?)" $ERR_INSTALLATION_FAILED
        fi
    else
        run_quietly "$PKG_MGR_INVOKER -t $CHANNEL install mdatp" "unable to install MDE ($?)" $ERR_INSTALLATION_FAILED
    fi

    sleep 5
    log_info "[v] installed"
}

install_on_fedora()
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

    repo=packages-microsoft-com
    packages=(curl yum-utils)

    if [[ $SCALED_VERSION == 7* ]] && [ "$DISTRO" == "rhel" ]; then
        packages=($packages deltarpm)
    fi

    install_required_pkgs ${packages[@]}

    ### Configure the repo name from which package should be installed
    if [[ $SCALED_VERSION == 7* ]] && [[ "$CHANNEL" != "prod" ]]; then
        repo=packages-microsoft-com-prod
    fi

    if [ "$DISTRO" == "ol" ] || [ "$DISTRO" == "fedora" ] || [ "$DISTRO" == "amzn" ]; then
        effective_distro="rhel"
    else
        effective_distro="$DISTRO"
    fi

    ### Configure the repository ###
    run_quietly "yum-config-manager --add-repo=$PMC_URL/$effective_distro/$SCALED_VERSION/$CHANNEL.repo" "Unable to fetch the repo ($?)" $ERR_FAILED_REPO_SETUP

    ### Fetch the gpg key ###
    run_quietly "curl https://packages.microsoft.com/keys/microsoft.asc > microsoft.asc" "unable to fetch gpg key $?" $ERR_FAILED_REPO_SETUP
    run_quietly "rpm $(get_rpm_proxy_params) --import microsoft.asc" "unable to import gpg key" $ERR_FAILED_REPO_SETUP

    ### Install MDE ###
    log_info "[>] installing MDE"
    run_quietly "$PKG_MGR_INVOKER --enablerepo=$repo-$CHANNEL install mdatp" "unable to install MDE ($?)" $ERR_INSTALLATION_FAILED
    
    sleep 5
    log_info "[v] installed"
}

install_on_sles()
{
    local packages=
    local pkg_version=
    local repo=

    if check_if_pkg_is_installed mdatp; then
        pkg_version=$($MDE_VERSION_CMD) || script_exit "unable to fetch the app version. please upgrade to latest version $?" $ERR_INTERNAL
        log_info "[i] MDE already installed ($pkg_version)"
        return
    fi

    repo=packages-microsoft-com
    packages=(curl)

    install_required_pkgs ${packages[@]}

    wait_for_package_manager_to_complete

    ### Configure the repository ###
    # add repository if it does not exist
    lines=$($PKG_MGR_INVOKER lr | grep "packages-microsoft-com-$CHANNEL" | wc -l)

    if [ $lines -eq 0 ]; then
        run_quietly "$PKG_MGR_INVOKER addrepo -c -f -n microsoft-$CHANNEL https://packages.microsoft.com/config/$DISTRO/$SCALED_VERSION/$CHANNEL.repo" "unable to load repo" $ERR_FAILED_REPO_SETUP
    fi

    ### Fetch the gpg key ###
    run_quietly "rpm $(get_rpm_proxy_params) --import https://packages.microsoft.com/keys/microsoft.asc > microsoft.asc" "unable to fetch gpg key $?" $ERR_FAILED_REPO_SETUP
    
    wait_for_package_manager_to_complete

    ### Install MDE ###
    log_info "[>] installing MDE"

    run_quietly "$PKG_MGR_INVOKER install $ASSUMEYES $repo-$CHANNEL:mdatp" "[!] failed to install MDE (1/2)"
    
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
    # TODO: add support for debian and fedora
    if [ $DISTRO == 'sles' ] || [ "$DISTRO" = "sle-hpc" ]; then
        run_quietly "$PKG_MGR_INVOKER removerepo packages-microsoft-com-$CHANNEL" "failed to remove repo"
    else
        script_exit "unsupported distro for remove repo $DISTRO" $ERR_UNSUPPORTED_DISTRO
    fi
}

upgrade_mdatp()
{
    if [ -z "$1" ]; then
        script_exit "INTERNAL ERROR. upgrade_mdatp requires an argument (the upgrade command)" $ERR_INTERNAL
    fi

    if ! check_if_pkg_is_installed mdatp; then
        script_exit "MDE package is not installed. Please install it first" $ERR_MDE_NOT_INSTALLED
    fi

    log_info "[>] Current MDE package installed: $($MDE_VERSION_CMD)"

    run_quietly "$PKG_MGR_INVOKER $1 mdatp" "Unable to upgrade MDE $?" $ERR_INSTALLATION_FAILED
    log_info "[v] upgraded"
}

remove_mdatp()
{
    if ! check_if_pkg_is_installed mdatp; then
        script_exit "MDE package is not installed. Please install it first" $ERR_MDE_NOT_INSTALLED
    fi

    run_quietly "$PKG_MGR_INVOKER remove mdatp" "unable to remove MDE $?" $ERR_UNINSTALLATION_FAILED
    script_exit "[v] removed" $SUCCESS
}

scale_version_id()
{
    ### We dont have pmc repos for rhel versions > 7.4. Generalizing all the 7* repos to 7 and 8* repos to 8
    if [ "$DISTRO_FAMILY" == "fedora" ]; then
        if [[ $VERSION == 7* ]] || [ "$DISTRO" == "amzn" ]; then
            SCALED_VERSION=7
        elif [[ $VERSION == 8* ]] || [ "$DISTRO" == "fedora" ]; then
            SCALED_VERSION=8
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
    elif [ $DISTRO == "ubuntu" ] && [[ $VERSION != "16.04" ]] && [[ $VERSION != "18.04" ]] && [[ $VERSION != "20.04" ]]; then
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

    # Make sure python is installed
    PYTHON=$(which python || which python3)

    if [ -z $PYTHON ]; then
        script_exit "error: cound not locate python." $ERR_FAILED_DEPENDENCY
    fi

    # Run onboarding script
    # echo "[>] running onboarding script..."
    sleep 1
    run_quietly "$PYTHON $ONBOARDING_SCRIPT" "error: onboarding failed" $ERR_ONBOARDING_FAILED

    # validate onboarding
    sleep 3
    if [[ $(mdatp health --field org_id | grep "No license found" -c) -gt 0 ]]; then
        script_exit "onboarding failed" $ERR_ONBOARDING_FAILED
    fi
    log_info "[v] onboarded"
}

set_epp_to_passive_mode()
{
    # echo "[>] setting MDE/EPP to passive mode"

    if ! check_if_pkg_is_installed mdatp; then
        script_exit "MDE package is not installed. Please install it first" $ERR_MDE_NOT_INSTALLED
    fi

    retry_quietly 3 "mdatp config passive-mode --value enabled" "failed to set MDE to passive-mode" $ERR_PARAMETER_SET_FAILED
    log_info "[v] passive mode set"
}

set_device_tags()
{
    for t in "${tags[@]}"
    do
        set -- $t
        if [ "$1" == "GROUP" ] || [ "$1" == "SecurityWorkspaceId" ] || [ "$1" == "AzureResourceId" ] || [ "$1" == "SecurityAgentId" ]; then
            # echo "[>] setting tag: ($1, $2)"
            retry_quietly 2 "mdatp edr tag set --name $1 --value $2" "failed to set tag" $ERR_PARAMETER_SET_FAILED
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
    echo " -c|--channel         specify the channel from which you want to install. Default: insiders-fast"
    echo " -i|--install         install the product"
    echo " -r|--remove          remove the product"
    echo " -u|--upgrade         upgrade the existing product to a newer version if available"
    echo " -o|--onboard         onboard/offboard the product with <onboarding_script>"
    echo " -p|--passive-mode    set EPP to passive mode"
    echo " -t|--tag             set a tag by declaring <name> and <value>. ex: -t GROUP Coders"
    echo " -m|--min_req         enforce minimum requirements"
    echo " -x|--skip_conflict   skip conflicting application verification"
    echo " -w|--clean           remove repo from package manager for a specific channel"
    echo " -y|--yes             assume yes for all mid-process prompts (highly reccomended)"
    echo " -s|--verbose         verbose output"
    echo " -v|--version         print out script version"
    echo " -d|--debug           set debug mode"
    echo " --log-path <PATH>    also log output to PATH"
    echo " --http-proxy <URL>   set http proxy"
    echo " --https-proxy <URL>  set https proxy"
    echo " --ftp-proxy <URL>    set ftp proxy"
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
        *)
            echo "use -h or --help for details"
            script_exit "unknown argument" $ERR_INVALID_ARGUMENTS
            ;;
    esac
done

if [[ -z "${INSTALL_MODE}" && -z "${ONBOARDING_SCRIPT}" && -z "${PASSIVE_MODE}" && ${#tags[@]} -eq 0 ]]; then
    script_exit "no installation mode specified. Specify --help for help" $ERR_INVALID_ARGUMENTS
fi

echo "--- mde_installer.sh v$SCRIPT_VERSION ---"
log_info "--- mde_installer.sh v$SCRIPT_VERSION ---"

### Validate mininum requirements ###
if [ $MIN_REQUIREMENTS ]; then
    verify_min_requirements
fi

### Detect the distro and version number ###
detect_distro

### Scale the version number according to repos avaiable on pmc ###
scale_version_id

### Set package manager ###
set_package_manager

### Act according to arguments ###
if [ "$INSTALL_MODE" == "i" ]; then
    verify_connectivity "package installation"

    if [ -z $SKIP_CONFLICTING_APPS ]; then
        verify_conflicting_applications
    fi
    
    if [ "$DISTRO_FAMILY" == "debian" ]; then
        install_on_debian
    elif [ "$DISTRO_FAMILY" == "fedora" ]; then
        install_on_fedora
    elif [ "$DISTRO_FAMILY" = "sles" ]; then
        install_on_sles
    else
        script_exit "unsupported distro $DISTRO $VERSION" $ERR_UNSUPPORTED_DISTRO
    fi

elif [ "$INSTALL_MODE" == "u" ]; then
    verify_connectivity "package update"

    if [ "$DISTRO_FAMILY" == "debian" ]; then
        upgrade_mdatp "$ASSUMEYES install --only-upgrade"
    elif [ "$DISTRO_FAMILY" == "fedora" ]; then
        upgrade_mdatp "$ASSUMEYES update"
    elif [ "$DISTRO_FAMILY" == "sles" ]; then
        upgrade_mdatp "up $ASSUMEYES"
    else    
        script_exit "unsupported distro $DISTRO $VERSION" $ERR_UNSUPPORTED_DISTRO
    fi

elif [ "$INSTALL_MODE" = "r" ]; then
    remove_mdatp

elif [ "$INSTALL_MODE" == "c" ]; then
    remove_repo
fi

if [ ! -z $PASSIVE_MODE ]; then
    set_epp_to_passive_mode
fi

if [ ! -z $ONBOARDING_SCRIPT ]; then
    onboard_device
fi

if [ ${#tags[@]} -gt 0 ]; then
    set_device_tags
fi

script_exit "--- mde_installer.sh ended. ---" $SUCCESS
