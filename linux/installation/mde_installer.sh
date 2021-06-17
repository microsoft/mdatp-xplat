#!/bin/bash

SCRIPT_VERSION=0.1
ASSUMEYES=
CHANNEL=insiders-fast
DISTRO=
PKG_MGR=
INSTALL_CMD=
INSTALL_MODE=
MDE_VERSION_CMD="mdatp health --field app_version"
PMC_URL=https://packages.microsoft.com/config
SCALED_VERSION=
VERSION=
ONBOARDING_SCRIPT=
MIN_REQUIREMENTS=
PASSIVE_MODE=
MIN_CORES=1
MIN_MEM_MB=1024
MIN_DISK_SPACE_MB=1024
declare -a tags
error_code=0

script_exit()
{
    if [ -z "$1" ]; then
        echo "INTERNAL ERROR. script_exit requires an argument" >&2
        exit 1
    fi

    if [ "$2" = "0" ]; then
        echo "$1"
    else
        echo "$1" >&2
    fi

    if [ -z "$2" ]; then
        exit 1
    else
        echo "Script exiting with status $2"
        exit $2
    fi
}

detect_distro()
{
    if [ -f /etc/os-release ]; then
        if [[ $(grep -o -i "amazon_linux:2" /etc/os-release) ]]; then
            DISTRO='rhel'
            VERSION=7
        else
            . /etc/os-release
            DISTRO=$ID
            VERSION=$VERSION_ID
            VERSION_NAME=$VERSION_CODENAME
        fi
        
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
        script_exit "Unable to detect distro"
    fi
    echo "Distro detected or similar to: $DISTRO"
}
verify_channel()
{
    if [ "$CHANNEL" != "prod" ] && [ "$CHANNEL" != "insiders-fast" ] && [ "$CHANNEL" != "insiders-slow" ]; then
        script_exit "Invalid channel: $CHANNEL. Please provide valid channel. Available channels are prod, insiders-fast, insiders-slow"
    fi
}

verify_privileges()
{
    if [ -z "$1" ]; then
        script_exit "Internal error. verify_privileges require a parameter"
    fi

    if [ $(id -u) -ne 0 ]; then
        script_exit "Need sudo privileges to perform $1 operation"
    fi
}

verify_min_requirements()
{
    echo "verifying minimal reuirements: $MIN_CORES cores, $MIN_MEM_MB MB RAM, $MIN_DISK_SPACE_MB MB disk space"

    local CORES=$(nproc --all)
    if [ $CORES -lt $MIN_CORES ]; then
        script_exit "MDE requires $MIN_CORES cores or more to run, found $CORES."
    fi

    local MEM_MB=$(free -m | grep Mem | awk '{print $2}')
    if [ $MEM_MB -lt $MIN_MEM_MB ]; then
        script_exit "MDE requires at least $MIN_MEM_MB MB of RAM to run. found $MEM_MB MB."
    fi

    local DISK_SPACE_MB=$(df -m . | tail -1 | awk '{print $4}')
    if [ $DISK_SPACE_MB -lt $MIN_DISK_SPACE_MB ]; then
        script_exit "MDE requires at least $MIN_DISK_SPACE_MB MB of free disk space for installation"
    fi

    echo "device qualifies"
}

set_package_manager()
{
    if [ "$DISTRO" = "debian" ] || [ "$DISTRO" = "ubuntu" ]; then
        PKG_MGR=apt
    elif [ "$DISTRO" = "rhel" ] || [ "$DISTRO" = "centos" ] || [ "$DISTRO" = "ol" ]; then
        PKG_MGR=yum
    elif [ "$DISTRO" = "sles" ] || [ "$DISTRO" = "sle-hpc" ] ; then
        DISTRO="sles"
        PKG_MGR=zypper
    else
        script_exit "Unsupported distro"
    fi
}

check_if_pkg_is_installed()
{
    if [ -z "$1" ]; then
        script_exit "INTERNAL ERROR. check_if_pkg_is_installed requires an argument"
    fi

    if [ "$PKG_MGR" = "apt" ]; then
        dpkg -s $1 2> /dev/null | grep Status | grep "install ok installed" 1> /dev/null
    else
        rpm --quiet --query $1
    fi

    return $?
}

