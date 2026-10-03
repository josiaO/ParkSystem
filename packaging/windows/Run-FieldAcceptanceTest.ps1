#requires -Version 5.1
<#
.SYNOPSIS
    Soak the live Site Service while cars pass. Writes PASS/FAIL under ProgramData\SmartParkEdge\logs.
.PARAMETER Minutes
    How long to sample (default 8).
.PARAMETER ExpectedCars
    Optional. Fail if fewer published recognition events than this count.
#>
[CmdletBinding()]
param(
    [int]$Minutes = 8,
    [int]$ExpectedCars = 0,
    [string]$Url = "http://127.0.0.1:8760",
    [string]$Username = "admin",
    [string]$Password = ""
)

$ErrorActionPreference = "Stop"
$InstallDir = [Environment]::GetEnvironmentVariable("SMARTPARK_HOME", "User")
if (-not $InstallDir) {
    $InstallDir = Join-Path $env:LOCALAPPDATA "Programs\SmartPark Edge"
}

$Py = Join-Path $InstallDir "python64\python.exe"
$Script = Join-Path $InstallDir "tools\field_acceptance_test.py"
if (-not (Test-Path $Script)) {
    $kit = $PSScriptRoot
    $fromKit = Join-Path $kit "payload\tools\field_acceptance_test.py"
    if (Test-Path $fromKit) {
        $Script = $fromKit
        $kitPy = Join-Path $kit "payload\python64\python.exe"
        if (Test-Path $kitPy) { $Py = $kitPy }
    }
}
if (-not (Test-Path $Script)) { throw "field_acceptance_test.py not found. Reinstall SmartPark from the USB kit." }
if (-not (Test-Path $Py)) {
    $Py = (Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1).Source
    if (-not $Py) { throw "Python not found. Install SmartPark first." }
}

Write-Host "SmartPark field acceptance - keep cars moving through the lanes."
Write-Host "Script: $Script"
$argsList = @($Script, "--url", $Url, "--username", $Username, "--minutes", "$Minutes")
if ($ExpectedCars -gt 0) { $argsList += @("--expected-cars", "$ExpectedCars") }
if ($Password) { $argsList += @("--password", $Password) }
& $Py @argsList
exit $LASTEXITCODE
