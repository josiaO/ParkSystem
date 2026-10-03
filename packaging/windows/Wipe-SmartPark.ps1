#requires -Version 5.1
<#
.SYNOPSIS
    Factory-reset this PC: stop SmartPark, then delete the database, media,
    logs, FastALPR cache, and (unless -KeepApp) the installed program.

    Stopping the Desktop or logging out is not enough. The live store is
    %ProgramData%\SmartParkEdge (SQLite, snapshots, receipts). FastALPR also
    caches ONNX files under %USERPROFILE%\.cache.

.PARAMETER Force
    Do not ask for confirmation.
.PARAMETER KeepApp
    Delete data and caches only. Leave the installed program files in place.
#>
[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$KeepApp
)

$ErrorActionPreference = "Stop"

function Stop-SmartParkProcesses {
    param([string[]]$Roots)
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $cmd = [string]$_.CommandLine
        $exe = [string]$_.ExecutablePath
        $fromRoot = $false
        foreach ($root in $Roots) {
            if ($root -and $exe -and $exe.StartsWith($root.TrimEnd("\"), [StringComparison]::OrdinalIgnoreCase)) {
                $fromRoot = $true
            }
            if ($root -and $cmd -and ($cmd -like "*$root*")) { $fromRoot = $true }
        }
        $fromRoot -or ($cmd -and (
            $cmd -like "*hvx_host.py*" -or
            $cmd -like "*app.desktop.launch*" -or
            $cmd -like "*app.desktop.main*" -or
            $cmd -like "*app.site_service*" -or
            $cmd -like "*app.media_service*" -or
            $cmd -like "*app.recognition_worker*" -or
            $cmd -like "*mediamtx.exe*"
        ))
    } | ForEach-Object {
        Write-Host ("  stopping {0} pid {1}" -f $_.Name, $_.ProcessId)
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Remove-TreeRetry {
    param([string]$Path)
    if (-not $Path -or -not (Test-Path $Path)) { return }
    $attempt = 0
    while ($attempt -lt 8) {
        try {
            Remove-Item $Path -Recurse -Force -ErrorAction Stop
            Write-Host ("  removed {0}" -f $Path)
            return
        } catch {
            Start-Sleep -Milliseconds (400 * ($attempt + 1))
            $attempt++
        }
    }
    Write-Host ("  WARNING: still locked: {0}" -f $Path)
}

$homeInstall = Join-Path $env:LOCALAPPDATA "Programs\SmartPark Edge"
$progInstall = Join-Path ${env:ProgramFiles} "SmartPark Edge"
$envHome = [Environment]::GetEnvironmentVariable("SMARTPARK_HOME", "User")
$envHomeMachine = [Environment]::GetEnvironmentVariable("SMARTPARK_HOME", "Machine")
$installRoots = @($homeInstall, $progInstall, $envHome, $envHomeMachine) | Where-Object { $_ } | Select-Object -Unique

if (-not $Force) {
    Write-Host "This deletes SmartPark data on this PC, including:"
    Write-Host "  %ProgramData%\SmartParkEdge  (database, media, logs)"
    Write-Host "  FastALPR model cache under %USERPROFILE%\.cache"
    Write-Host "  temp files, env vars, scheduled tasks"
    if (-not $KeepApp) {
        Write-Host "  the installed program under LocalAppData\Programs\SmartPark Edge"
    }
    $answer = Read-Host "Type YES to wipe"
    if ($answer -ne "YES") {
        Write-Host "Cancelled."
        exit 1
    }
}

Write-Host "Stopping SmartPark processes, tasks, and services..."
foreach ($name in @(
    "SmartPark Site Service",
    "SmartPark HVX Host",
    "SmartPark Media Service"
)) {
    Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
}
foreach ($svc in @("SmartParkSiteService", "SmartParkHvxHost", "SmartParkMediaService")) {
    $service = Get-Service -Name $svc -ErrorAction SilentlyContinue
    if ($service) {
        Stop-Service -Name $svc -Force -ErrorAction SilentlyContinue
        if (Get-Command sc.exe -ErrorAction SilentlyContinue) {
            & sc.exe delete $svc | Out-Null
        }
    }
    $nssm = Join-Path $homeInstall "vendor\nssm\nssm.exe"
    if (Test-Path $nssm) {
        & $nssm stop $svc 2>$null | Out-Null
        & $nssm remove $svc confirm 2>$null | Out-Null
    }
}
Stop-SmartParkProcesses -Roots $installRoots
Start-Sleep -Milliseconds 900
Stop-SmartParkProcesses -Roots $installRoots

Write-Host "Deleting database, media, logs, and caches..."
$dataRoots = @(
    (Join-Path $env:ProgramData "SmartParkEdge"),
    (Join-Path $env:LOCALAPPDATA "SmartParkEdge"),
    (Join-Path $env:APPDATA "SmartParkEdge")
)
if ($env:USERPROFILE) {
    $cache = Join-Path $env:USERPROFILE ".cache"
    $dataRoots += @(
        (Join-Path $cache "open-image-models"),
        (Join-Path $cache "fast-plate-ocr")
    )
}
foreach ($p in $dataRoots) { Remove-TreeRetry $p }

Get-ChildItem $env:TEMP -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -like "SmartPark*" -or $_.Name -like "smartpark*" -or $_.Name -like "mediamtx*"
} | ForEach-Object { Remove-TreeRetry $_.FullName }

if ($env:LOCALAPPDATA) {
    $pip = Join-Path $env:LOCALAPPDATA "pip\Cache"
    if (Test-Path $pip) {
        Get-ChildItem $pip -ErrorAction SilentlyContinue | Where-Object {
            $_.Name -like "*smartpark*" -or $_.Name -like "*fast_alpr*" -or $_.Name -like "*fast-alpr*"
        } | ForEach-Object { Remove-TreeRetry $_.FullName }
    }
}

if (-not $KeepApp) {
    Write-Host "Removing installed program files..."
    foreach ($root in $installRoots) { Remove-TreeRetry $root }
    Remove-Item (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\SmartPark") -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item (Join-Path ([Environment]::GetFolderPath("Desktop")) "SmartPark Edge.lnk") -Force -ErrorAction SilentlyContinue
    Remove-Item (Join-Path ([Environment]::GetFolderPath("Startup")) "SmartPark Edge.lnk") -Force -ErrorAction SilentlyContinue
}

Write-Host "Clearing SmartPark environment variables..."
foreach ($scope in @("User", "Machine")) {
    $names = @()
    try {
        $all = [Environment]::GetEnvironmentVariables($scope)
        foreach ($key in @($all.Keys)) {
            if ($key -like "SMARTPARK_*") { $names += [string]$key }
        }
    } catch { }
    foreach ($extra in @("PYTHONPATH", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH")) {
        try {
            $cur = [Environment]::GetEnvironmentVariable($extra, $scope)
        } catch { $cur = $null }
        if ($cur -and ($cur -like "*SmartPark*" -or $cur -like "*smartpark*")) {
            $names += $extra
        }
    }
    foreach ($name in ($names | Select-Object -Unique)) {
        try {
            [Environment]::SetEnvironmentVariable($name, $null, $scope)
            Write-Host ("  cleared {0} ({1})" -f $name, $scope)
        } catch {
            Write-Host ("  skip {0} ({1}): {2}" -f $name, $scope, $_)
        }
    }
    try {
        $userPath = [Environment]::GetEnvironmentVariable("Path", $scope)
        if ($userPath) {
            $kept = @($userPath -split ";" | Where-Object {
                $entry = $_.TrimEnd("\")
                -not (
                    $entry -like "*SmartPark Edge*" -or
                    $entry -like "*SmartParkEdge*"
                )
            })
            [Environment]::SetEnvironmentVariable("Path", ($kept -join ";"), $scope)
        }
    } catch { }
}

Write-Host ""
Write-Host "Wipe complete. Database, media, logs, and caches are gone."
if ($KeepApp) {
    Write-Host "Program files were kept. Restart Site Service or run Start-SmartPark.bat."
} else {
    Write-Host "Reinstall from the USB kit: double-click Install-SmartPark.bat"
}
exit 0