install_required_pkgs()
{
    local PACKAGES=
    local PKGS_TO_BE_INSTALLED=

    if [ -z "$1" ]; then
        script_exit "INTERNAL ERROR. install_required_pkgs requires an argument"
    fi

    PACKAGES=("$@")
    for pkg in "${PACKAGES[@]}"
    do
        if  ! check_if_pkg_is_installed $pkg; then
            PKGS_TO_BE_INSTALLED="$PKGS_TO_BE_INSTALLED $pkg"
        fi
    done

    if [ ! -z "$PKGS_TO_BE_INSTALLED" ]; then
        echo "Installing required packages $PKGS_TO_BE_INSTALLED"
        eval "$INSTALL_CMD $PKGS_TO_BE_INSTALLED" || script_exit "Unable to install the required packages" $?
    else
        echo "All the required packages are installed"
    fi
}

wait_for_package_manager_to_complete()
{
    local LINES=
    local COUNTER=10

    while [ $COUNTER -gt 0 ]
    do
        LINES=$(ps axo pid,comm | grep "$PKG_MGR" | grep -v grep -c)
        if [ "$LINES" -eq 0 ]; then
            echo "package manager is free"
            return
        fi
        sleep 1
        ((COUNTER--))
    done

    echo "package manager still online..."
}

install_on_debian()
{
    INSTALL_CMD="sudo apt install $ASSUMEYES"
    local PACKAGES=
    local PKG_VERSION=

    if check_if_pkg_is_installed mdatp; then
        PKG_VERSION=$($MDE_VERSION_CMD) || script_exit "Unable to fetch the app version. Please upgrade to latest version" $?
        script_exit "MDE package is already installed with version $PKG_VERSION" 0
    fi

    PACKAGES=(curl libplist-utils apt-transport-https gnupg)

    install_required_pkgs ${PACKAGES[@]}

    ### Configure the repository ###
    curl -sSL $PMC_URL/$DISTRO/$SCALED_VERSION/$CHANNEL.list | sudo tee /etc/apt/sources.list.d/microsoft-$CHANNEL.list || script_exit "Unable to fetch the repo" $?

    ### Fetch the gpg key ###
    curl -sSL https://packages.microsoft.com/keys/microsoft.asc | sudo tee /etc/apt/trusted.gpg.d/microsoft.asc || script_exit "Unable to fetch the gpg key" $?

    sudo apt-get update || echo "Unable to refresh the repos properly. command exited with status $?" >&2

    ### Install MDE ###
    echo "Installing MDE on distro: $DISTRO version: $VERSION"
    if [ "$CHANNEL" = "prod" ]; then
        sudo apt -t $VERSION_NAME install $ASSUMEYES mdatp || script_exit "Unable to install MDE" $?
    else
        sudo apt -t $CHANNEL install $ASSUMEYES mdatp || script_exit "Unable to install MDE" $?
    fi

    echo "Package successfully installed"
}

install_on_redhat()
{
    INSTALL_CMD="sudo yum install $ASSUMEYES"
    local PACKAGES=
    local PKG_VERSION=
    local REPO=

    if check_if_pkg_is_installed mdatp; then
        PKG_VERSION=$($MDE_VERSION_CMD) || script_exit "Unable to fetch the app version. Please upgrade to latest version" $?
        script_exit "MDE package is already installed with version $PKG_VERSION" 0
    fi

    REPO=packages-microsoft-com
    PACKAGES=(curl yum-utils)

    install_required_pkgs ${PACKAGES[@]}

    ### Configure the repo name from which package should be installed
    if [[ $SCALED_VERSION == 7* ]] && [[ "$CHANNEL" != "prod" ]]; then
        REPO=packages-microsoft-com-prod
    fi

    if [ "$DISTRO" == "ol" ]; then
        DISTRO="rhel"
    fi

    ### Configure the repository ###
    sudo yum-config-manager --add-repo=$PMC_URL/$DISTRO/$SCALED_VERSION/$CHANNEL.repo || script_exit "Unable to fetch the repo" $?

    ### Fetch the gpg key ###
    curl -sSL https://packages.microsoft.com/keys/microsoft.asc > ./microsoft.asc || script_exit "Unable to fetch gpg key" $?
    sudo rpm --import ./microsoft.asc
    sudo yum makecache || echo " Unable to refresh the repos properly. Command exited with status $?">&2

    ### Install MDE ###
    echo "Installing MDE on distro: $DISTRO version: $VERSION"
    sudo yum --enablerepo=$REPO-$CHANNEL install $ASSUMEYES mdatp || script_exit "Unable to install MDE" $?
    echo "Package successfully installed"
}

