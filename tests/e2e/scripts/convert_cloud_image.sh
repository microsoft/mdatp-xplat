#!/bin/bash
# Convert cloud qcow2 images to Vagrant boxes for libvirt
# 
# This script downloads official cloud images and converts them to Vagrant boxes.
# It's much faster than building from scratch with Packer.
#
# The script uses virt-customize (from libguestfs-tools) to:
# 1. Create a 'vagrant' user with sudo access
# 2. Install the Vagrant insecure public key (Vagrant replaces this on first boot)
# 3. Configure passwordless sudo for the vagrant user
#
# Requirements:
#   - libguestfs-tools (provides virt-customize)
#   - wget
#   - qemu-img
#
# Usage:
#   ./convert_cloud_image.sh debian 12
#   ./convert_cloud_image.sh debian 11
#   ./convert_cloud_image.sh debian 10
#   ./convert_cloud_image.sh fedora 42
#   ./convert_cloud_image.sh fedora 43
#   ./convert_cloud_image.sh --all    # Convert all supported images

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="${SCRIPT_DIR}/build"
BOX_OUTPUT_DIR="${SCRIPT_DIR}/boxes"

# Vagrant insecure public key - Vagrant will replace this on first boot
# https://github.com/hashicorp/vagrant/blob/main/keys/vagrant.pub
VAGRANT_INSECURE_KEY="ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEA6NF8iallvQVp22WDkTkyrtvp9eWW6A8YVr+kz4TjGYe7gHzIw+niNltGEFHzD8+v1I2YJ6oXevct1YeS0o9HZyN1Q9qgCgzUFtdOKLv6IedplqoPkcmF0aYet2PkEDo3MlTBckFXPITAMzF8dJSIFo9D8HfdOV0IAdx4O7PtixWKn5y2hMNG0zQPyUecp4pzC6kivAIhyfHilFR61RGL+GPXQ2MWZWFYbAGjyiYJnAmCP3NOTd0jMZEnDkbUvxhMmBYSdETk1rRgm+R4LOzFUGaHqHDLKLX+FIPKcF96hrucXzcWyLbIbEgE98OHlnVYCzRdK8jlqm8tehUc9c9WhQ== vagrant insecure public key"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

check_dependencies() {
    local missing=()
    
    if ! command -v virt-customize &> /dev/null; then
        missing+=("virt-customize (libguestfs-tools)")
    fi
    
    if ! command -v wget &> /dev/null; then
        missing+=("wget")
    fi
    
    if ! command -v qemu-img &> /dev/null; then
        missing+=("qemu-img")
    fi
    
    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "Missing required tools:"
        for tool in "${missing[@]}"; do
            echo "  - ${tool}"
        done
        echo ""
        log_info "Install with: sudo pacman -S libguestfs wget qemu-img"
        return 1
    fi
}

# Image definitions: DISTRO_VERSION -> (URL, BOX_NAME, CODENAME)
declare -A CLOUD_IMAGES=(
    # Debian uses "nocloud" variant - no cloud metadata required, uses DHCP
    ["debian_12"]="https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-nocloud-amd64.qcow2|local/debian12|bookworm"
    ["debian_11"]="https://cloud.debian.org/images/cloud/bullseye/latest/debian-11-nocloud-amd64.qcow2|local/debian11|bullseye"
    ["debian_10"]="https://cloud.debian.org/images/cloud/buster/latest/debian-10-nocloud-amd64.qcow2|local/debian10|buster"
    # Fedora uses "Generic" variant - works with libvirt without cloud-init
    # Note: Fedora 40/41 are EOL and moved to archives.fedoraproject.org
    # Fedora 42 has alvistack/fedora-42 with libvirt support
    ["fedora_40"]="https://archives.fedoraproject.org/pub/archive/fedora/linux/releases/40/Cloud/x86_64/images/Fedora-Cloud-Base-Generic.x86_64-40-1.14.qcow2|local/fedora40|40"
    ["fedora_41"]="https://archives.fedoraproject.org/pub/archive/fedora/linux/releases/41/Cloud/x86_64/images/Fedora-Cloud-Base-Generic-41-1.4.x86_64.qcow2|local/fedora41|41"
    ["fedora_43"]="https://download.fedoraproject.org/pub/fedora/linux/releases/43/Cloud/x86_64/images/Fedora-Cloud-Base-Generic-43-1.6.x86_64.qcow2|local/fedora43|43"
)

