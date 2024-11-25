<#
.SYNOPSIS

    This script is used to download offline signature updates for Microsoft Defender for Endpoint on Linux / macOS.

.DESCRIPTION

    This script can be can be used to download Linux / macOS signature updates, by using pwsh, on Linux / macOS host machines. 
    The script does not take any command line arguments, but uses inputs from the settings.json file. Please update the details in the settings.json file correctly before running the script.
    As of this version of the script (0.0.2), scheduled tasks for downloading update packages cannot be created, and only full signature packages can be downloaded (no delta packages). 
    All possible signature update packages specified as part of the settings.json file are downloaded within a specific nested directory structure:
    /home/user/wdav-update/latest
    ├── mac
    │   ├── preview_back
    │   │   ├── arch_arm64
    │   │   └── arch_x86_64
    │   ├── preview
    │   │   ├── arch_arm64
    │   │   │   ├── manifest.json
    │   │   │   └── updates.zip
    │   │   └── arch_x86_64
    │   │       ├── manifest.json
    │   │       └── updates.zip
    │   ├── production_back
    │   │   ├── arch_arm64
    │   │   └── arch_x86_64
    │   └── production
    │       ├── arch_arm64
    │       │   ├── manifest.json
    │       │   └── updates.zip
    │       └── arch_x86_64
    │           ├── manifest.json
    │           └── updates.zip
    └── linux
        ├── preview
        │   ├── arch_x86_64
        │   │   ├── manifest.json
        │   │   └── updates.zip
        │   ├── arch_arm64
        ├── preview_back
        │   ├── arch_x86_64
        │   │   ├── manifest.json
        │   │   └── updates.zip
        ├── production
        │   ├── arch_x86_64
        │   │   ├── manifest.json
        │   │   └── updates.zip
        │   ├── arch_arm64
        └── production_back
            ├── arch_x86_64
            │   ├── manifest.json
            │   └── updates.zip 
#>

$scriptVersion = "0.0.2"
$defaultBaseUpdateUrl = "https://go.microsoft.com/fwlink/"
$defaultDownloadFolder = "$env:HOME" + "/wdav-update"
$defaultLogFilePath = "/tmp/mdatp_offline_updates.log"
$global:logFilePath = ""

# If a string field is part of a given json object, returns the corresponding value, else returns the default value.
Function Set-String-Param($object, [string]$fieldName, [string]$defaultValue)
{
    $value = $defaultValue
    if ($fieldName -in $object.PSobject.Properties.Name)
    {
        $value = $object.$fieldName
    }
    return $value
}

# If a boolean field is part of a given json object, returns the corresponding value, else returns the default value of false.
Function Set-Bool-Param($object, [string]$fieldName)
{
    $value = $false
    if ($fieldName -in $object.PSobject.Properties.Name)
    {
        $value = $object.$fieldName
    }
    return $value
}

# Returns the linkid associated with the platform.
Function Get-Link-Id([string] $platform)
{
    if ($platform -eq "linux")
    {
        return "2144709"
    }
    else # ($platform -eq "mac")
    {
        return "2120136"
    }
}

# Flushes the log file if it is bigger than 100 KB.
Function Clear-Log-File()
{
    if (Test-Path $global:logFilePath)
    {
        $file = Get-Item $global:logFilePath    
        if ($file.Length -gt 100KB)
        {
            "" | Out-File $file
        }
    }
    else
    {
        New-Item $global:logFilePath -type file
        Write-Output "Log file created."
    }
}

# Appends a message to log file path with the time stamp.
Function Write-Log-Message([string]$message)
{
    Write-Output $message
    $date = Get-Date
    $date | Out-File $global:logFilePath -Append
    $message | Out-File $global:logFilePath -Append
    "----------End of message----------" | Out-File $global:logFilePath -Append
}

# function to handle error from Invoke-WebRequest
function Handle-Error([string]$errorMessage, [string]$updateFilePath, [string]$manifestPath)
{

    Write-Host "Error: $errorMessage"
    # Add your custom error handling logic here, such as logging or exiting the script
    $null = Remove-Item -Path $updateFilePath -Force -ErrorAction SilentlyContinue
    $null = Remove-Item -Path $manifestPath -Force -ErrorAction SilentlyContinue
    exit 1
} 