install_on_sles()
{
    INSTALL_CMD="sudo zypper install $ASSUMEYES"
    local PACKAGES=
    local PKG_VERSION=
    local REPO=

    if check_if_pkg_is_installed mdatp; then
        PKG_VERSION=$($MDE_VERSION_CMD) || script_exit "Unable to fetch the app version. Please upgrade to latest version" $?
        script_exit "MDE package is already installed with version $PKG_VERSION" 0
    fi

    REPO=packages-microsoft-com
    PACKAGES=(curl)

    install_required_pkgs ${PACKAGES[@]}

    wait_for_package_manager_to_complete

    ### Configure the repository ###
    sudo zypper addrepo -c -f -n microsoft-$CHANNEL https://packages.microsoft.com/config/$DISTRO/$SCALED_VERSION/$CHANNEL.repo

    ### Fetch the gpg key ###
    curl -sSL https://packages.microsoft.com/keys/microsoft.asc > ./microsoft.asc || script_exit "Unable to fetch gpg key" $?
    sudo rpm --import ./microsoft.asc
    sudo zypper refresh || echo " Unable to refresh the repos properly. Command exited with status $?" >&2

    ### Install MDE ###
    echo "Installing MDE on distro: $DISTRO version: $VERSION"
    if ! sudo zypper install $ASSUMEYES $REPO-$CHANNEL:mdatp; then
        echo "Failed, trying again"
        sudo zypper install mdatp || script_exit "Unable to install MDE" $?
    fi
    echo "Package successfully installed"
}

remove_repo()
{
    # TODO: add support for debian and fedora
    if [ $DISTRO == 'sles' ]; then
        sudo zypper removerepo packages-microsoft-com-$CHANNEL
    else
        echo "unsupported for distro $DISTRO"
    fi
}

upgrade_mdatp()
{
    if [ -z "$1" ]; then
        script_exit "INTERNAL ERROR. upgrade_mdatp requires an argument (the upgrade command)"
    fi

    if ! check_if_pkg_is_installed mdatp; then
        script_exit "MDE package is not installed. Please install it first"
    fi

    sudo $PKG_MGR $1 $ASSUMEYES mdatp || script_exit "Unable to upgrade MDE" $?
    echo "Package successfully upgraded"
}

remove_mdatp()
{
    if ! check_if_pkg_is_installed mdatp; then
        script_exit "MDE package is not installed. Please install it first"
    fi

    sudo $PKG_MGR remove $ASSUMEYES mdatp || script_exit "Unable to remove MDE" $?
    script_exit "Package successfully removed" 0
}

scale_version_id()
{
    ### We dont have pmc repos for rhel versions > 7.4. Generalizing all the 7* repos to 7 and 8* repos to 8
    if [ "$DISTRO" == "rhel" ] || [ "$DISTRO" == "centos" ] || [ "$DISTRO" == "ol" ]; then
        if [[ $VERSION == 7* ]]; then
            SCALED_VERSION=7
        elif [[ $VERSION == 8* ]]; then
            SCALED_VERSION=8
        else
            script_exit "Unsupported version: $DISTRO $VERSION" 7
        fi
    elif [ "$DISTRO" == "sles" ]; then
        if [[ $VERSION == 12* ]]; then
            SCALED_VERSION=12
        elif [[ $VERSION == 15* ]]; then
            SCALED_VERSION=15
        else
            script_exit "Unsupported version: $DISTRO $VERSION" 7
        fi
    else
        SCALED_VERSION=$VERSION
    fi
    echo "Scaled version: $SCALED_VERSION"
}

onboard_device()
{
    echo "onboarding script: $ONBOARDING_SCRIPT"

    if ! check_if_pkg_is_installed mdatp; then
        script_exit "MDE package is not installed. Please install it first"
    fi

    if [ ! -f $ONBOARDING_SCRIPT ]; then
        script_exit "error: onboarding script not found."
    fi

    # Make sure python is installed
    PYTHON=$(which python || which python3)

    if [ -z $PYTHON ]; then
        script_exit "error: cound not locate python."
    fi

    # Run onboarding script
    echo "running onboarding script..."
    sleep 2
    sudo $PYTHON $ONBOARDING_SCRIPT || script_exit "error: onboarding failed" 9
    echo "onboarding successful"
}

set_epp_to_passive_mode()
{
    echo "Settgin MDE/EPP to passive mode"

    if ! check_if_pkg_is_installed mdatp; then
        script_exit "MDE package is not installed. Please install it first"
    fi

    mdatp config passive-mode --value enabled
}

