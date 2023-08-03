# Definition Downloader scripts

## About the script

This script is used to download the definition files from the https://go.microsoft.com/fwlink? website.

The scripts does not take any command line arguments, but uses inputs from the settings.json file.
Please copy the settings.json file to the same directory as this script, and update the details in the file correctly before running the script.
As of this version of the scripts (0.0.1), scheduled tasks for downloading update packages cannot be created, and only full signature packages can be downloaded (no delta packages). 
All possible signature update packages specified as part of the settings.json file are downloaded within a specific nested directory structure:

     /home/user/wdav-update/latest
     ├── linux
     │   ├── preview
     │   │   ├── arch_arm64
     │   │   └── arch_x86_64
     │   │       └── updates.zip
     │   └── production
     │       ├── arch_arm64
     │       └── arch_x86_64
     │           └── updates.zip
     └── mac
         ├── preview
         │   ├── arch_arm64
         │   │   └── updates.zip
         │   └── arch_x86_64
         │       └── updates.zip
         └── production
             ├── arch_arm64
             │   └── updates.zip
             └── arch_x86_64
                 └── updates.zip



Sample settings.json
{
  "downloadFolder": "/tmp/wdav-update",
  "downloadLinuxUpdates": true,
  "logFilePath": "/tmp/mdatp_offline_updates.log",
  "downloadMacUpdates": true,
  "downloadPreviewUpdates": false
}


## dependencies
Shell version of the script is dependent on the following tools:
1.  curl
2.  jq

## How to run the script
chmod +x ./xplat_offline_updates_download.sh
./xplat_offline_updates_download.sh

## How to run the script in powershell
1. Open powershell
2. Navigate to the directory where the script is located
3. Update settings.json with the correct values
4. Run the following command:
    `.\xplat_offline_updates_download.ps1`