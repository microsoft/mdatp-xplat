<#
.SYNOPSIS

    This script is used to download offline signature updates for Microsoft Defender for Endpoint on Linux / macOS.

.DESCRIPTION

    This script can be can be used to download Linux / macOS signature updates, by using pwsh, on Linux / macOS host machines. 
    The script does not take any command line arguments, but uses inputs from the settings.json file. Please update the details in the settings.json file correctly before running the script.
    As of this version of the script (0.0.1), scheduled tasks for downloading update packages cannot be created, and only full signature packages can be downloaded (no delta packages). 
    All possible signature update packages specified as part of the settings.json file are downloaded within a specific nested directory structure:
     /home/user/wdav-update/latest
     ├── linux
     │   ├── preview
     │   │   ├── arch_arm64
     │   │   └── arch_x86_64
     │   │       └── updates.zip
     │   ├── preview_back
     │   │   ├── arch_arm64
     │   │   └── arch_x86_64
     │   │       └── updates.zip
     │   └── production
     │   │   ├── arch_arm64
     │   │   └── arch_x86_64
     │   │       └── updates.zip
     │   └── production_back
     │       ├── arch_arm64
     │       └── arch_x86_64
     │           └── updates.zip
     └── mac
     │   ├── preview
     │   │   ├── arch_arm64
     │   │   |   └── updates.zip
     │   │   └── arch_x86_64
     │   │       └── updates.zip
     │   ├── preview_back
     │   │   ├── arch_arm64
     │   │   |   └── updates.zip
     │   │   └── arch_x86_64
     │   │       └── updates.zip
     │   └── production
     │   │   ├── arch_arm64
     │   │   |   └── updates.zip
     │   │   └── arch_x86_64
     │   │       └── updates.zip
     │   └── production_back
     │       ├── arch_arm64
     │       |   └── updates.zip
     │       └── arch_x86_64
     │           └── updates.zip
     
#>

$scriptVersion = "0.0.1"
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

# Constructs the list of urls and downloads the signature updates.
Function Invoke-Download-All-Updates([string]$platform, [bool]$downloadPreviewUpdates, [string]$baseUpdateUrl, [string]$downloadFolder)
{
    Write-Log-Message "------------ Downloading $platform updates! ------------"

    $package = "updates.zip"
    $previewRingArgs = "&engRing=3&sigRing=1"
    $armArchArgs = "&arch=arm64"
    $archs = @("x86_64", "arm64")
    $rings = @("production")
    if ($downloadPreviewUpdates)
    {
        $rings += ("preview")
    }

    foreach ($ring in $rings)
    {
        foreach ($arch in $archs)
        {
            $path = $downloadFolder + "/$platform/$ring/arch_$arch"
            $savePath = "$path/$package"

            if (!(Test-Path -PathType container $path))
            {
                New-Item -ItemType Directory -Path $path
            }

            if (($platform -eq "linux") -and ($arch -eq "arm64"))
            {
                continue # currently, we do not support linux arm64, so we skip the download step in this case
            }

            $linkid = Get-Link-Id $platform
            $url = $baseUpdateUrl + "?linkid=$linkid"

            if (($platform -eq "mac") -and ($arch -eq "arm64"))
            {
                $url = $url + $armArchArgs
            }

            if ($ring -eq "preview")
            {
                $url = $url + $previewRingArgs
            }

            Write-Log-Message "Downloading from $url and saving to folder $path"
            if ($backupPreviousUpdates)
            {
                $backupPath="$downloadFolder/$platform/$ring"+"_back"
                Write-Log-Message "Backing up previous updates to folder $backupPath"
                if (!(Test-Path -PathType container $backupPath))
                {
                    New-Item -ItemType Directory -Path $backupPath
                }
                if (Test-Path -PathType leaf $savePath)
                {
                    Copy-Item -Path $path -Destination $backupPath  -Recurse -Force
                }
                else
                {
                    Write-Log-Message "No previous updates found."
                }

            }
            Invoke-WebRequest -Uri "$url" -OutFile $savePath
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

    $settings = Get-Content -Path settings.json | ConvertFrom-Json
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
