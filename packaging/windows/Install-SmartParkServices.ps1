#requires -Version 5.1
<#
.SYNOPSIS
    Register SmartPark background processes so parking does not need the Desktop UI.
    The main installer runs this automatically.
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

function Register-SmartParkTask {
    param(
        [string]$Name,
        [string]$Command,
        [string]$WorkingDirectory
    )
    Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue
    $action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c $Command" -WorkingDirectory $WorkingDirectory
    $triggerLogon = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
    try {
        $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
        Register-ScheduledTask -TaskName $Name -Action $action -Trigger $triggerLogon -Settings $settings -Principal $principal -Force | Out-Null
    } catch {
        Register-ScheduledTask -TaskName $Name -Action $action -Trigger $triggerLogon -Settings $settings -Force | Out-Null
    }
    Start-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
}

$mtxBin = ""
if (Test-Path $MediaMtx) {
    $mtxBin = "set SMARTPARK_MEDIAMTX_BIN=$MediaMtx&& "
}
$envPrefix = "set SMARTPARK_HOME=$InstallDir&& set PYTHONPATH=$InstallDir&& set SMARTPARK_HVX_VENDOR_DIR=$InstallDir\vendor&& ${mtxBin}set PATH=$InstallDir\python64;$InstallDir\python64\Scripts;$InstallDir\vendor;%PATH%"
$siteCmd = "$envPrefix&& `"$Py64`" -m app.site_service"
$hostCmd = "$envPrefix&& `"$Py32`" `"$HostPy`""
$mediaCmd = "$envPrefix&& `"$Py64`" -m app.media_service"

Write-Host "Registering SmartPark background tasks..."
$failed = @()
try {
    Register-SmartParkTask -Name "SmartPark Site Service" -Command $siteCmd -WorkingDirectory $InstallDir
} catch {
    $failed += "Site Service: $_"
}
if (Test-Path $Py32) {
    try {
        Register-SmartParkTask -Name "SmartPark HVX Host" -Command $hostCmd -WorkingDirectory (Join-Path $InstallDir "tools\hvx_sdk_host")
    } catch {
        $failed += "HVX host: $_"
    }
} else {
    Write-Host "HVX host skipped: 32-bit Python is not in this kit."
}
if (Test-Path $MediaMtx) {
    try {
        Register-SmartParkTask -Name "SmartPark Media Service" -Command $mediaCmd -WorkingDirectory $InstallDir
    } catch {
        $failed += "Media Service: $_"
    }
} else {
    Write-Host "Media Service skipped: vendor\mediamtx\mediamtx.exe not in this kit."
}
if ($failed.Count -gt 0) {
    throw ($failed -join "; ")
}

Write-Host ""
Write-Host "Background tasks:"
Write-Host "  SmartPark Site Service   (API + camera events, port 8760)"
Write-Host "  SmartPark HVX Host       (32-bit NetSDK, port 8765)"
if (Test-Path $MediaMtx) {
    Write-Host "  SmartPark Media Service  (MediaMTX sidecar; idle until SMARTPARK_MEDIA_GATEWAY_ENABLED=true)"
}
Write-Host "Desktop is only a client. Parking continues if the UI is closed."
Write-Host "MediaMTX: off by default. After soak, run Enable-MediaMTX.ps1 from the install/USB folder."
Write-Host "Recovery: Windows restarts each task up to 3 times, 1 minute apart."
