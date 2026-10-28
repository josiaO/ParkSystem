#requires -Version 5.1
<#
.SYNOPSIS
    Optional Windows Service (SCM) registration for Site Service and HVX host.

    This is an alternative to the scheduled-task supervisor. It removes the
    scheduled-task owners before registering SCM services so two supervisors
    can never compete for ports or instance locks.
#>
[CmdletBinding()]
param(
    [string]$InstallDir = "",
    [switch]$FallbackToScheduledTasks
)

$ErrorActionPreference = "Stop"

if (-not $InstallDir) {
    $InstallDir = [Environment]::GetEnvironmentVariable("SMARTPARK_HOME", "User")
    if (-not $InstallDir) {
        $InstallDir = Join-Path $env:LOCALAPPDATA "Programs\SmartPark Edge"
    }
}

$Nssm = Join-Path $InstallDir "vendor\nssm\nssm.exe"
$TaskScript = Join-Path $PSScriptRoot "Install-SmartParkServices.ps1"

function Register-WithNssm {
    param([string]$Name, [string]$Exe, [string]$Args, [string]$WorkDir)
    & $Nssm stop $Name | Out-Null
    & $Nssm remove $Name confirm | Out-Null
    & $Nssm install $Name $Exe $Args
    & $Nssm set $Name AppDirectory $WorkDir
    & $Nssm set $Name Start SERVICE_AUTO_START
    & $Nssm set $Name AppRestartDelay 5000
    $profile = [Environment]::GetEnvironmentVariable("SMARTPARK_DEPLOYMENT_PROFILE", "User")
    if (-not $profile) { $profile = "PRODUCTION" }
    $nodeRole = [Environment]::GetEnvironmentVariable("SMARTPARK_NODE_ROLE", "User")
    if (-not $nodeRole) { $nodeRole = "SERVER" }
    & $Nssm set $Name AppEnvironmentExtra "SMARTPARK_DEPLOYMENT_PROFILE=$profile" "SMARTPARK_NODE_ROLE=$nodeRole" "SMARTPARK_HOME=$InstallDir" "PYTHONPATH=$InstallDir" "SMARTPARK_HVX_VENDOR_DIR=$InstallDir\vendor"
    & $Nssm start $Name
}

if (-not (Test-Path $Nssm)) {
    Write-Host "nssm.exe is not in this kit. Scheduled-task install remains the supported path."
    if ($FallbackToScheduledTasks -and (Test-Path $TaskScript)) {
        & $TaskScript -InstallDir $InstallDir
    }
    return
}

$Py64 = Join-Path $InstallDir "python64\python.exe"
$Py32 = Join-Path $InstallDir "python32\python.exe"
$HostPy = Join-Path $InstallDir "tools\hvx_sdk_host\hvx_host.py"
if (-not (Test-Path $Py64)) {
    throw "Install SmartPark Edge first. Missing $Py64"
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run Install-SmartParkWinService.ps1 from an elevated PowerShell window."
}

Write-Host "Removing scheduled-task owners before registering SCM services..."
foreach ($task in @(
    "SmartPark Site Service",
    "SmartPark Recognition Worker",
    "SmartPark HVX Host",
    "SmartPark Media Service"
)) {
    Stop-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 1
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $cmd = [string]$_.CommandLine
    $cmd -and (
        $cmd -like "*hvx_host.py*" -or
        $cmd -like "*app.site_service*" -or
        $cmd -like "*app.media_service*" -or
        $cmd -like "*app.recognition_worker*" -or
        $cmd -like "*mediamtx.exe*"
    ) -and $cmd -like "*$InstallDir*"
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Milliseconds 800

Write-Host "Registering Windows services via nssm (scheduled-task owners have been removed)."
Register-WithNssm -Name "SmartParkSiteService" -Exe $Py64 -Args "-m app.site_service" -WorkDir $InstallDir
Register-WithNssm -Name "SmartParkRecognitionWorker" -Exe $Py64 -Args "-m app.recognition_worker" -WorkDir $InstallDir
if (Test-Path (Join-Path $InstallDir "vendor\mediamtx\mediamtx.exe")) {
    Register-WithNssm -Name "SmartParkMediaService" -Exe $Py64 -Args "-m app.media_service" -WorkDir $InstallDir
}
if (Test-Path $Py32) {
    Register-WithNssm -Name "SmartParkHvxHost" -Exe $Py32 -Args "`"$HostPy`"" -WorkDir (Join-Path $InstallDir "tools\hvx_sdk_host")
} else {
    Write-Host "HVX host service skipped: 32-bit Python is not in this kit."
}
Write-Host "Verify crash restart on site hardware before dropping Install-SmartParkServices.ps1."
