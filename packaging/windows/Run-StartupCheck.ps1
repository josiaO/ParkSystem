#requires -Version 5.1
<#
.SYNOPSIS
    Check live video, one recognition read, and a gate dry-run after SmartPark starts.
.DESCRIPTION
    Start SmartPark first (the desktop shortcut or the logon tasks), then run this.
    The gate step sends dry_run=true. It does not pulse the barrier or print a ticket.
.PARAMETER Seconds
    How long to watch the live picture. Default 20.
#>
[CmdletBinding()]
param(
    [int]$Seconds = 20,
    [string]$Url = "http://127.0.0.1:8760",
    [string]$Username = "admin",
    [string]$Password = ""
)

$ErrorActionPreference = "Stop"
$InstallDir = [Environment]::GetEnvironmentVariable("SMARTPARK_HOME", "User")
if (-not $InstallDir) {
    $InstallDir = Join-Path $env:LOCALAPPDATA "Programs\SmartPark Edge"
}

$Py = Join-Path $InstallDir "python64\python.exe"
$Script = Join-Path $InstallDir "tools\startup_check.py"
if (-not (Test-Path $Script)) {
    $kit = $PSScriptRoot
    $fromKit = Join-Path $kit "payload\tools\startup_check.py"
    if (Test-Path $fromKit) {
        $Script = $fromKit
        $kitPy = Join-Path $kit "payload\python64\python.exe"
        if (Test-Path $kitPy) { $Py = $kitPy }
    }
}
if (-not (Test-Path $Script)) { throw "startup_check.py not found. Reinstall SmartPark from the USB kit." }
if (-not (Test-Path $Py)) {
    $Py = (Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1).Source
    if (-not $Py) { throw "Python not found. Install SmartPark first." }
}

Write-Host "SmartPark startup check"
Write-Host "SmartPark must already be running. This does not open the barrier."
Write-Host "Script: $Script"
$argsList = @($Script, "--url", $Url, "--username", $Username, "--seconds", "$Seconds")
if ($Password) { $argsList += @("--password", $Password) }
& $Py @argsList
exit $LASTEXITCODE
