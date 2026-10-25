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
$TaskUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name

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
    $triggerLogon = New-ScheduledTaskTrigger -AtLogOn -User $taskUser
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
    try {
        $principal = New-ScheduledTaskPrincipal -UserId $taskUser -LogonType Interactive -RunLevel Limited
        Register-ScheduledTask -TaskName $Name -Action $action -Trigger $triggerLogon -Settings $settings -Principal $principal -Force | Out-Null
    } catch {
        Register-ScheduledTask -TaskName $Name -Action $action -Trigger $triggerLogon -Settings $settings -Force | Out-Null
    }
}

function Start-SmartParkTask {
    param([string]$Name)
    try {
        Start-ScheduledTask -TaskName $Name -ErrorAction Stop
    } catch {
        throw "registered, but Windows did not start '$Name': $($_.Exception.Message)"
    }
}

function Wait-SmartParkHttp {
    param(
        [string]$Url,
        [string]$Label,
        [int]$TimeoutSeconds = 30
    )
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            if ([int]$response.StatusCode -ge 200 -and [int]$response.StatusCode -lt 500) {
                return
            }
        } catch {
            # The process may still be starting. Keep polling until the bounded deadline.
        }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "$Label did not answer $Url within $TimeoutSeconds seconds. Check the SmartPark logs."
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
$registered = @()
try {
    Register-SmartParkTask -Name "SmartPark Site Service" -Launcher $siteBat -WorkingDirectory $InstallDir
    $registered += "SmartPark Site Service"
} catch {
    $failed += "Site Service: $_"
}
try {
    Register-SmartParkTask -Name "SmartPark Recognition Worker" -Launcher $recognitionBat -WorkingDirectory $InstallDir
    $registered += "SmartPark Recognition Worker"
} catch {
    $failed += "Recognition Worker: $_"
}
if ($hostBat) {
    try {
        Register-SmartParkTask -Name "SmartPark HVX Host" -Launcher $hostBat -WorkingDirectory (Join-Path $InstallDir "tools\hvx_sdk_host")
        $registered += "SmartPark HVX Host"
    } catch {
        $failed += "HVX host: $_"
    }
} else {
    Write-Host "HVX host skipped: 32-bit Python is not in this kit."
}
if ($mediaBat) {
    try {
        Register-SmartParkTask -Name "SmartPark Media Service" -Launcher $mediaBat -WorkingDirectory $InstallDir
        $registered += "SmartPark Media Service"
    } catch {
        $failed += "Media Service: $_"
    }
} else {
    Write-Host "Media Service skipped: vendor\mediamtx\mediamtx.exe not in this kit."
}
if ($failed.Count -gt 0) {
    throw ($failed -join "; ")
}

# Start in dependency order. The tasks remain registered with an AtLogOn
# trigger, so the same sequence is repeated automatically after the next
# Windows sign-in. The Site Service also has its own duplicate-safe fallback,
# but starting the explicit host first makes HVX diagnostics deterministic.
foreach ($name in @("SmartPark HVX Host", "SmartPark Site Service", "SmartPark Media Service", "SmartPark Recognition Worker")) {
    if ($registered -contains $name) {
        Write-Host "Starting $name..."
        Start-SmartParkTask -Name $name
    }
}

if ($registered -contains "SmartPark HVX Host") {
    Wait-SmartParkHttp -Url "http://127.0.0.1:8765/info" -Label "HVX SDK host" -TimeoutSeconds 30
}
if ($registered -contains "SmartPark Site Service") {
    Wait-SmartParkHttp -Url "http://127.0.0.1:8760/health/live" -Label "Site Service" -TimeoutSeconds 45
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
Write-Host "Automatic startup: tasks run for $taskUser at Windows logon; no manual Start-SmartPark.bat is required."
