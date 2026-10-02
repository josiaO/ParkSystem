#requires -Version 5.1
<#
.SYNOPSIS
    Promote SmartPark to the MediaMTX realtime pipeline.
.DESCRIPTION
    Persists rollout flags in the SmartPark database, sets matching environment
    defaults, and restarts background tasks. Use CameraId 0 to enable all
    configured cameras. This script is also useful on upgraded installations
    whose old SiteSetting values still select DIRECT_LEGACY.
.PARAMETER CameraId
    Database camera id. 0 (default) means all enabled cameras.
.PARAMETER LiveView
    Switch live view to MediaMTX WebRTC. If omitted, MediaMTX is enabled in
    parallel while DIRECT_LEGACY stays the operator live provider.
.PARAMETER InstallDir
    SmartPark install folder (default %SMARTPARK_HOME%).
#>
[CmdletBinding()]
param(
    [int]$CameraId = 0,
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

$Py64 = Join-Path $InstallDir "python64\python.exe"
if (-not (Test-Path $Py64)) {
    throw "SmartPark Python is missing: $Py64"
}

$cameraLabel = if ($CameraId -gt 0) { "camera $CameraId" } else { "all enabled cameras" }
$cameraIds = if ($CameraId -gt 0) { "$CameraId" } else { "" }
Write-Host "Enabling MediaMTX for $cameraLabel ..."
[Environment]::SetEnvironmentVariable("SMARTPARK_MEDIAMTX_BIN", $mtx, "User")
[Environment]::SetEnvironmentVariable("SMARTPARK_MEDIA_GATEWAY_ENABLED", "true", "User")
[Environment]::SetEnvironmentVariable("SMARTPARK_MEDIA_GATEWAY_CAMERA_IDS", $cameraIds, "User")
if ($LiveView) {
    [Environment]::SetEnvironmentVariable("SMARTPARK_LIVE_VIEW_PROVIDER", "MEDIAMTX", "User")
    [Environment]::SetEnvironmentVariable("SMARTPARK_WEBRTC_LIVE_ENABLED", "true", "User")
    Write-Host "Live view provider: MEDIAMTX (WebRTC)."
} else {
    Write-Host "Parallel mode only (DIRECT_LEGACY live view). Run again with -LiveView after soak."
}

$env:SMARTPARK_HOME = $InstallDir
$env:PYTHONPATH = $InstallDir
$env:SMARTPARK_MEDIAMTX_BIN = $mtx

# SiteSetting overrides environment defaults, so persist the rollout in the DB.
$liveProvider = if ($LiveView) { "MEDIAMTX" } else { "DIRECT_LEGACY" }
$webrtc = if ($LiveView) { "True" } else { "False" }
& $Py64 -c @"
from app.db import SessionLocal
from app.services.flags import save_flags
camera_id = int($CameraId)
with SessionLocal() as db:
    out = save_flags(db, {
        "media_gateway_enabled": True,
        "media_gateway_camera_ids": [camera_id] if camera_id > 0 else [],
        "fastalpr_new_pipeline_enabled": True,
        "recognition_pipeline": "FASTALPR_NEW",
        "live_view_provider": "$liveProvider",
        "webrtc_live_enabled": $webrtc,
        "native_alpr_enabled": True,
    })
print("Saved migration flags:", out)
"@
if ($LASTEXITCODE -ne 0) {
    throw "Could not persist realtime migration flags."
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
if ($CameraId -gt 0) {
    Write-Host "Local RTSP: rtsp://127.0.0.1:8554/cam$CameraId"
    Write-Host "Soak test: powershell -File `"$PSScriptRoot\MediaMTX-SoakTest.ps1`" -CameraId $CameraId"
} else {
    Write-Host "All enabled cameras are registered. Use Hardware Lab to inspect each MediaMTX path."
}
if ($LiveView) {
    Write-Host "LAN WebRTC requires TCP 8889 and UDP 8189 to be reachable from operator PCs."
}
