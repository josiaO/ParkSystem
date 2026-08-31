#requires -Version 5.1
<#
.SYNOPSIS
    Turn on MediaMTX for one camera after the soak test passes.
.DESCRIPTION
    Sets user environment flags and restarts SmartPark background tasks.
    Default camera 3 = 2# Entry (192.168.1.49). MediaMTX stays off until you run this.
.PARAMETER CameraId
    Database camera id (default 3).
.PARAMETER LiveView
    Also switch live view to MediaMTX WebRTC (only after soak test is smooth).
.PARAMETER InstallDir
    SmartPark install folder (default %SMARTPARK_HOME%).
#>
[CmdletBinding()]
param(
    [int]$CameraId = 3,
    [switch]$LiveView,
    [string]$InstallDir = ""
)

$ErrorActionPreference = "Stop"
if (-not $InstallDir) {
    $InstallDir = [Environment]::GetEnvironmentVariable("SMARTPARK_HOME", "User")
    if (-not $InstallDir) {
        $InstallDir = Join-Path $env:LOCALAPPDATA "Programs\SmartPark Edge"
    }
}
if (-not (Test-Path $InstallDir)) {
    throw "SmartPark is not installed at $InstallDir. Run Install-SmartPark.bat first."
}

$mtx = Join-Path $InstallDir "vendor\mediamtx\mediamtx.exe"
if (-not (Test-Path $mtx)) {
    throw "MediaMTX binary missing: $mtx. Rebuild or reinstall the USB kit."
}

Write-Host "Enabling MediaMTX for camera $CameraId ..."
[Environment]::SetEnvironmentVariable("SMARTPARK_MEDIAMTX_BIN", $mtx, "User")
[Environment]::SetEnvironmentVariable("SMARTPARK_MEDIA_GATEWAY_ENABLED", "true", "User")
[Environment]::SetEnvironmentVariable("SMARTPARK_MEDIA_GATEWAY_CAMERA_IDS", "$CameraId", "User")
if ($LiveView) {
    [Environment]::SetEnvironmentVariable("SMARTPARK_LIVE_VIEW_PROVIDER", "MEDIAMTX", "User")
    [Environment]::SetEnvironmentVariable("SMARTPARK_WEBRTC_LIVE_ENABLED", "true", "User")
    Write-Host "Live view provider: MEDIAMTX (WebRTC)."
} else {
    Write-Host "Parallel mode only (DIRECT_LEGACY live view). Run again with -LiveView after soak."
}

foreach ($task in @("SmartPark Media Service", "SmartPark Site Service")) {
    try {
        Stop-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
        Start-ScheduledTask -TaskName $task -ErrorAction Stop
        Write-Host "Restarted: $task"
    } catch {
        Write-Warning "Could not restart $task : $_"
    }
}

Write-Host ""
Write-Host "Check: http://127.0.0.1:8760/media/gateway  (mediamtx.ok should be true)"
Write-Host "Local RTSP: rtsp://127.0.0.1:8554/cam$CameraId"
Write-Host "Soak test:  powershell -File `"$PSScriptRoot\MediaMTX-SoakTest.ps1`" -CameraId $CameraId"