create_vagrantfile() {
    local output_file="$1"
    local guest_type="${2:-debian}"  # default to debian for backward compatibility
    cat > "$output_file" << VAGRANTFILE
Vagrant.configure("2") do |config|
  config.vm.provider :libvirt do |libvirt|
    libvirt.driver = "kvm"
    libvirt.memory = 2048
    libvirt.cpus = 2
  end
  
  # Use vagrant user (created by convert script with insecure key)
  config.ssh.username = "vagrant"
  
  # Use the insecure key - Vagrant will replace it on first boot
  config.ssh.insert_key = true
  
  # Tell Vagrant the guest OS type for correct guest capabilities
  config.vm.guest = :${guest_type}
  
  # Disable default synced folder (we'll configure via runner)
  config.vm.synced_folder ".", "/vagrant", disabled: true
end
VAGRANTFILE
}

create_metadata() {
    local output_file="$1"
    cat > "$output_file" << 'METADATA'
{
  "provider": "libvirt",
  "format": "qcow2",
  "virtual_size": 128
}
METADATA
}

# Create Debian-specific customization script
create_debian_customize_script() {
    local output_file="$1"
    cat > "$output_file" << 'SCRIPT'
#!/bin/bash
set -e
# Fix Debian 10 (buster) repos - it's archived
if grep -q 'buster' /etc/os-release 2>/dev/null; then
    echo 'deb http://archive.debian.org/debian buster main' > /etc/apt/sources.list
    echo 'deb http://archive.debian.org/debian-security buster/updates main' >> /etc/apt/sources.list
    echo 'Acquire::Check-Valid-Until "false";' > /etc/apt/apt.conf.d/99no-check-valid-until
fi
apt-get update -qq
apt-get install -y -qq openssh-server sudo rsync
ssh-keygen -A
systemctl enable ssh.service
SCRIPT
    chmod +x "$output_file"
}

# Create Fedora-specific customization script
create_fedora_customize_script() {
    local output_file="$1"
    cat > "$output_file" << 'SCRIPT'
#!/bin/bash
set -e
# Fedora uses dnf and sshd (not ssh)
dnf install -y -q openssh-server sudo rsync
ssh-keygen -A
systemctl enable sshd.service
SCRIPT
    chmod +x "$output_file"
}

# Get distro family from distro name
get_distro_family() {
    local distro="$1"
    case "$distro" in
        debian|ubuntu) echo "debian" ;;
        fedora|rhel|centos|rocky|alma|amazon) echo "rhel" ;;
        *) echo "unknown" ;;
    esac
}

# Get Vagrant guest type from distro name
get_guest_type() {
    local distro="$1"
    case "$distro" in
        debian) echo "debian" ;;
        ubuntu) echo "ubuntu" ;;
        fedora) echo "fedora" ;;
        rhel|centos|rocky|alma) echo "redhat" ;;
        amazon) echo "redhat" ;;
        *) echo "linux" ;;
    esac
}

