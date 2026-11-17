#requires -Version 5.1
<#
.SYNOPSIS
    Run the 32-bit HVX SDK host as a Windows service (boot-time, no logon).
.DESCRIPTION
    Use after Test-HvxHostAsService.ps1 shows the SDK, camera connection and
    live video working in Session 0. Registers only "SmartParkHvxHost" with
    the same NSSM settings as the other SmartPark services, removes the
    "SmartPark HVX Host" logon task so two hosts never compete for the
    cameras, and starts the service. Undo with -Remove (restores nothing
    else; re-run Install-SmartParkServices.ps1 to bring the logon task back).
.EXAMPLE
    .\Register-HvxHostService.ps1
    .\Register-HvxHostService.ps1 -Remove
#>
[CmdletBinding()]
param(
    [string]$InstallDir = "",
    [switch]$Remove
)
$ErrorActionPreference = "Stop"
if (-not $InstallDir) { $InstallDir = $PSScriptRoot }
$Name = "SmartParkHvxHost"
$Nssm = Join-Path $InstallDir "vendor\nssm\nssm.exe"
$Py32 = Join-Path $InstallDir "python32\python.exe"
$HostDir = Join-Path $InstallDir "tools\hvx_sdk_host"
$DataDir = Join-Path $env:ProgramData "SmartParkEdge"
$LogDir = Join-Path $DataDir "logs\services"

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this from an elevated PowerShell window."
}
foreach ($path in @($Nssm, $Py32, (Join-Path $HostDir "hvx_host.py"))) {
    if (-not (Test-Path $path)) { throw "Missing $path" }
}

function Invoke-Nssm {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $output = & $Nssm @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw ("nssm {0} failed ({1}): {2}" -f ($Arguments -join " "), $LASTEXITCODE, ($output -join " ")) }
}

if (Get-Service -Name $Name -ErrorAction SilentlyContinue) {
    & $Nssm stop $Name 2>$null | Out-Null
    & $Nssm remove $Name confirm 2>$null | Out-Null
    Start-Sleep -Seconds 2
}
if ($Remove) {
    Write-Host "$Name removed."
    return
}

# One owner for the cameras: stop the logon task and any interactive host.
Stop-ScheduledTask -TaskName "SmartPark HVX Host" -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName "SmartPark HVX Host" -Confirm:$false -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { ([string]$_.CommandLine) -like "*hvx_host.py*" -or ([string]$_.CommandLine) -like "*run-hvx-host*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
# Script path relative to AppDirectory: PowerShell 5.1 drops embedded quotes
# on native calls and the install path contains a space.
Invoke-Nssm install $Name $Py32 "hvx_host.py"
Invoke-Nssm set $Name DisplayName "SmartPark HVX SDK Host (32-bit)"
Invoke-Nssm set $Name Description "QY/HVX camera SDK host: cameras, plate events and barrier GPIO. Starts at boot."
Invoke-Nssm set $Name AppDirectory $HostDir
Invoke-Nssm set $Name ObjectName LocalSystem
Invoke-Nssm set $Name Start SERVICE_AUTO_START
Invoke-Nssm set $Name AppExit Default Restart
Invoke-Nssm set $Name AppRestartDelay 2000
Invoke-Nssm set $Name AppThrottle 15000
Invoke-Nssm set $Name AppStopMethodConsole 5000
Invoke-Nssm set $Name AppStopMethodWindow 3000
Invoke-Nssm set $Name AppStopMethodThreads 3000
$log = Join-Path $LogDir "$Name.log"
Invoke-Nssm set $Name AppStdout $log
Invoke-Nssm set $Name AppStderr $log
Invoke-Nssm set $Name AppStdoutCreationDisposition 4
Invoke-Nssm set $Name AppStderrCreationDisposition 4
Invoke-Nssm set $Name AppRotateFiles 1
# Rotate at start only: NSSM 2.24 online rotation left services stuck in
# StopPending after the app had already exited (the Python services rotate
# their own logs; stdout here holds startup lines and tracebacks).
Invoke-Nssm set $Name AppRotateOnline 0
Invoke-Nssm set $Name AppRotateBytes 10485760
Invoke-Nssm set $Name AppEnvironmentExtra `
    "SMARTPARK_HOME=$InstallDir" "SMARTPARK_LOG_DIR=$DataDir\logs" "PYTHONPATH=$InstallDir" `
    "PYTHONUNBUFFERED=1" "SMARTPARK_HVX_VENDOR_DIR=$InstallDir\vendor"
& sc.exe failure $Name reset= 86400 actions= restart/5000/restart/15000/restart/60000 | Out-Null
& sc.exe failureflag $Name 1 | Out-Null
# Same rights as the other SmartPark services: interactive users may query,
# start and stop it (desktop repair button); nothing else changes.
& sc.exe sdset $Name "D:(A;;CCLCSWRPWPDTLOCRRC;;;SY)(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)(A;;CCLCSWRPWPLOCRRC;;;IU)(A;;CCLCSWLOCRRC;;;SU)" | Out-Null
Invoke-Nssm start $Name

$deadline = (Get-Date).AddSeconds(45)
$info = $null
while ((Get-Date) -lt $deadline -and -not $info) {
    try { $info = Invoke-RestMethod -Uri "http://127.0.0.1:8765/info" -TimeoutSec 3 } catch { Start-Sleep -Seconds 1 }
}
if ($info -and $info.available) {
    Write-Host "$Name is running as a service; SDK loaded. Cameras reconnect automatically (Site Service restores sessions)."
} else {
    Write-Warning "$Name started but /info did not answer within 45 s. Check $log"
}
