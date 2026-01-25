#!/bin/bash
#
# shellcheck disable=SC1091
# This script is used to download offline signature updates for Microsoft Defender for Endpoint on Linux / macOS.
#
# This script has dependencies on jq and curl. Please ensure that these programs are installed on the system before running the script.
# The script does not take any command line arguments, but uses inputs from the settings.json file.
# Please copy the settings.json file to the same directory as this script, and update the details in the file correctly before running the script.

# Strict mode for better error handling
set -euo pipefail

# Read version from central VERSION file if it exists
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." 2>/dev/null && pwd)" || REPO_ROOT=""
if [[ -n "${REPO_ROOT}" ]] && [[ -f "${REPO_ROOT}/VERSION" ]]; then
    scriptVersion=$(tr -d '[:space:]' < "${REPO_ROOT}/VERSION")
else
    scriptVersion="1.2.0"  # Fallback version
fi
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

# Function to handle errors
function handle_error()
{
    local exit_code="$1"
    local error_message="$2"
    cleanupUpdateFile=$3
    cleanupManifestFile=$4


    echo "Error ($exit_code): $error_message"
    if [[ -f "$cleanupUpdateFile" ]]; then
        rm -rf "$cleanupUpdateFile"
    fi
    if [[ -f "$cleanupManifestFile" ]]; then
        rm -rf "$cleanupManifestFile"
    fi
    exit "$exit_code"
}



# Checks for new updates by comparing the engine and definition versions in the manifest file and the manifest url.
function is_latest_update_downloaded()
{
    manifestJsonFile=$1
    manifestUrl=$2

    # Use secure temp file creation
    local tempFile
    tempFile=$(mktemp -t "mdatp_manifest.XXXXXX") || {
        echo "Failed to create secure temporary file"
        return 1
    }

    # Ensure temp file is cleaned up on function exit
    trap 'rm -f "$tempFile"' RETURN

    # Use jq to extract the Engine and Definition versions from the JSON file
    engine_version_prev=$(jq -r '.EngineVersion' "$manifestJsonFile")
    definition_version_prev=$(jq -r '.DefinitionVersion' "$manifestJsonFile")

    if ! curl -L -o "$tempFile" "$manifestUrl"; then
        echo "Curl failed"
        handle_error $? "Failed to download manifest from $manifestUrl"
    fi
    sync
    echo "Curl success"
    # Extract and log the engine version
    engine_version=$(awk -F'</?engine>' 'NF>1{print $2}' "$tempFile")
    # Extract and log the definition version using sed
    definition_version=$(sed -n 's/.*<signatures date=".*">\([^<]*\)<\/signatures>.*/\1/p' "$tempFile")


    # Print the extracted versions
    echo "Engine Version: $engine_version"
    echo "Definition Version: $definition_version"
    echo "Engine version Prev: $engine_version_prev"
    echo "Definiton Version Prev: $definition_version_prev"

    # check for version for match
    if [[ "$engine_version_prev" = "$engine_version" ]] && [[ "$definition_version_prev" = "$definition_version" ]]; then
        return 0
    else
        return 1
    fi
}

