param([Parameter(Mandatory=$true)][string]$Mt5DataPath)
$ErrorActionPreference = "Stop"
$dst = Join-Path $Mt5DataPath "MQL5"
New-Item -ItemType Directory -Force (Join-Path $dst "Experts/SQX") | Out-Null
New-Item -ItemType Directory -Force (Join-Path $dst "Include/SQX") | Out-Null
Copy-Item "$PSScriptRoot/Experts/SQX/*.mq5" (Join-Path $dst "Experts/SQX") -Force
Copy-Item "$PSScriptRoot/Include/SQX/*.mqh" (Join-Path $dst "Include/SQX") -Force
Write-Host "Copied SQX MQL5 package to $dst. Compile in MetaEditor; compiler status is not inferred by this script."