# Checks for new updates by comparing the engine and definition versions in the manifest file and the manifest url.
function is_latest_update_downloaded([string]$manifestFile, [string]$manifestUrl)
{
    $tempFile = "temp.txt"
    Write-Host "File path: $manifestFile"

    # Read the JSON content from manifest.json
    $jsonContent = Get-Content -Raw -Path $manifestFile | ConvertFrom-Json

    # Extract the engine and definition versions from the JSON content
    $engine_version_prev = $jsonContent.EngineVersion
    $definition_version_prev = $jsonContent.DefinitionVersion



    try
    {
        Invoke-WebRequest -Uri $manifestUrl -OutFile $tempFile
        Write-Host "File downloaded successfully: $tempFile"
    }
    catch
    {
        Handle-Error -errorMessage "Failed to download file from $manifestUrl"
    }

    # Extract and log the engine version using regex
    $engine_version = (Get-Content $tempFile | Select-String -Pattern "<engine>(.*?)<\/engine>").Matches.Groups[1].Value
    # Extract and log the definition version using regex
    $definition_version = [regex]::Match((Get-Content $tempFile), '<signatures date=".*?">(.*?)<\/signatures>').Groups[1].Value

    # Print the extracted versions
    Write-Host "Engine Version Prev: $engine_version_prev"
    Write-Host "Definition Version Prev: $definition_version_prev"
    Write-Host "Engine version: $engine_version"
    Write-Host "Definition Version: $definition_version"

    $null = Remove-Item -Path $tempFile -Force -ErrorAction SilentlyContinue

    # Trim leading and trailing spaces from the versions
    $engine_version = $engine_version.Trim()
    $definition_version = $definition_version.Trim()
    $engine_version_prev = $engine_version_prev.Trim()
    $definition_version_prev = $definition_version_prev.Trim()

    # Check for version match
    if ($engine_version_prev -eq $engine_version -and $definition_version_prev -eq $definition_version) {
        return $true
    } else {
        return $false
    }
}

# Constructs the list of urls and downloads the signature updates.
Function Invoke-Download-All-Updates([string]$platform, [bool]$downloadPreviewUpdates, [string]$baseUpdateUrl, [string]$downloadFolder)
{
    Write-Log-Message "------------ Downloading $platform updates! ------------"

    $package = "updates.zip"
    $previewRingArgs = "&engRing=3&sigRing=1"
    $armArchArgs = "&arch=arm64"
    $archs = @("x86_64", "arm64")
    $rings = @("production")
    $json_file="manifest.json"
    if ($downloadPreviewUpdates)
    {
        $rings += ("preview")
    }

    foreach ($ring in $rings)
    {
        foreach ($arch in $archs)
        {
            Write-Host "....... Start ........"
            $path = $downloadFolder + "/$platform/$ring/arch_$arch"
            $savePath = "$path/$package"
            $tempSavePath="$savePath"+"_temp"
            $currentManifestPath="$path/$json_file"
            $downloadedManifestXML="$path/manifest.xml"

            if (!(Test-Path -PathType container $path))
            {
                New-Item -ItemType Directory -Path $path
            }
            $linkid = Get-Link-Id $platform
            $url = $baseUpdateUrl + "?linkid=$linkid"
            if ($arch -eq "arm64")
            {
                $url = $url + $armArchArgs
            }
            if ($ring -eq "preview")
            {
                $url = $url + $previewRingArgs
            }
            $manifestUrl = $url + "&action=info"
            # Example usage:
            if (Test-Path -PathType leaf $currentManifestPath)
            {
                $isUpdateDownloaded = is_latest_update_downloaded -manifestFile $currentManifestPath -manifestUrl $manifestUrl

                if ($isUpdateDownloaded -eq $true) {
                    Write-Host "Got value eq to 0 -eq $isUpdateDownloaded"
                    continue;
                }
            }

            if ($backupPreviousUpdates)
            {
                $backupPath="$downloadFolder/$platform/$ring"+"_back"+"/arch_$arch"
                Write-Log-Message "Backing up previous updates to folder $backupPath"
                if (!(Test-Path -PathType container $backupPath))
                {
                    New-Item -ItemType Directory -Path $backupPath
                }
                # Test if $savePath exists and is a file
                $savePathExists = Test-Path -PathType Leaf $savePath
                # Test if $currentManifestPath exists and is a file
                $currentManifestExists = Test-Path -PathType Leaf $currentManifestPath
                # Check both conditions
                if ($savePathExists -and $currentManifestExists) {
                    Copy-Item -Path $savePath -Destination $backupPath  -Recurse -Force
                    Copy-Item -Path $currentManifestPath -Destination $backupPath  -Recurse -Force
                }
                else
                {
                    Write-Log-Message "No previous updates found."
                }
            }

            Write-Log-Message "Downloading from $url and saving to folder $path"
            try
            {
                Invoke-WebRequest -Uri "$url" -OutFile $tempSavePath -ErrorAction Stop
                Write-Host "File downloaded successfully: $tempSavePath"
            }
            catch
            {
                Handle-Error -errorMessage "Failed to download file from $url" -updateFilePath $tempSavePath  -manifestPath $downloadedManifestXML
            }
            try
            {
                Invoke-WebRequest -Uri "$manifestUrl" -OutFile $downloadedManifestXML
                Write-Host "File downloaded successfully: $downloadedManifestXML"
            }
            catch
            {
                Handle-Error -errorMessage "Failed to download file from $manifestUrl" -updateFilePath $tempSavePath  -manifestPath $downloadedManifestXML
            }

            Move-Item -Path "$tempSavePath" -Destination "$savePath"  -Force
            # Extract and log the engine version using regex
            $engine_version = (Get-Content $downloadedManifestXML | Select-String -Pattern "<engine>(.*?)<\/engine>").Matches.Groups[1].Value
            # Extract and log the definition version using regex
            $definition_version = [regex]::Match((Get-Content $downloadedManifestXML), '<signatures date=".*?">(.*?)<\/signatures>').Groups[1].Value

            # Create a PowerShell object to hold the versions
            $versions = @{
                "EngineVersion" = $engine_version
                "DefinitionVersion" = $definition_version
                }
            $versions | ConvertTo-Json | Set-Content -Path $currentManifestPath
            $null = Remove-Item -Path $downloadedManifestXML -Force -ErrorAction SilentlyContinue
        }
    }
}