convert_image() {
    local distro="$1"
    local version="$2"
    local key="${distro}_${version}"
    
    if [[ ! -v CLOUD_IMAGES[$key] ]]; then
        log_error "Unknown image: ${distro} ${version}"
        log_info "Supported images:"
        for k in "${!CLOUD_IMAGES[@]}"; do
            echo "  - ${k/_/ }"
        done
        return 1
    fi
    
    # Parse the image definition
    IFS='|' read -r url box_name codename <<< "${CLOUD_IMAGES[$key]}"
    local distro_family
    distro_family=$(get_distro_family "$distro")
    local guest_type
    guest_type=$(get_guest_type "$distro")
    
    log_info "Converting ${distro} ${version} (${codename})"
    log_info "  URL: ${url}"
    log_info "  Box name: ${box_name}"
    log_info "  Distro family: ${distro_family}"
    
    # Create work directories
    mkdir -p "${WORK_DIR}/${key}" "${BOX_OUTPUT_DIR}"
    local work="${WORK_DIR}/${key}"
    
    # Download image if not already present
    local qcow2_file="${work}/box.img"
    local qcow2_orig="${work}/original.qcow2"
    
    if [[ -f "${qcow2_orig}" ]]; then
        log_info "Image already downloaded, reusing..."
    else
        log_info "Downloading image..."
        if ! wget -q --show-progress -O "${qcow2_orig}" "${url}"; then
            log_error "Failed to download image"
            rm -f "${qcow2_orig}"
            return 1
        fi
    fi
    
    # Verify it's a valid qcow2
    if ! qemu-img info "${qcow2_orig}" | grep -q "file format: qcow2"; then
        log_error "Downloaded file is not a valid qcow2 image"
        return 1
    fi
    
    # Create a working copy for customization
    log_info "Creating working copy of image..."
    
    # Resize the disk - cloud images are typically 2GB which is too small
    # virt-resize will copy and expand the partition in one step
    log_info "Resizing disk to 30GB (this may take a minute)..."
    
    # Create a new empty disk of the target size
    qemu-img create -f qcow2 "${qcow2_file}" 30G
    
    # Use virt-resize to copy and expand the main partition
    # --expand /dev/sda1 expands the root partition to fill the disk
    export LIBGUESTFS_BACKEND=direct
    if ! virt-resize --expand /dev/sda1 "${qcow2_orig}" "${qcow2_file}"; then
        log_error "Failed to resize image"
        return 1
    fi
    
    # Customize the image: add vagrant user with insecure key
    log_info "Customizing image (adding vagrant user, enabling SSH)..."
    
    # Create the authorized_keys content
    local auth_keys_file="${work}/authorized_keys"
    echo "${VAGRANT_INSECURE_KEY}" > "${auth_keys_file}"
    
    # Create sudoers file for vagrant user - must work without tty
    # Format is critical: no trailing whitespace, proper permissions (440)
    local sudoers_file="${work}/vagrant-sudoers"
    cat > "${sudoers_file}" << 'SUDOERS'
Defaults:vagrant !requiretty
Defaults:vagrant !fqdn
vagrant ALL=(ALL:ALL) NOPASSWD:ALL
SUDOERS
    
    # Create SSH config to enable legacy ssh-rsa keys (disabled by default in Debian 12+/Fedora 33+)
    local sshd_config_file="${work}/vagrant-sshd.conf"
    cat > "${sshd_config_file}" << 'SSHD_CONFIG'
# Enable legacy ssh-rsa key type for Vagrant insecure key
PubkeyAcceptedKeyTypes +ssh-rsa
HostkeyAlgorithms +ssh-rsa
SSHD_CONFIG

    # Create distro-specific package installation script
    local pkg_install_script="${work}/install-packages.sh"
    case "$distro_family" in
        debian)
            create_debian_customize_script "${pkg_install_script}"
            ;;
        rhel)
            create_fedora_customize_script "${pkg_install_script}"
            ;;
        *)
            log_error "Unsupported distro family: ${distro_family}"
            return 1
            ;;
    esac
    
    # Use virt-customize to modify the image
    # Note: Running without sudo - if this fails, user needs to be in libvirt group
    # or run with LIBGUESTFS_BACKEND=direct
    export LIBGUESTFS_BACKEND=direct
    
    if ! virt-customize -a "${qcow2_file}" \
        --run-command "groupadd -f sudo || groupadd -f wheel" \
        --run-command "useradd -m -s /bin/bash vagrant || true" \
        --run-command "usermod -aG sudo vagrant 2>/dev/null || usermod -aG wheel vagrant" \
        --run-command "echo 'vagrant:vagrant' | chpasswd" \
        --run-command "mkdir -p /home/vagrant/.ssh" \
        --run-command "chmod 700 /home/vagrant/.ssh" \
        --upload "${auth_keys_file}:/home/vagrant/.ssh/authorized_keys" \
        --run-command "chmod 600 /home/vagrant/.ssh/authorized_keys" \
        --run-command "chown -R vagrant:vagrant /home/vagrant/.ssh" \
        --run-command "rm -f /etc/sudoers.d/*" \
        --upload "${sudoers_file}:/etc/sudoers.d/vagrant" \
        --run-command "chmod 440 /etc/sudoers.d/vagrant" \
        --run-command "chown root:root /etc/sudoers.d/vagrant" \
        --run-command "visudo -cf /etc/sudoers.d/vagrant" \
        --upload "${pkg_install_script}:/tmp/install-packages.sh" \
        --run-command "/tmp/install-packages.sh" \
        --run-command "rm -f /tmp/install-packages.sh" \
        --run-command "mkdir -p /etc/ssh/sshd_config.d" \
        --run-command "rm -f /etc/ssh/sshd_config.d/*.conf" \
        --upload "${sshd_config_file}:/etc/ssh/sshd_config.d/vagrant.conf" \
        --run-command "sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config || true" \
        --run-command "sed -i 's/^#*PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config || true" \
        --run-command "sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config || true" \
        --run-command "mkdir -p /mde_repo && chown vagrant:vagrant /mde_repo" \
        --run-command "grep -q '^127.0.0.1' /etc/hosts || echo '127.0.0.1 localhost' >> /etc/hosts" \
        --run-command "iptables -F || true" \
        --run-command "rm -f /etc/machine-id" \
        --run-command "truncate -s 0 /etc/machine-id"; then
        log_error "Failed to customize image with virt-customize"
        log_info "Make sure you're in the 'libvirt' group or try: LIBGUESTFS_BACKEND=direct $0 $*"
        return 1
    fi
    
    # Clean up temp files
    rm -f "${auth_keys_file}" "${sudoers_file}" "${sshd_config_file}" "${pkg_install_script}"
    
    # Create Vagrantfile and metadata
    log_info "Creating box metadata..."
    create_vagrantfile "${work}/Vagrantfile" "${guest_type}"
    create_metadata "${work}/metadata.json"
    
    # Create the box
    local box_file="${BOX_OUTPUT_DIR}/${distro}${version}.box"
    log_info "Creating Vagrant box..."
    (cd "${work}" && tar czvf "${box_file}" metadata.json Vagrantfile box.img)
    
    # Check if box already exists in Vagrant
    if vagrant box list | grep -q "^${box_name} "; then
        log_warn "Box ${box_name} already exists, removing old version..."
        vagrant box remove "${box_name}" --provider libvirt --force || true
    fi
    
    # Add box to Vagrant
    log_info "Adding box to Vagrant..."
    vagrant box add --name "${box_name}" "${box_file}"
    
    log_info "✅ Successfully created box: ${box_name}"
    log_info "   Box file: ${box_file}"
    log_info ""
    log_info "To use in e2e tests, update distro_parser.py:"
    log_info "   \"${version}\": (\"${version}\", \"${codename}\", \"${box_name}\"),"
    
    return 0
}

