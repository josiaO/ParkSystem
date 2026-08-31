#requires -Version 5.1
<#
.SYNOPSIS
    Play local MediaMTX RTSP for N minutes to prove the proxy is smooth.
.PARAMETER CameraId
    Camera database id (default 3 = 2# Entry).
.PARAMETER Minutes
    Soak duration (default 10).
#>
[CmdletBinding()]
param(
    [int]$CameraId = 3,
    [int]$Minutes = 10
)

$ErrorActionPreference = "Stop"
$InstallDir = [Environment]::GetEnvironmentVariable("SMARTPARK_HOME", "User")
if (-not $InstallDir) {
    $InstallDir = Join-Path $env:LOCALAPPDATA "Programs\SmartPark Edge"
}
$Py64 = Join-Path $InstallDir "python64\python.exe"
$Mtx = Join-Path $InstallDir "vendor\mediamtx\mediamtx.exe"
if (-not (Test-Path $Py64)) { throw "Install SmartPark first. Missing $Py64" }
if (-not (Test-Path $Mtx)) { throw "MediaMTX not bundled. Missing $Mtx" }

$env:SMARTPARK_HOME = $InstallDir
$env:PYTHONPATH = $InstallDir
$env:SMARTPARK_MEDIAMTX_BIN = $Mtx
$env:SMARTPARK_MEDIA_GATEWAY_ENABLED = "true"
$env:SMARTPARK_MEDIA_GATEWAY_CAMERA_IDS = "$CameraId"

Write-Host "Registering camera $CameraId with MediaMTX..."
& $Py64 -c @"
import sys
sys.path.insert(0, r'$InstallDir')
from app.db import SessionLocal
from app.models import Camera
from app.services import mediamtx
from app.services.mediamtx_sources import sync_camera
cid = int($CameraId)
with SessionLocal() as db:
    cam = db.get(Camera, cid)
    if cam is None:
        raise SystemExit(f'Camera {cid} not in database. Add site cameras first.')
    out = sync_camera(cam, db=db)
    if not out.get('registered'):
        raise SystemExit(f'Register failed: {out}')
print('Local RTSP:', mediamtx.live_endpoint(cid).get('rtsp'))
print(mediamtx.start())
"@

$local = "rtsp://127.0.0.1:8554/cam$CameraId"
$logDir = Join-Path $env:ProgramData "SmartParkEdge\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("mediamtx_soak_cam{0}_{1:yyyyMMdd_HHmmss}.log" -f $CameraId, (Get-Date))

Write-Host "Soak: ffplay $local for $Minutes minutes"
Write-Host "Log: $log"
$seconds = $Minutes * 60
$ffplay = Get-Command ffplay -ErrorAction SilentlyContinue
if ($ffplay) {
    $proc = Start-Process -FilePath $ffplay.Source -ArgumentList @(
        "-rtsp_transport", "tcp", "-loglevel", "warning", "-autoexit", "-nodisp", $local
    ) -PassThru -NoNewWindow -RedirectStandardError $log -RedirectStandardOutput $log
    $proc | Wait-Process -Timeout $seconds -ErrorAction SilentlyContinue
    if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
} else {
    Write-Warning "ffplay not on PATH. Using ffmpeg null mux for $Minutes minutes."
    $ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if (-not $ffmpeg) { throw "Install ffmpeg and add it to PATH for RTSP soak tests." }
    & $ffmpeg.Source -hide_banner -loglevel warning -rtsp_transport tcp -i $local -t $seconds -f null - 2>&1 | Tee-Object -FilePath $log
}

Write-Host "Soak finished. Review $log"
Write-Host "If smooth, run: powershell -File Enable-MediaMTX.ps1 -CameraId $CameraId -LiveView"
