#!/bin/bash

# This script is used to download offline signature updates for Microsoft Defender for Endpoint on Linux / macOS.

# This script has dependencies on jq and curl. Please ensure that these programs are installed on the system before running the script.
# The script does not take any command line arguments, but uses inputs from the settings.json file.
# Please copy the settings.json file to the same directory as this script, and update the details in the file correctly before running the script.
# As of this version of the script (0.0.1), scheduled tasks for downloading update packages cannot be created, and only full signature packages can be downloaded (no delta packages). 
# All possible signature update packages specified as part of the settings.json file are downloaded within a specific nested directory structure:
#     /home/user/wdav-update/latest
#     ├── linux
#     │   ├── preview
#     │   │   ├── arch_arm64
#     │   │   └── arch_x86_64
#     │   │       └── updates.zip
#     │   └── production
#     │       ├── arch_arm64
#     │       └── arch_x86_64
#     │           └── updates.zip
#     └── mac
#         ├── preview
#         │   ├── arch_arm64
#         │   │   └── updates.zip
#         │   └── arch_x86_64
#         │       └── updates.zip
#         └── production
#             ├── arch_arm64
#             │   └── updates.zip
#             └── arch_x86_64
#                 └── updates.zip

scriptVersion="0.0.1"
defaultBaseUpdateUrl="https://go.microsoft.com/fwlink/"
defaultDownloadFolder="$HOME/wdav-update"
defaultLogFilePath="/tmp/mdatp_offline_updates.log"
logFilePath=""

# Returns the linkid associated with the platform.
function get_link_id() 
{
    local platform=$1
    
    if [[ "$platform" == "linux" ]]; then
        echo "2144709"
    else
        echo "2120136"
    fi
}

# Flushes the log file if it is bigger than 100 KB.
function clear_log_file() 
{
    local logFile=$1
    
    if [[ -f "$logFile" ]]; then
        local fileSizeKb
        fileSizeKb=$(du -k "$logFile" | cut -f1)
        local threshold=102400  # 100 KB
        
        if [[ $fileSizeKb -gt $threshold ]]; then
            echo "" > "$logFile"
        fi
    else
        touch "$logFile"
        echo "Log file created."
    fi
}

# Appends a message to log file path with the time stamp.
function write_log_message() 
{
    local logFile=$1
    local message=$2

    # (SC2155: Declare and assign separately to avoid masking return values.)
    # shellcheck disable=2155
    local date=$(date)

    echo "$message"
    {
        echo "$date"
        echo "$message"
        echo "----------End of message----------"
    } >> "$logFile"
}

# Constructs the list of URLs and downloads the signature updates.
function invoke_download_all_updates() 
{
    local platform=$1
    local downloadPreviewUpdates=$2
    local baseUpdateUrl=$3
    local downloadFolder=$4
    
    echo "------------ Downloading $platform updates! ------------"
    
    package="updates.zip"
    previewRingArgs="&engRing=3&sigRing=1"
    armArchArgs="&arch=arm64"
    archs=("x86_64" "arm64")
    rings=("production")
    
    if [[ "$downloadPreviewUpdates" == true ]]; then
        rings+=("preview")
    fi
    
    for ring in "${rings[@]}"; do
        for arch in "${archs[@]}"; do
            path="$downloadFolder/$platform/$ring/arch_$arch"
            savePath="$path/$package"
            
            if [[ ! -d "$path" ]]; then
                mkdir -p "$path"
            fi
            
            if [[ ( "$platform" == "linux" ) && ( "$arch" == "arm64" ) ]]; then
                continue  # Currently, we do not support Linux ARM64, so we skip the download step in this case.
            fi
            
            linkid=$(get_link_id "$platform")
            url="$baseUpdateUrl?linkid=$linkid"
            
            if [[ ( "$platform" == "mac" ) && ( "$arch" == "arm64" ) ]]; then
                url="$url$armArchArgs"
            fi
            
            if [[ "$ring" == "preview" ]]; then
                url="$url$previewRingArgs"
            fi
            
            echo "Downloading from $url and saving to folder $path"
            curl -L -o "$savePath" "$url"
        done
    done
}

# Main
echo ""
echo "------ xplat_offline_updates_download.sh version $scriptVersion ------"
echo ""

if ! [ -x "$(command -v jq)" ]; then
    echo "Exiting script since jq is not installed. Please install jq and then re-run the script."
    exit 0
fi

if ! [ -x "$(command -v curl)" ]; then
    echo "Exiting script since curl is not installed. Please install curl and then re-run the script."
    exit 0
fi

if [ -f "settings.json" ]; then
    echo "Reading input parameters from settings.json file"
else
    echo "Exiting script since settings.json file does not exist. Please copy the settings.json file to the same directory as the script and then re-run the script."
    exit 0
fi

settings=$(cat settings.json | jq .)

logFilePath=$(echo "$settings" | jq -r '.logFilePath')
if [[ $logFilePath == "null" ]]; then 
    logFilePath=$defaultLogFilePath
fi

downloadFolder=$(echo "$settings" | jq -r '.downloadFolder')
if [[ $downloadFolder == "null" ]]; then 
    downloadFolder=$defaultDownloadFolder
fi

downloadLinuxUpdates=$(echo "$settings" | jq -r '.downloadLinuxUpdates')
if [[ $downloadLinuxUpdates == "null" ]]; then 
    downloadLinuxUpdates=false
fi

downloadMacUpdates=$(echo "$settings" | jq -r '.downloadMacUpdates')
if [[ $downloadMacUpdates == "null" ]]; then 
    downloadMacUpdates=false
fi

downloadPreviewUpdates=$(echo "$settings" | jq -r '.downloadPreviewUpdates')
if [[ $downloadPreviewUpdates == "null" ]]; then 
    downloadPreviewUpdates=false
fi

baseUpdateUrl="$defaultBaseUpdateUrl"

echo "Using log file: $logFilePath"
echo "Using base update url: $baseUpdateUrl"
echo "Using download folder: $downloadFolder"

clear_log_file "$logFilePath"

write_log_message "$logFilePath" "Script started."

if [[ "$downloadLinuxUpdates" == true ]]; then
    invoke_download_all_updates "linux" "$downloadPreviewUpdates" "$baseUpdateUrl" "$downloadFolder"
fi

if [[ "$downloadMacUpdates" == true ]]; then
    invoke_download_all_updates "mac" "$downloadPreviewUpdates" "$baseUpdateUrl" "$downloadFolder"
fi

write_log_message "$logFilePath" "Script completed."
