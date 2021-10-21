# Installer scripts

## About the script

`mde_installer.sh` is a bash script that sets up mde on all [supported distros](https://docs.microsoft.com/en-us/windows/security/threat-protection/microsoft-defender-atp/microsoft-defender-atp-linux#system-requirements).

It runs through the steps of the [manual deployment](https://docs.microsoft.com/en-us/windows/security/threat-protection/microsoft-defender-atp/linux-install-manually), and installs MDE.
There are a few extra features for one-line installation like [onboarding](https://docs.microsoft.com/en-us/windows/security/threat-protection/microsoft-defender-atp/linux-install-manually#download-the-onboarding-package).

## How to use

```bash
❯ ./mde_installer.sh --help
mde_installer.sh v0.4.2
usage: basename ./mde_installer.sh [OPTIONS]
Options:
 -c|--channel         specify the channel from which you want to install. Default: insiders-fast
 -i|--install         install the product
 -r|--remove          remove the product
 -u|--upgrade         upgrade the existing product to a newer version if available
 -o|--onboard         onboard/offboard the product with <onboarding_script>
 -p|--passive-mode    set EPP to passive mode
 -t|--tag             set a tag by declaring <name> and <value>. ex: -t GROUP Coders
 -m|--min_req         enforce minimum requirements
 -x|--skip_conflict   skip conflicting application verification
 -w|--clean           remove repo from package manager for a specific channel
 -y|--yes             assume yes for all mid-process prompts (highly reccomended)
 -s|--verbose         verbose output
 -v|--version         print out script version
 -d|--debug           set debug mode
 --proxy <proxy URL>  set proxy
 -h|--help            display help
```

## Sample use case

```bash
sudo ~/mde_installer.sh --install --channel prod --onboard ~/linux_onboarding_script.py --tag GROUP Coders --min_req -y
```

This one-liner would:

1. Check that the device qualifies to run MDE (`--min_req`)
2. Install MDE according to the detected distribution and version and defined channel (`--install` and `--channel prod`):
   1. Install required packages.
   2. Set up the package repository in the package manager.
   3. Pull latest version of MDE and install it.
3. Onboard MDE according to a provided onboarding script (`--onboarding <onboarding_script>`)
4. Once installed, will set a device group tag to the device (`--tag GROUP Coders`)
5. If the machine is behind proxy, use `--proxy` to set proxy url

## Additional details

The installer script can be used to (separatly or combined):

* Install, upgrade or remove the product.
* Onboad or offboard the product.
* Clean package manager from repositry (only SLES for now)

> [!NOTE] API might change in the future, please make sure to validate version.
