#requires -Version 5.1
<#
.SYNOPSIS
    Prove (or disprove) that the 32-bit HVX SDK host works as a Windows service.

.DESCRIPTION
    Windows services run in Session 0, which has no interactive desktop. The
    HVX host uses a hidden, message-pumped window for the vendor NetSDK/PlaySdk
    callbacks. This script answers one question on the real site PC: does the
    vendor SDK still connect, deliver live video and native plate reads there?

    It never commands a barrier (no GPIO). Steps:
      1. stop the HVX logon task and any running hvx_host.py;
      2. run the host as a temporary service "SmartParkHvxHostTest" (LocalSystem);
      3. check /info (SDK loaded), connect to one camera, count live frames for
         -Seconds, and optionally wait for a native plate read (drive a car past);
      4. remove the test service, restart the logon task, and write a PASS/FAIL
         report to %ProgramData%\SmartParkEdge\logs\hvx-service-test-*.txt.

    If it passes, make the HVX host a real service:
        .\Install-SmartParkWinService.ps1 -HvxHostAsService
    If it fails, keep the logon task and use the auto-logon arrangement in
    docs\WINDOWS-SERVICES.md.

.EXAMPLE
    .\Test-HvxHostAsService.ps1 -CameraIp 192.168.1.144 -WaitForPlate
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$CameraIp,
    [string]$Username = "admin",
    [int]$SdkPort = 30000,
    [int]$Seconds = 30,
    [switch]$WaitForPlate,
    [int]$PlateWaitSeconds = 120,
    [string]$InstallDir = ""
)

$ErrorActionPreference = "Stop"
if (-not $InstallDir) {
    $InstallDir = [Environment]::GetEnvironmentVariable("SMARTPARK_HOME", "User")
    if (-not $InstallDir) { $InstallDir = Join-Path $env:LOCALAPPDATA "Programs\SmartPark Edge" }
}
$Nssm = Join-Path $InstallDir "vendor\nssm\nssm.exe"
$Py32 = Join-Path $InstallDir "python32\python.exe"
$HostDir = Join-Path $InstallDir "tools\hvx_sdk_host"
$HostPy = Join-Path $HostDir "hvx_host.py"
$TestService = "SmartParkHvxHostTest"
$Base = "http://127.0.0.1:8765"
$LogDir = Join-Path $env:ProgramData "SmartParkEdge\logs"
$Report = Join-Path $LogDir ("hvx-service-test-{0}.txt" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
$results = New-Object System.Collections.Generic.List[string]
$failed = $false

function Note([string]$line) { $script:results.Add($line); Write-Host $line }
function Check([string]$name, [bool]$ok, [string]$detail) {
    if (-not $ok) { $script:failed = $true }
    Note ("{0}  {1}  {2}" -f ($(if ($ok) { "PASS" } else { "FAIL" })), $name, $detail)
}

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this from an elevated PowerShell window."
}
foreach ($path in @($Nssm, $Py32, $HostPy)) {
    if (-not (Test-Path $path)) { throw "Missing $path. Install a kit that includes NSSM and 32-bit Python." }
}
if (Get-Service -Name "SmartParkHvxHost" -ErrorAction SilentlyContinue) {
    throw "SmartParkHvxHost is already a service. Nothing to test."
}
$secure = Read-Host -AsSecureString "Camera password for $Username@$CameraIp"
$password = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

