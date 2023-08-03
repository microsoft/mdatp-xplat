# This PowerShell script can be used to update the settings.json file.

$settings = @{
    downloadLinuxUpdates      = $true
    downloadMacUpdates        = $true
    downloadPreviewUpdates    = $false
    downloadFolder            = "/tmp/wdav-update"
    logFilePath               = "/tmp/mdatp_offline_updates.log"
}

$settings | ConvertTo-Json | Out-File -FilePath settings.json
