#requires -Version 5.1
<#
.SYNOPSIS
    Optional Windows Service (SCM) registration for Site Service and HVX host.

    Default installs still use logon scheduled tasks (Install-SmartParkServices.ps1).
    Keep that path until SCM restart is verified on the real site PC.
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

Write-Host "Registering optional Windows services via nssm (scheduled tasks are not removed)."
Register-WithNssm -Name "SmartParkSiteService" -Exe $Py64 -Args "-m app.site_service" -WorkDir $InstallDir
if (Test-Path $Py32) {
    Register-WithNssm -Name "SmartParkHvxHost" -Exe $Py32 -Args "`"$HostPy`"" -WorkDir (Join-Path $InstallDir "tools\hvx_sdk_host")
} else {
    Write-Host "HVX host service skipped: 32-bit Python is not in this kit."
}
Write-Host "Verify crash restart on site hardware before dropping Install-SmartParkServices.ps1."