set_device_tags()
{
    for t in "${tags[@]}"
    do
        set -- $t
        if [ "$1" == "GROUP" ] || [ "$1" == "SecurityWorkspaceId" ] || [ "$1" == "AzureResourceId" ] || [ "$1" == "SecurityAgentId" ]; then
            echo "setting tag: ($1, $2)"
            eval "sudo mdatp edr tag set --name $1 --value $2"
        else
            echo "invalid tag name: $1. supported tags: GROUP, SecurityWorkspaceId, AzureResourceId and SecurityAgentId"
            error_code=11
        fi
    done
}

usage()
{
    echo "mde_installer.sh v$SCRIPT_VERSION"
    echo "usage: $1 [OPTIONS]"
    echo "Options:"
    echo " -c|--channel      specify the channel from which you want to install. Default: insiders-fast"
    echo " -i|--install      install the product"
    echo " -r|--remove       remove the product"
    echo " -u|--upgrade      upgrade the existing product"
    echo " -o|--onboard      onboard/offboard the product with <onboarding_script>"
    echo " -p|--passive-mode set EPP to passive mode"
    echo " -t|--tag          set a tag by declaring <name> and <value>. ex: -t GROUP Coders"
    echo " -m|--min_req      enforce minimum requirements"
    echo " -w|--clean        remove repo from package manager for a specific channel"
    echo " -v|--version      print out script version"
    echo " -h|--help         display help"
}

if [ $# -eq 0 ]; then
    usage
    script_exit "No arguments were provided. Specify --help for help"
fi

while [ $# -ne 0 ];
do
    case "$1" in
        -c|--channel)
            if [ -z "$2" ]; then
                script_exit "$1 option requires an argument"
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
        -u|--upgrade)
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
                script_exit "$1 option requires an argument"
            fi
            ONBOARDING_SCRIPT=$2
            verify_privileges "onboard"
            shift 2
            ;;
        -m|--min_req)
            MIN_REQUIREMENTS=1
            shift 1
            ;;
        -p|--passive-mode)
            verify_privileges "passive-mode"
            PASSIVE_MODE=1
            shift 1
            ;;
        -t|--tag)
            if [[ -z "$2" || -z "$3" ]]; then
                script_exit "$1 option requires two arguments"
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
        -v|--version)
            script_exit "$SCRIPT_VERSION" 0
            ;;
        *)
            echo "Unknown argument: '$1'" >&2
            echo "Use -h or --help for usage" >&2
            script_exit "Invalid argument" 2
            ;;
    esac
done

if [[ -z "${INSTALL_MODE}" && -z "${ONBOARDING_SCRIPT}" && -z "${PASSIVE_MODE}" && ${#tags[@]} -eq 0 ]]; then
    script_exit "No installation mode specified. Specify --help for help"
fi

echo "--- mde_installer.sh v$SCRIPT_VERSION ---"

### Validate mininum requirements ###
if [ $MIN_REQUIREMENTS ]; then
    verify_min_requirements
fi

### Detect the distro and version number ###
detect_distro

### Scale the version number according to repos avaiable on pmc ###
scale_version_id

### Set package manager
set_package_manager

if [ "$INSTALL_MODE" == "i" ]; then
    if [ "$DISTRO" == "debian" ] || [ "$DISTRO" == "ubuntu" ]; then
        install_on_debian
    elif [ "$DISTRO" == "rhel" ] || [ "$DISTRO" == "centos" ] || [ "$DISTRO" == "ol" ]; then
        install_on_redhat
    elif [ "$DISTRO" = "sles" ]; then
        install_on_sles
    else
        script_exit "Unsupported distro $DISTRO $VERSION"
    fi

elif [ "$INSTALL_MODE" == "u" ]; then
    if [ "$DISTRO" == "debian" ] || [ "$DISTRO" == "ubuntu" ]; then
        upgrade_mdatp "install --only-upgrade"
    elif [ "$DISTRO" == "rhel" ] || [ "$DISTRO" == "centos" ] || [ "$DISTRO" == "sles" ] || [ "$DISTRO" == "ol" ]; then
        upgrade_mdatp "update"
    else
        script_exit "Unsupported distro"
    fi

elif [ "$INSTALL_MODE" = "r" ]; then
    remove_mdatp

elif [ "$INSTALL_MODE" == "c" ]; then
    remove_repo
fi

if [ $ONBOARDING_SCRIPT ]; then
    onboard_device
fi

if [ $PASSIVE_MODE ]; then
    set_epp_to_passive_mode
fi

if [ ${#tags[@]} -gt 0 ]; then
    set_device_tags
fi

script_exit "--- mde_installer.sh ended. ---" $error_code