Note "HVX host Session 0 test  $(Get-Date -Format s)  PC $env:COMPUTERNAME  camera $CameraIp"
Note "Stopping the HVX logon task and any running host..."
Stop-ScheduledTask -TaskName "SmartPark HVX Host" -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { ([string]$_.CommandLine) -like "*hvx_host.py*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

$handle = $null
try {
    # Relative to AppDirectory: PowerShell 5.1 drops embedded quotes on native
    # calls, and the install path contains a space ("SmartPark Edge").
    & $Nssm install $TestService $Py32 "hvx_host.py" | Out-Null
    & $Nssm set $TestService AppDirectory $HostDir | Out-Null
    & $Nssm set $TestService ObjectName LocalSystem | Out-Null
    & $Nssm set $TestService AppEnvironmentExtra "SMARTPARK_HOME=$InstallDir" "SMARTPARK_HVX_VENDOR_DIR=$InstallDir\vendor" "PYTHONUNBUFFERED=1" | Out-Null
    & $Nssm set $TestService AppStdout (Join-Path $LogDir "hvx-service-test.log") | Out-Null
    & $Nssm set $TestService AppStderr (Join-Path $LogDir "hvx-service-test.log") | Out-Null
    & $Nssm start $TestService | Out-Null

    $info = $null
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline -and -not $info) {
        try { $info = Invoke-RestMethod -Uri "$Base/info" -TimeoutSec 3 } catch { Start-Sleep -Seconds 1 }
    }
    Check "host-starts-as-service" ([bool]$info) "GET /info answered from Session 0"
    if (-not $info) { throw "host did not answer" }
    Check "sdk-loaded" ([bool]$info.available) ("startup_error=" + [string]$info.startup_error)

    $body = @{ ip = $CameraIp; port = $SdkPort; timeout = 5; username = $Username; password = $password } | ConvertTo-Json
    $connect = Invoke-RestMethod -Method Post -Uri "$Base/connect" -Body $body -ContentType "application/json" -TimeoutSec 30
    $handle = $connect.handle
    if ($null -eq $handle -and $connect.result) { $handle = $connect.result.handle }
    Check "camera-connects" ($null -ne $handle) ("handle=" + [string]$handle)

    if ($null -ne $handle) {
        $frames = 0; $seq = 0
        $end = (Get-Date).AddSeconds($Seconds)
        while ((Get-Date) -lt $end) {
            try {
                $r = Invoke-WebRequest -Uri "$Base/live-jpeg/$handle`?after=$seq&wait_ms=1500" -UseBasicParsing -TimeoutSec 4
                if ($r.StatusCode -eq 200 -and $r.Content.Length -gt 1000) {
                    $frames++
                    $seq = [int]($r.Headers["X-Frame-Seq"] | Select-Object -First 1)
                }
            } catch { Start-Sleep -Milliseconds 300 }
        }
        $fps = [Math]::Round($frames / [Math]::Max(1, $Seconds), 1)
        Check "live-video" ($frames -ge [Math]::Max(5, $Seconds)) ("$frames frames in $Seconds s ($fps fps); expect >= 1 fps")

        if ($WaitForPlate) {
            Note "Drive a car past the camera now (waiting up to $PlateWaitSeconds s)..."
            $plate = ""
            $end = (Get-Date).AddSeconds($PlateWaitSeconds)
            while ((Get-Date) -lt $end -and -not $plate) {
                try {
                    $events = Invoke-RestMethod -Uri "$Base/events/$handle" -TimeoutSec 4
                    foreach ($event in @($events.events)) {
                        if ($event -and $event.plate) { $plate = [string]$event.plate; break }
                    }
                } catch {}
                if (-not $plate) { Start-Sleep -Seconds 1 }
            }
            Check "native-plate-read" ([bool]$plate) ("plate=" + $plate)
        }
        try { Invoke-RestMethod -Method Post -Uri "$Base/disconnect/$handle" -Body "{}" -ContentType "application/json" -TimeoutSec 10 | Out-Null } catch {}
    }
} catch {
    $failed = $true
    Note ("ERROR  " + $_.Exception.Message)
} finally {
    & $Nssm stop $TestService 2>$null | Out-Null
    & $Nssm remove $TestService confirm 2>$null | Out-Null
    Start-ScheduledTask -TaskName "SmartPark HVX Host" -ErrorAction SilentlyContinue
    $password = $null
}

$verdict = if ($failed) { "FAIL: keep the HVX host as a logon task (see docs\WINDOWS-SERVICES.md, auto-logon)." } else { "PASS: run .\Install-SmartParkWinService.ps1 -HvxHostAsService" }
Note ""
Note $verdict
$results | Set-Content -Path $Report -Encoding UTF8
Write-Host "Report: $Report"
if ($failed) { exit 1 }
