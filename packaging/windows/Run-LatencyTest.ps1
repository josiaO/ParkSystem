#requires -Version 5.1
<#
.SYNOPSIS
    Click-to-run wrapper for the latency tests A1, A2 and A3 (docs/WINDOWS-TEST-PROTOCOL.md).
.DESCRIPTION
    Finds the installed SmartPark (the copy Install-SmartPark.bat put in place),
    checks that its HVX host is the instrumented version, asks the few questions
    each test needs, and runs tools\windows\Run-LatencyCapture.ps1 from the
    installation. Every run ends with one zip under Desktop\SmartParkLatency.

    A1 and A3 PHYSICALLY OPEN THE BOOM. The capture asks you to type OPEN first.
.PARAMETER Test
    A1 (boom timing), A2 (real cars, no scripted pulses) or A3 (saturated host).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("A1", "A2", "A3")]
    [string]$Test,
    [string]$InstallDir = "",
    [string]$HostUrl = "http://127.0.0.1:8765",
    [double]$A2Seconds = 900
)

$ErrorActionPreference = "Stop"

function Find-InstallDir {
    $candidates = @()
    if ($InstallDir) { $candidates += $InstallDir }
    # When this file was copied into the installation folder itself.
    $candidates += $PSScriptRoot
    foreach ($scope in @("Process", "User", "Machine")) {
        $value = [Environment]::GetEnvironmentVariable("SMARTPARK_HOME", $scope)
        if ($value) { $candidates += $value }
    }
    if ($env:ProgramFiles) { $candidates += (Join-Path $env:ProgramFiles "SmartPark Edge") }
    if ($env:LOCALAPPDATA) { $candidates += (Join-Path $env:LOCALAPPDATA "Programs\SmartPark Edge") }
    # Elevated as another administrator: also look in every user profile.
    Get-ChildItem "$env:SystemDrive\Users" -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        $candidates += (Join-Path $_.FullName "AppData\Local\Programs\SmartPark Edge")
    }
    foreach ($candidate in $candidates) {
        if (-not $candidate) { continue }
        $dir = [Environment]::ExpandEnvironmentVariables($candidate.TrimEnd('\'))
        if ((Test-Path (Join-Path $dir "tools\windows\Run-LatencyCapture.ps1")) -and
            (Test-Path (Join-Path $dir "python64\python.exe"))) {
            return $dir
        }
    }
    return $null
}

function Read-YesNo([string]$question) {
    while ($true) {
        $answer = (Read-Host "$question (Y/N)").Trim().ToUpperInvariant()
        if ($answer -in @("Y", "YES")) { return $true }
        if ($answer -in @("N", "NO")) { return $false }
    }
}

function Confirm-BoomOpen([object[]]$cameras, [int]$handle, [string]$what) {
    $ip = ($cameras | Where-Object { [int]$_.handle -eq $handle } | Select-Object -First 1).ip
    Write-Host ""
    $answer = Read-Host "This will OPEN THE BOOM on camera handle $handle ($ip) $what. Type OPEN to continue"
    if ($answer.Trim() -cne "OPEN") {
        Write-Host "Cancelled. The boom was not opened."
        exit 0
    }
}

function Select-Camera([object[]]$cameras) {
    if ($cameras.Count -eq 1) {
        Write-Host "Using the only connected camera: handle $($cameras[0].handle) ($($cameras[0].ip))."
        return [int]$cameras[0].handle
    }
    Write-Host ""
    Write-Host "Connected cameras:"
    foreach ($camera in $cameras) { Write-Host "  handle $($camera.handle)   ip $($camera.ip)" }
    $valid = @($cameras | ForEach-Object { [string]$_.handle })
    while ($true) {
        $answer = (Read-Host "Type the handle of the camera wired to the TEST BOOM").Trim()
        if ($valid -contains $answer) { return [int]$answer }
        Write-Host "Not one of: $($valid -join ', ')"
    }
}

$Root = Find-InstallDir
if (-not $Root) {
    throw "No SmartPark installation with the latency tools was found. Run Install-SmartPark.bat from this kit first, then run this again."
}
$Capture = Join-Path $Root "tools\windows\Run-LatencyCapture.ps1"
$env:SMARTPARK_PYTHON = Join-Path $Root "python64\python.exe"
Write-Host "SmartPark latency test $Test"
Write-Host "Installation: $Root"

# The host must be running the instrumented code installed from this kit.
try {
    Invoke-RestMethod -Uri "$HostUrl/metrics" -TimeoutSec 5 | Out-Null
} catch {
    throw "The HVX host at $HostUrl does not answer /metrics. Either SmartPark is not running, or it is still running the old version. Restart the PC (or the SmartPark services), open Zirp, connect the cameras, then run this again."
}
$info = Invoke-RestMethod -Uri "$HostUrl/info" -TimeoutSec 5
$cameras = @($info.connections | Where-Object { $null -ne $_.handle })
if ($cameras.Count -eq 0) {
    throw "No camera is connected to the HVX host. Open Zirp, connect the cameras (Live Gates -> Connect all), then run this again."
}

$capArgs = @{ HostUrl = $HostUrl }
$notes = $null
$desktop = [Environment]::GetFolderPath("Desktop")
if (-not $desktop) { $desktop = Join-Path $HOME "Desktop" }
$base = Join-Path $desktop "SmartParkLatency"
New-Item -ItemType Directory -Force -Path $base | Out-Null

switch ($Test) {
    "A1" {
        Write-Host ""
        Write-Host "A1 opens the boom 10 times (5 with no extra viewers, 5 with 4 viewers per camera), 10 s apart."
        Write-Host "Run it twice: once with the Zirp desktop app open on live video, once with it closed."
        Write-Host "Keep the lane clear. For B1, start the phone slow-motion video before you type OPEN."
        $appOpen = Read-YesNo "Is the Zirp desktop app open right now, showing live video"
        $capArgs.Handle = Select-Camera $cameras
        $capArgs.Beep = $true
        $capArgs.Yes = $true
        $capArgs.Label = if ($appOpen) { "A1-app-open" } else { "A1-app-closed" }
        $inputAnswer = (Read-Host "B2 only: camera GPIO input index wired to the boom state (press Enter to skip)").Trim()
        if ($inputAnswer -match '^\d+$') {
            $capArgs.PollInput = [int]$inputAnswer
            $capArgs.Label += "-input$inputAnswer"
        }
        Confirm-BoomOpen $cameras $capArgs.Handle "10 times (5 per phase, 10 s apart)"
    }
    "A2" {
        Write-Host ""
        Write-Host "A2 records 15 minutes of real cars. The script does NOT open the boom."
        Write-Host "Drive at least 10 passes: two cars back to back (twice), one stop of 20 s under the camera,"
        Write-Host "and one at normal customer speed. Write each pass in the Notepad window that opens now."
        $notes = Join-Path $base ("A2-passes-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".txt")
        @(
            "A2 passes. One line per pass. Save this file (Ctrl+S) before the test ends.",
            "time (PC clock) | plate | lane | what looked wrong (wrong plate, old picture, frozen live view and for how long, slow boom)",
            ""
        ) | Set-Content -Path $notes -Encoding UTF8
        try { Start-Process notepad.exe -ArgumentList "`"$notes`"" } catch { Write-Host "Open this file and write your passes in it: $notes" }
        $capArgs.NoPulse = $true
        $capArgs.PassiveSeconds = $A2Seconds
        $capArgs.Label = "A2-real-cars"
    }
    "A3" {
        Write-Host ""
        Write-Host "A3 holds every HVX host worker busy, then opens the boom 3 times."
        Write-Host "During this run other SmartPark requests can fail for about a minute and THE BOOM MAY OPEN LATE."
        Write-Host "Keep the lane clear and watch the boom: note how many seconds after each 'pulse' line it opened."
        if (-not (Read-YesNo "Continue")) { Write-Host "Cancelled."; exit 0 }
        $capArgs.Handle = Select-Camera $cameras
        $capArgs.Saturate = $true
        $capArgs.Pulses = 3
        $capArgs.Yes = $true
        $capArgs.Label = "A3-saturated"
        Confirm-BoomOpen $cameras $capArgs.Handle "3 times, possibly late"
    }
}

$capArgs.OutDir = $base
$before = @(Get-ChildItem $base -Filter "capture-*.zip" -ErrorAction SilentlyContinue | ForEach-Object FullName)
& $Capture @capArgs
$exit = $LASTEXITCODE
$zip = Get-ChildItem $base -Filter "capture-*.zip" -ErrorAction SilentlyContinue |
    Where-Object { $before -notcontains $_.FullName } | Sort-Object LastWriteTime -Descending | Select-Object -First 1

if ($notes -and $zip) {
    Write-Host ""
    Read-Host "Save your notes in Notepad (Ctrl+S), then press Enter here to add them to the zip"
    try {
        $ProgressPreference = "SilentlyContinue"
        Copy-Item $notes ([IO.Path]::ChangeExtension($zip.FullName, $null).TrimEnd('.')) -ErrorAction SilentlyContinue
        Compress-Archive -Path $notes -DestinationPath $zip.FullName -Update
        Write-Host "Notes added to the zip."
    } catch {
        Write-Warning "Could not add the notes to the zip ($($_.Exception.Message)). Send this file as well: $notes"
    }
}
Write-Host ""
if ($exit -ne 0) {
    Write-Warning "The capture stopped early (code $exit). If you typed something other than OPEN, run it again. Otherwise send the zip below anyway; it holds the error."
}
if ($zip) {
    Write-Host "Send this file back: $($zip.FullName)"
    if ($Test -eq "A1") { Write-Host "(The file name says whether the desktop app was open.)" }
    if ($Test -eq "A3") { Write-Host "Also say whether the boom opened late (how many seconds after 'pulse') or not at all." }
    try { Start-Process explorer.exe -ArgumentList "/select,`"$($zip.FullName)`"" } catch { }
} else {
    Write-Warning "No zip was produced. Send the console text above (or a screenshot) back instead."
}
exit $exit
