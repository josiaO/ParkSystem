#requires -Version 5.1
<#
.SYNOPSIS
    Watch live camera video for a few minutes. Does not open the gate or print a ticket.

.DESCRIPTION
    SmartPark must already be running (the Desktop shortcut, or the logon tasks).
    This only reads the picture health. It does not create a parking session.

    Double-click Run-CameraLab.bat for all cameras, 15 minutes.
    One camera for 10 minutes:

        powershell -ExecutionPolicy Bypass -File .\Run-CameraLab.ps1 -Camera 1 -Duration 600

.PARAMETER Camera
    Camera id. Omit it to watch every camera.
.PARAMETER Duration
    Seconds to watch. Default 900 (15 minutes).
#>
[CmdletBinding()]
param(
    [int]$Camera = 0,
    [int]$Duration = 900,
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
$Script = Join-Path $InstallDir "tools\camera_lab.py"
if (-not (Test-Path $Script)) {
    $kit = $PSScriptRoot
    $fromKit = Join-Path $kit "payload\tools\camera_lab.py"
    if (Test-Path $fromKit) {
        $Script = $fromKit
        $kitPy = Join-Path $kit "payload\python64\python.exe"
        if (Test-Path $kitPy) { $Py = $kitPy }
    }
}
if (-not (Test-Path $Script)) {
    throw "camera_lab.py is not in this install. Build a new USB kit and run Install-SmartPark.bat again."
}
if (-not (Test-Path $Py)) {
    throw "SmartPark Python was not found at $Py. Run Install-SmartPark.bat first."
}

$logDir = Join-Path $env:ProgramData "SmartParkEdge\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("camera_lab_{0:yyyyMMdd_HHmmss}.txt" -f (Get-Date))

Write-Host "SmartPark camera lab"
Write-Host "Leave SmartPark running. This does not open the gate or print a ticket."
Write-Host "Install folder: $InstallDir"
if ($Camera -gt 0) {
    Write-Host "Watching camera $Camera for $Duration seconds."
} else {
    Write-Host "Watching every camera for $Duration seconds."
}
Write-Host "The result is also saved to:"
Write-Host "  $log"
Write-Host ""

$argsList = @($Script, "--duration", "$Duration", "--url", $Url, "--username", $Username)
if ($Camera -gt 0) {
    $argsList += @("--camera", "$Camera")
} else {
    $argsList += "--all"
}
if ($Password) { $argsList += @("--password", $Password) }

& $Py @argsList 2>&1 | Tee-Object -FilePath $log
$code = $LASTEXITCODE
if ($null -eq $code) { $code = 1 }
Write-Host ""
Write-Host "Saved: $log"
exit $code