# Constructs the list of URLs and downloads the signature updates.
function invoke_download_all_updates() 
{
    local platform=$1
    local downloadPreviewUpdates=$2
    local baseUpdateUrl=$3
    local downloadFolder=$4
    local backupPreviousUpdates=$5
    
    echo "------------ Downloading $platform updates! with $backupPreviousUpdates------------"
    
    package="updates.zip"
    previewRingArgs="&engRing=3&sigRing=1"
    armArchArgs="&arch=arm64"
    archs=("x86_64" "arm64")
    json_file="manifest.json"
    rings=("production")
    
    if [[ "$downloadPreviewUpdates" == true ]]; then
        rings+=("preview")
    fi
    
    for ring in "${rings[@]}"; do
        for arch in "${archs[@]}"; do
            path="$downloadFolder/$platform/$ring/arch_$arch"
            savePath="$path/$package"
            tempSavePath="$savePath"_temp
            currentManifestPath="$path/$json_file"
            downloadedManifestXML="$path/manifest.xml"
            
            if [[ ! -d "$path" ]]; then
                mkdir -p "$path"
            fi
            
            linkid=$(get_link_id "$platform")
            url="$baseUpdateUrl?linkid=$linkid"
            
            if [[ "$arch" == "arm64" ]]; then
                url="$url$armArchArgs"
            fi
            
            if [[ "$ring" == "preview" ]]; then
                url="$url$previewRingArgs"
            fi

            manifestUrl="$url&action=info"

            if [[ -f "$currentManifestPath" ]]; then
                if is_latest_update_downloaded "$currentManifestPath" "$manifestUrl"; then
                    echo "No new update available"
                    continue;
                fi
            fi

            if [[ "$backupPreviousUpdates" == true ]]; then
                backupPath="$downloadFolder/$platform/$ring""_back/arch_$arch"
                echo "Backing up previous updates to $backupPath"
                if [[ ! -d "$backupPath" ]]; then
                    mkdir -p "$backupPath"
                fi
                if [[ -f "$savePath" ]] && [[ -f "$currentManifestPath" ]]; then
                    echo "copying from $path to $backupPath"
                    cp -rf "$savePath" "$backupPath"
                    cp -rf "$currentManifestPath" "$backupPath"
                else
                    echo "File does not exist"  
                fi
            fi

            echo "Downloading from $url and saving to folder $path"
            if ! curl -L -o "$tempSavePath" "$url"; then
                handle_error $? "Failed to download $url" "$tempSavePath" "$downloadedManifestXML"
            fi
            if ! curl -L -o "$downloadedManifestXML" "$manifestUrl"; then
                handle_error $? "Failed to download manifest from $manifestUrl" "$tempSavePath" "$downloadedManifestXML"
            fi

            mv "$tempSavePath" "$savePath"

            # Extract and log the engine version
            engine_version=$(awk -F'</?engine>' 'NF>1{print $2}' "$downloadedManifestXML")
            write_log_message "$logFilePath" "Engine version: $engine_version"
            
            # Extract and log the definition version using sed
            definition_version=$(sed -n 's/.*<signatures date=".*">\([^<]*\)<\/signatures>.*/\1/p' "$downloadedManifestXML")
            write_log_message "$logFilePath" "Definition version: $definition_version."
            # Create a JSON structure and format it with jq
            json_data=$(jq -n --arg engine "$engine_version" --arg definition "$definition_version" \
                        '{ "EngineVersion": $engine, "DefinitionVersion": $definition }')
            # Save JSON data to a file
            echo "$json_data" > "$currentManifestPath"
            rm -rf "$downloadedManifestXML"
        done
    done
}

# Main
echo ""
echo "------ xplat_offline_updates_download.sh version $scriptVersion ------"
echo ""
# Get the directory containing this script
scriptDir="$(dirname "$0")"

echo "The script is being executed from: $scriptDir"

if ! [[ -x "$(command -v jq)" ]]; then
    echo "Exiting script since jq is not installed. Please install jq and then re-run the script."
    exit 0
fi

if ! [[ -x "$(command -v curl)" ]]; then
    echo "Exiting script since curl is not installed. Please install curl and then re-run the script."
    exit 0
fi

if [[ -f "$scriptDir/settings.json" ]]; then
    echo "Reading input parameters from settings.json file"
else
    echo "Exiting script since settings.json file does not exist. Please copy the settings.json file to the same directory as the script and then re-run the script."
    exit 0
fi

settings=$(jq . < "$scriptDir"/settings.json)

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

backupPreviousUpdates=$(echo "$settings" | jq -r '.backupPreviousUpdates')
if [[ $backupPreviousUpdates == "null" ]]; then 
    backupPreviousUpdates=false
fi

baseUpdateUrl="$defaultBaseUpdateUrl"

echo "Using log file: $logFilePath"
echo "Using base update url: $baseUpdateUrl"
echo "Using download folder: $downloadFolder"
echo "Using backup previous updates: $backupPreviousUpdates"

clear_log_file "$logFilePath"

write_log_message "$logFilePath" "Script started."

if [[ "$downloadLinuxUpdates" == true ]]; then
    invoke_download_all_updates "linux" "$downloadPreviewUpdates" "$baseUpdateUrl" "$downloadFolder" "$backupPreviousUpdates"
fi

if [[ "$downloadMacUpdates" == true ]]; then
    invoke_download_all_updates "mac" "$downloadPreviewUpdates" "$baseUpdateUrl" "$downloadFolder" "$backupPreviousUpdates"
fi

write_log_message "$logFilePath" "Script completed."