# Main
try
{
    $Error.clear()

    Write-Output ""
    Write-Output "------ xplat_offline_updates_download.ps1 version: $scriptVersion ------"
    Write-Output ""
    # Get the directory from which the script is being executed
    $scriptDir = Split-Path -Path $MyInvocation.MyCommand.Path -Parent


    Write-Host "The script is being executed from: $scriptDir"

    $settings = Get-Content -Path $scriptDir"/settings.json" | ConvertFrom-Json
    $global:logFilePath = Set-String-Param $settings "logFilePath" $defaultLogFilePath
    $baseUpdateUrl = $defaultBaseUpdateUrl
    $downloadFolder = Set-String-Param $settings "downloadFolder" $defaultDownloadFolder
    $downloadLinuxUpdates = Set-Bool-Param $settings "downloadLinuxUpdates"
    $downloadMacUpdates = Set-Bool-Param $settings "downloadMacUpdates"
    $downloadPreviewUpdates = Set-Bool-Param $settings "downloadPreviewUpdates"
    $backupPreviousUpdates = Set-Bool-Param $settings "backupPreviousUpdates"

    Write-Output "Using log file: $global:logFilePath"
    Write-Output "Using base update url: $baseUpdateUrl"
    Write-Output "Using download folder: $downloadFolder"
    Write-Output "Using backup previous updates: $backupPreviousUpdates"

    Clear-Log-File

    Write-Log-Message "Script started."
    
    if ($downloadLinuxUpdates)
    {
        Invoke-Download-All-Updates -platform "linux" -downloadPreviewUpdates $downloadPreviewUpdates -baseUpdateUrl $baseUpdateUrl -downloadFolder $downloadFolder -backupPreviousUpdates $backupPreviousUpdates | Out-Default
    }
    
    if ($downloadMacUpdates)
    {
        Invoke-Download-All-Updates -platform "mac" -downloadPreviewUpdates $downloadPreviewUpdates -baseUpdateUrl $baseUpdateUrl -downloadFolder $downloadFolder -backupPreviousUpdates $backupPreviousUpdates | Out-Default
    } 

    Write-Log-Message "Script completed."
}
catch [System.Exception]
{
    Write-Log-Message $Error
}
