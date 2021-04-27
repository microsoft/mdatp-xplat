#Clear the screen
clear
# Set the directory path where the output is located
$Directory = "C:\temp\High_CPU_util_parser_for_Linux"
# Set the path to where the input file (in Json format) is located
$InputFilename = ".\real_time_protection_logs"
# Set the path to where the file (in csv format)is located
$OutputFilename = ".\real_time_protection_logs_converted.csv"
# Change directory
cd $Directory
# Convert from json
$json = Get-Content $InputFilename | convertFrom-Json | select -expand value
# Convert to CSV and sort by the totalFilesScanned column
##  -“NoTypeInformation switched parameter. This will keep the Type information from being written to the first line of the file. If the Type information is written, it will mess up the column display in Excel.
### Optional, you could try using -Unique to remove the 0 files that are not part of the performance impact.
$json |Sort-Object -Property totalFilesScanned -“Descending | ConvertTo-Csv -NoTypeInformation  | Out-File $OutputFilename -Encoding ascii
#Open up in Microsoft Excel
Invoke-Item $OutputFilename
