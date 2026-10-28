#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$Dataset = "",
    [ValidateSet("inspect", "video", "multi-camera", "images", "all")]
    [string]$Mode = "all",
    [int]$DurationSeconds = 12,
    [switch]$IncludeImages
)

$ErrorActionPreference = "Stop"
$InstallDir = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Dataset)) {
    $Dataset = Join-Path (Split-Path -Parent $InstallDir) "TestingData"
}
$Dataset = [Environment]::ExpandEnvironmentVariables($Dataset)
if (-not (Test-Path -LiteralPath $Dataset -PathType Container)) {
    throw "TestingData directory was not found: $Dataset"
}
$Py64 = Join-Path $InstallDir "python64\python.exe"
if (-not (Test-Path -LiteralPath $Py64)) {
    throw "Bundled Python was not found: $Py64. Run this from the installed Zirp folder."
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$out = Join-Path $env:TEMP "Zirp-RecordedMedia-$stamp"
New-Item -ItemType Directory -Path $out -Force | Out-Null
$env:SMARTPARK_HOME = $InstallDir
$env:PYTHONPATH = $InstallDir
$env:PATH = "$InstallDir\python64;$InstallDir\python64\Scripts;$InstallDir\vendor;$env:PATH"

function Invoke-Lab([string[]]$Arguments) {
    Write-Host (">> " + ($Arguments -join " "))
    & $Py64 -m tools.camera_lab_replay @Arguments
    if ($LASTEXITCODE -gt 2) {
        throw "Recorded-media test command failed to start or crashed (exit $LASTEXITCODE)."
    }
}

$video = Join-Path $Dataset "Video Project.mp4"
if ($Mode -in @("inspect", "all")) {
    Invoke-Lab @("inspect", $Dataset, "--output", (Join-Path $out "inventory"))
}
if ($Mode -in @("video", "all")) {
    if (-not (Test-Path -LiteralPath $video)) { throw "Recorded video was not found: $video" }
    Invoke-Lab @("benchmark", "Video Project.mp4", "--dataset", $Dataset, "--duration", $DurationSeconds, "--cameras", "1", "--output", (Join-Path $out "video"))
}
if ($Mode -in @("multi-camera", "all")) {
    if (-not (Test-Path -LiteralPath $video)) { throw "Recorded video was not found: $video" }
    Invoke-Lab @("multi-camera", "Video Project.mp4", "--dataset", $Dataset, "--duration", $DurationSeconds, "--output", (Join-Path $out "multi-camera"))
}
if ($Mode -eq "images" -or $IncludeImages) {
    Invoke-Lab @("test-image", ".", "--dataset", $Dataset, "--output", (Join-Path $out "images"))
}

$reportRoot = Join-Path $out "report"
Invoke-Lab @("report", $out, "--output", (Join-Path $reportRoot "report.json"))
$archive = "$out.zip"
Compress-Archive -Path (Join-Path $out "*") -DestinationPath $archive -Force
Write-Host ""
Write-Host "Recorded-media diagnostics saved to: $archive"
Write-Host "Send this ZIP together with Run-ServerDiagnostics output when reporting a Windows camera issue."