convert_all() {
    log_info "Converting all supported cloud images..."
    local failed=0
    
    for key in "${!CLOUD_IMAGES[@]}"; do
        IFS='_' read -r distro version <<< "${key}"
        if ! convert_image "${distro}" "${version}"; then
            log_error "Failed to convert ${distro} ${version}"
            ((failed++))
        fi
        echo ""
    done
    
    if [[ ${failed} -gt 0 ]]; then
        log_error "${failed} image(s) failed to convert"
        return 1
    fi
    
    log_info "✅ All images converted successfully!"
}

cleanup() {
    log_info "Cleaning up work directory..."
    rm -rf "${WORK_DIR}"
    log_info "Done. Box files preserved in: ${BOX_OUTPUT_DIR}"
}

usage() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS] <distro> <version>

Convert cloud qcow2 images to Vagrant boxes for libvirt.

Options:
  --all       Convert all supported images
  --cleanup   Remove work directory (keeps box files)
  --list      List supported images
  -h, --help  Show this help

Examples:
  $(basename "$0") debian 12       # Convert Debian 12 (Bookworm)
  $(basename "$0") debian 11       # Convert Debian 11 (Bullseye)  
  $(basename "$0") --all           # Convert all supported images

Supported images:
EOF
    for key in "${!CLOUD_IMAGES[@]}"; do
        IFS='|' read -r url box_name codename <<< "${CLOUD_IMAGES[$key]}"
        echo "  ${key/_/ } -> ${box_name} (${codename})"
    done
}

# Main

# Check dependencies first (except for help/list commands)
case "${1:-}" in
    -h|--help|--list|"")
        # No dependency check needed for these commands
        ;;
    *)
        check_dependencies
        ;;
esac

case "${1:-}" in
    --all)
        convert_all
        ;;
    --cleanup)
        cleanup
        ;;
    --list)
        for key in "${!CLOUD_IMAGES[@]}"; do
            IFS='|' read -r url box_name codename <<< "${CLOUD_IMAGES[$key]}"
            echo "${key/_/ } -> ${box_name} (${codename})"
        done
        ;;
    -h|--help|"")
        usage
        exit 0
        ;;
    *)
        if [[ -z "${2:-}" ]]; then
            log_error "Missing version argument"
            usage
            exit 1
        fi
        convert_image "$1" "$2"
        ;;
esac
