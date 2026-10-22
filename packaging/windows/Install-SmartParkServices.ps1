#requires -Version 5.1
<#
.SYNOPSIS
    Register SmartPark background processes so parking does not need the Desktop UI.
    The main installer runs this automatically. This scheduled-task path stays
    the supported default until Install-SmartParkWinService.ps1 is verified on
    site hardware — do not remove this file in the same change as SCM.
#>
[CmdletBinding()]
param(
    [string]$InstallDir = ""
)

$ErrorActionPreference = "Stop"

if (-not $InstallDir) {
    $InstallDir = [Environment]::GetEnvironmentVariable("SMARTPARK_HOME", "User")
    if (-not $InstallDir) {
        $InstallDir = Join-Path $env:LOCALAPPDATA "Programs\SmartPark Edge"
    }
}
$Py64 = Join-Path $InstallDir "python64\python.exe"
$Py32 = Join-Path $InstallDir "python32\python.exe"
$HostPy = Join-Path $InstallDir "tools\hvx_sdk_host\hvx_host.py"
$MediaMtx = Join-Path $InstallDir "vendor\mediamtx\mediamtx.exe"
if (-not (Test-Path $Py64)) {
    throw "Install SmartPark Edge first. Missing $Py64"
}

function Write-SmartParkLauncher {
    param(
        [string]$BatName,
        [string]$PythonExe,
        [string]$Arguments
    )
    $bat = Join-Path $InstallDir $BatName
    $mtxLine = ""
    if (Test-Path $MediaMtx) {
        $mtxLine = "set `"SMARTPARK_MEDIAMTX_BIN=$MediaMtx`""
    }
    @"
@echo off
setlocal
cd /d "$InstallDir"
set "SMARTPARK_HOME=$InstallDir"
set "PYTHONPATH=%SMARTPARK_HOME%"
set "SMARTPARK_HVX_VENDOR_DIR=%SMARTPARK_HOME%\vendor"
if not defined SMARTPARK_DEPLOYMENT_PROFILE set "SMARTPARK_DEPLOYMENT_PROFILE=PRODUCTION"
$mtxLine
set "PATH=%SMARTPARK_HOME%\python64;%SMARTPARK_HOME%\python64\Scripts;%SMARTPARK_HOME%\vendor;%PATH%"
"$PythonExe" $Arguments
"@ | Set-Content -Path $bat -Encoding ASCII
    return $bat
}

function Register-SmartParkTask {
    param(
        [string]$Name,
        [string]$Launcher,
        [string]$WorkingDirectory
    )
    Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue
    # Quote the launcher. "SmartPark Edge" has a space; an unquoted set-chain
    # makes Start-ScheduledTask fail and the installer never opens the app.
    $action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument ("/c `"{0}`"" -f $Launcher) -WorkingDirectory $WorkingDirectory
    $taskUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $triggerLogon = New-ScheduledTaskTrigger -AtLogOn -User $taskUser
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
    try {
        $principal = New-ScheduledTaskPrincipal -UserId $taskUser -LogonType Interactive -RunLevel Limited
        Register-ScheduledTask -TaskName $Name -Action $action -Trigger $triggerLogon -Settings $settings -Principal $principal -Force | Out-Null
    } catch {
        Register-ScheduledTask -TaskName $Name -Action $action -Trigger $triggerLogon -Settings $settings -Force | Out-Null
    }
    try {
        Start-ScheduledTask -TaskName $Name -ErrorAction Stop
    } catch {
        throw "registered, but Windows did not start it: $($_.Exception.Message)"
    }
}

$siteBat = Write-SmartParkLauncher -BatName "run-site-service.bat" -PythonExe $Py64 -Arguments "-m app.site_service"
$recognitionBat = Write-SmartParkLauncher -BatName "run-recognition-worker.bat" -PythonExe $Py64 -Arguments "-m app.recognition_worker"
$hostBat = ""
if (Test-Path $Py32) {
    $hostBat = Write-SmartParkLauncher -BatName "run-hvx-host.bat" -PythonExe $Py32 -Arguments "`"$HostPy`""
}
$mediaBat = ""
if (Test-Path $MediaMtx) {
    $mediaBat = Write-SmartParkLauncher -BatName "run-media-service.bat" -PythonExe $Py64 -Arguments "-m app.media_service"
}

Write-Host "Registering SmartPark background tasks..."
$failed = @()
try {
    Register-SmartParkTask -Name "SmartPark Site Service" -Launcher $siteBat -WorkingDirectory $InstallDir
} catch {
    $failed += "Site Service: $_"
}
try {
    Register-SmartParkTask -Name "SmartPark Recognition Worker" -Launcher $recognitionBat -WorkingDirectory $InstallDir
} catch {
    $failed += "Recognition Worker: $_"
}
if ($hostBat) {
    try {
        Register-SmartParkTask -Name "SmartPark HVX Host" -Launcher $hostBat -WorkingDirectory (Join-Path $InstallDir "tools\hvx_sdk_host")
    } catch {
        $failed += "HVX host: $_"
    }
} else {
    Write-Host "HVX host skipped: 32-bit Python is not in this kit."
}
if ($mediaBat) {
    try {
        Register-SmartParkTask -Name "SmartPark Media Service" -Launcher $mediaBat -WorkingDirectory $InstallDir
    } catch {
        $failed += "Media Service: $_"
    }
} else {
    Write-Host "Media Service skipped: vendor\mediamtx\mediamtx.exe not in this kit."
}
if ($failed.Count -gt 0) {
    Write-Host ("WARNING: {0}" -f ($failed -join "; "))
    Write-Host "The desktop and browser will still open. Site Service starts with the desktop if a task did not."
    exit 0
}

Write-Host ""
Write-Host "Background tasks:"
Write-Host "  SmartPark Site Service   (API + camera events, port 8760)"
Write-Host "  SmartPark Recognition Worker (warm models and local MediaMTX decoders)"
Write-Host "  SmartPark HVX Host       (32-bit NetSDK, port 8765)"
if (Test-Path $MediaMtx) {
    Write-Host "  SmartPark Media Service  (MediaMTX realtime gateway when enabled by effective site flags)"
}
Write-Host "Desktop is only a client. Parking continues if the UI is closed."
Write-Host "Fresh installs prefer MediaMTX/WebRTC when the bundled binary is available; upgraded sites keep their stored rollout flags."
Write-Host "To promote an upgraded site explicitly, run Enable-MediaMTX.ps1 -LiveView."
Write-Host "Recovery: Windows restarts each task up to 3 times, 1 minute apart."
