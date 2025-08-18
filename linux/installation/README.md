# Installer scripts

## About the script

`mde_installer.sh` is a bash script that can install MDE on all [supported distros](https://docs.microsoft.com/en-us/windows/security/threat-protection/microsoft-defender-atp/microsoft-defender-atp-linux#system-requirements). With the help of installer script, you can not just install but also onboard MDE on your endpoints.

## How to use

1. Download onboarding package from the Microsft Defender Portal. For guidance, refer to the [steps](https://learn.microsoft.com/en-us/defender-endpoint/linux-install-manually#download-the-onboarding-package)
2. Give executable permission to the installer script
```bash
chmod +x /mde_installer.sh
```
3. Execute the installer script with appropriate parameters such as (onboard, channel, realtime protection, etc) based on your requirements. Check help for all the available options

```bash
❯ ./mde_installer.sh --help
mde_installer.sh v0.8.0
usage: basename ./mde_installer.sh [OPTIONS]
Options:
 -c|--channel         specify the channel(insiders-fast / insiders-slow / prod) from which you want to install. Default: prod
 -i|--install         install the product
 -r|--remove          uninstall the product
 -u|--upgrade         upgrade the existing product to a newer version if available
 -l|--downgrade       downgrade the existing product to a older version if available
 -o|--onboard         onboard the product with <onboarding_script>
 -f|--offboard        offboard the product with <offboarding_script>
 -p|--passive-mode    set real time protection to passive mode
 -a|--rtp-mode        set real time protection to active mode. passive-mode and rtp-mode are mutually exclusive
 -t|--tag             set a tag by declaring <name> and <value>, e.g: -t GROUP Coders
 -m|--min_req         enforce minimum requirements
 -x|--skip_conflict   skip conflicting application verification
 -w|--clean           remove repo from package manager for a specific channel
 -y|--yes             assume yes for all mid-process prompts (default, depracated)
 -n|--no              remove assume yes sign
 -s|--verbose         verbose output
 -v|--version         print out script version
 -d|--debug           set debug mode
 --log-path <PATH>    also log output to PATH
 --http-proxy <URL>   set http proxy
 --https-proxy <URL>  set https proxy
 --ftp-proxy <URL>    set ftp proxy
 --mdatp              specific version of mde to be installed. will use the latest if not provided
 --use-local-repo     this will skip the MDE repo setup and use the already configured repo instead
 -b|--install-path    specify the installation and configuration path for MDE. Default: /
 -h|--help            display help
```

> [!NOTE] ARM64 release is only available on insiders-slow channel

## Sample use case

```bash
sudo ~/mde_installer.sh --install --channel prod --onboard ~/MicrosoftDefenderATPOnboardingLinuxServer.py --tag GROUP Coders --min_req -y
```

This one-liner will:

1. Check if the device qualifies to run MDE (`--min_req`). Aborts installation, if the check fails
2. Install MDE according to the detected distribution and version and defined channel (`--install` and `--channel prod`):
   1. Install required packages
   2. Set up the package repository in the package manager
   3. Pull latest version of MDE from production and install it
3. Onboard MDE according to a provided onboarding script (`--onboarding <onboarding_script>`)
4. Once installed, will set a device group tag to the device (`--tag GROUP Coders`)

## Additional details

> [!NOTE] To onboard a device that was previously offboarded you must remove the mdatp_offboard.json file located at /etc/opt/microsoft/mdatp.

The installer script can be used to (separatly or combined):

* Install, upgrade or uninstall the product.
* Onboad or offboard the product.
* Clean package manager from repositry (only SLES for now)

> [!NOTE] API might change in the future, please make sure to validate version.
