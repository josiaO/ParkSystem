#requires -Version 5.1
<#
.SYNOPSIS
    Power-cut recovery test: restart the PC, do not sign in, check that parking came back.

.DESCRIPTION
    -Arm      registers a one-off SYSTEM task that runs at the next boot
              (before anyone signs in) and executes tools\boot_health_check.py,
              then restarts the PC after you confirm.
    -Report   after the reboot (wait at least TimeoutMinutes, then sign in):
              prints the PASS/FAIL report and removes the one-off task.

    The check passes when every installed SmartPark service is RUNNING and the
    Site Service answers /health/live and /health/ready (and the HVX host /info
    if it runs as a service) within -TimeoutMinutes of boot.

.EXAMPLE
    .\tools\Test-RebootRecovery.ps1 -Arm -TimeoutMinutes 5
    # do not sign in; wait 10 minutes; sign in, then:
    .\tools\Test-RebootRecovery.ps1 -Report
#>
[CmdletBinding(DefaultParameterSetName = "Report")]
param(
    [Parameter(ParameterSetName = "Arm", Mandatory = $true)][switch]$Arm,
    [Parameter(ParameterSetName = "Arm")][int]$TimeoutMinutes = 5,
    [Parameter(ParameterSetName = "Arm")][switch]$NoRestart,
    [Parameter(ParameterSetName = "Report")][switch]$Report,
    [string]$InstallDir = ""
)

$ErrorActionPreference = "Stop"
if (-not $InstallDir) {
    $InstallDir = [Environment]::GetEnvironmentVariable("SMARTPARK_HOME", "User")
    if (-not $InstallDir) { $InstallDir = Join-Path $env:LOCALAPPDATA "Programs\SmartPark Edge" }
}
$TaskName = "SmartPark Reboot Recovery Check"
$LogDir = Join-Path $env:ProgramData "SmartParkEdge\logs"
$ReportPath = Join-Path $LogDir "reboot-recovery-report.json"
$ArmedPath = Join-Path $LogDir "reboot-recovery-armed.txt"
$Py64 = Join-Path $InstallDir "python64\python.exe"
$Checker = Join-Path $InstallDir "tools\boot_health_check.py"

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this from an elevated PowerShell window."
}

if ($Arm) {
    foreach ($path in @($Py64, $Checker)) {
        if (-not (Test-Path $path)) { throw "Missing $path" }
    }
    $services = @(Get-Service -Name "SmartPark*" -ErrorAction SilentlyContinue)
    if ($services.Count -eq 0) {
        throw "No SmartPark Windows services are installed. Install Zirp with Zirp-Setup.exe (Site Server or Edge Node role) first."
    }
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    Remove-Item -LiteralPath $ReportPath -ErrorAction SilentlyContinue
    $arguments = "`"$Checker`" --timeout-minutes $TimeoutMinutes --report `"$ReportPath`""
    $action = New-ScheduledTaskAction -Execute $Py64 -Argument $arguments -WorkingDirectory $InstallDir
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $taskPrincipal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes ($TimeoutMinutes + 5)) -AllowStartIfOnBatteries
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $taskPrincipal -Settings $settings -Force | Out-Null
    "Armed $(Get-Date -Format s) on $env:COMPUTERNAME; timeout $TimeoutMinutes min" | Set-Content -Path $ArmedPath -Encoding UTF8
    Write-Host "Armed. Services under test: $(($services | ForEach-Object Name) -join ', ')"
    Write-Host "After the restart do NOT sign in. Wait at least $($TimeoutMinutes + 5) minutes, then sign in and run:"
    Write-Host "    .\tools\Test-RebootRecovery.ps1 -Report"
    if ($NoRestart) { return }
    $answer = Read-Host "Restart this PC now? Type YES to restart"
    if ($answer -ne "YES") { Write-Host "Not restarted. Restart it yourself (or cut the power) to run the test."; return }
    Restart-Computer -Force
    return
}

if (-not (Test-Path $ReportPath)) {
    Write-Host "No report yet at $ReportPath."
    Write-Host "Either the PC has not been restarted since -Arm, the check is still running, or the task failed:"
    Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue | Format-List LastRunTime, LastTaskResult
    exit 2
}
$result = Get-Content -LiteralPath $ReportPath -Raw -Encoding UTF8 | ConvertFrom-Json
Write-Host ""
Write-Host ("Verdict: {0}" -f $result.verdict)
if ($result.seconds_to_green) { Write-Host ("Green {0} s after the check started at boot." -f $result.seconds_to_green) }
$result.checks.PSObject.Properties | ForEach-Object { Write-Host ("  {0,-18} {1}" -f $_.Name, $(if ($_.Value) { "PASS" } else { "FAIL" })) }
$result.services.PSObject.Properties | ForEach-Object { Write-Host ("  service {0,-28} {1}" -f $_.Name, $(if ($_.Value) { $_.Value } else { "not installed" })) }
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "Report: $ReportPath (the one-off boot task has been removed)"
if ($result.verdict -ne "PASS") { exit 1 }
