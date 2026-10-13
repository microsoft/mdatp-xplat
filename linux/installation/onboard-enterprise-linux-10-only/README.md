# How To

## Date: 2026-06-22
## Repository URL: https://packages.microsoft.com/

### Import Microsoft key
sudo rpm --import https://packages.microsoft.com/rhel/10/prod/repodata/repomd.xml.key

### Add repository
sudo dnf install https://packages.microsoft.com/config/rhel/10/packages-microsoft-prod.rpm

### Refresh metadata
sudo dnf clean all
sudo dnf makecache -y

### List configured repos
sudo dnf repolist
sudo dnf repolist all

### Install a package from the new repo (Remember to check what the newest version is !)
sudo dnf install https://packages.microsoft.com/rhel/10/prod/Packages/m/mdatp-101.26032.0000-1.x86_64.rpm

### Onboadring
sudo ./mde_onboard.sh --onboard MicrosoftDefenderATPOnboardingLinuxServer.py --tag GROUP {TAG HERE}

---
