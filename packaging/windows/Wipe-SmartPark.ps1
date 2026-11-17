#requires -Version 5.1
<#
.SYNOPSIS
    Factory-reset this PC: stop SmartPark, then delete the database, media,
    logs, FastALPR cache, and (unless -KeepApp) the installed program.

    Stopping the Desktop or logging out is not enough. The live store is
    %ProgramData%\SmartParkEdge (SQLite, snapshots, receipts). FastALPR also
    caches ONNX files under %USERPROFILE%\.cache.

    With PostgreSQL the visit records live outside this folder. Deleting
    only the files left records pointing at missing photos, so the wipe asks
    what to do with the site data (-SiteData):
      Reset  Site Server only: empty the PostgreSQL database first, then
             delete everything. Type the database name to confirm
             (-ConfirmDatabaseName with -Force). Never on an Edge Node: there
             the database is the whole site's data.
      Keep   keep the site data (database, photos, connection settings);
             remove the program, logs and caches only.
    Edge Nodes with shared photo storage wipe their local files only; the
    central database and shared photos are never touched.

.PARAMETER Force
    Do not ask for confirmation.
.PARAMETER KeepApp
    Delete data and caches only. Leave the installed program files in place.
.PARAMETER SiteData
    Ask (default), Reset or Keep: what to do when PostgreSQL holds this PC's
    visit records. -Force requires Reset or Keep.
.PARAMETER ConfirmDatabaseName
    With -SiteData Reset -Force: the PostgreSQL database name, exactly.
.PARAMETER DryRun
    Show what would be stopped, reset and deleted; change nothing.
#>
[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$KeepApp,
    [ValidateSet("Ask", "Reset", "Keep")][string]$SiteData = "Ask",
    [string]$ConfirmDatabaseName = "",
    [switch]$DryRun
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
# The kit ships this script in its install folder: that is the most reliable
# root (a different Windows user may run the wipe than the one who installed).
$scriptInstall = if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot "python64\python.exe"))) { $PSScriptRoot } else { $null }
$installRoots = @($scriptInstall, $homeInstall, $progInstall, $envHome, $envHomeMachine) | Where-Object { $_ } | Select-Object -Unique

# ---------------------------------------------------------------------------
# What does this PC hold? Ask the app itself; fall back to deployment.json.
# ---------------------------------------------------------------------------
$dataDir = Join-Path $env:ProgramData "SmartParkEdge"
$python = $installRoots | ForEach-Object { Join-Path $_ "python64\python.exe" } | Where-Object { Test-Path $_ } | Select-Object -First 1
$appRoot = if ($python) { Split-Path (Split-Path $python -Parent) -Parent } else { "" }

function Invoke-ZirpCli {
    param([string[]]$Arguments)
    if (-not $python) { return $null }
    $previous = $env:SMARTPARK_HOME
    $env:SMARTPARK_HOME = $appRoot
    Push-Location $appRoot
    try {
        $out = & $python -m app.cli @Arguments 2>$null
        $code = $LASTEXITCODE
    } finally {
        Pop-Location
        $env:SMARTPARK_HOME = $previous
    }
    $json = $null
    try { $json = ($out | Select-Object -Last 1) | ConvertFrom-Json } catch { }
    return [pscustomobject]@{ Code = $code; Json = $json }
}

$site = $null
$status = Invoke-ZirpCli @("db", "status")
if ($status -and $status.Code -eq 0 -and $status.Json) { $site = $status.Json }
if (-not $site) {
    $deploymentFile = Join-Path $dataDir "deployment.json"
    if (Test-Path $deploymentFile) {
        try {
            $d = Get-Content $deploymentFile -Raw | ConvertFrom-Json
            $engine = [string]$d.database.engine
            $isPg = $engine -eq "POSTGRESQL"
            $site = [pscustomobject]@{
                role = [string]$d.role; engine = $engine; postgres = $isPg
                database = [string]$d.database.postgres_database; host = [string]$d.database.postgres_host
                shared_media = $false; local_photos_referenced_externally = $isPg
                may_reset_database = ($isPg -and [string]$d.role -eq "SITE_SERVER")
            }
        } catch { }
    }
}

$keepSiteData = $false
$resetDatabase = $false
if ($site -and $site.postgres) {
    Write-Host ("This PC is a {0} using PostgreSQL '{1}' on {2}." -f $site.role, $site.database, $site.host)
    if (-not $site.local_photos_referenced_externally) {
        Write-Host "  Photos are on shared storage: only this PC's local files are wiped; the site database is not touched."
    } else {
        if ($SiteData -eq "Ask") {
            if ($Force) {
                Write-Host "PostgreSQL holds this PC's visit records. Re-run with -SiteData Reset or -SiteData Keep."
                exit 2
            }
            Write-Host "  The visit records are in PostgreSQL and their photos are in this PC's data folder."
            Write-Host "  [R] Reset: empty the site database too (Site Server only), then delete everything"
            Write-Host "  [K] Keep:  keep the site data (database, photos, connection settings); remove program, logs, caches"
            $choice = Read-Host "Choose R or K (anything else cancels)"
            if ($choice -match "^[Rr]$") { $SiteData = "Reset" } elseif ($choice -match "^[Kk]$") { $SiteData = "Keep" } else {
                Write-Host "Cancelled."
                exit 1
            }
        }
        if ($SiteData -eq "Keep") {
            $keepSiteData = $true
        } else {
            if (-not $site.may_reset_database) {
                Write-Host ("This PC is a {0}: the PostgreSQL database is the whole site's data. Reset it from the Site Server, or use -SiteData Keep." -f $site.role)
                exit 2
            }
            if (-not $python) {
                Write-Host "The SmartPark program is missing, so the database cannot be reset from here. Use -SiteData Keep, or reinstall first."
                exit 2
            }
            if (-not $ConfirmDatabaseName) {
                if ($Force) { Write-Host ("Add -ConfirmDatabaseName {0} to reset the database unattended." -f $site.database); exit 2 }
                $ConfirmDatabaseName = Read-Host ("Type the database name ({0}) to delete ALL parking data in it" -f $site.database)
            }
            if ($ConfirmDatabaseName -cne $site.database) {
                Write-Host "Database name does not match. Cancelled."
                exit 1
            }
            $resetDatabase = $true
        }
    }
}

if ($DryRun) {
    Write-Host ""
    Write-Host "DRY RUN: nothing is stopped, reset or deleted."
    if ($resetDatabase) { Write-Host ("  would empty PostgreSQL database '{0}' on {1}" -f $site.database, $site.host) }
    if ($keepSiteData) { Write-Host ("  would keep {0}\media, deployment.json and secrets (site data)" -f $dataDir) }
    else { Write-Host ("  would delete {0}" -f $dataDir) }
    Write-Host "  would remove logs, caches, scheduled tasks, SmartPark services and environment variables"
    if (-not $KeepApp) { Write-Host ("  would remove program files: {0}" -f ($installRoots -join ", ")) }
    exit 0
}

if (-not $Force) {
    Write-Host "This deletes SmartPark data on this PC, including:"
    if ($keepSiteData) { Write-Host "  logs and caches in %ProgramData%\SmartParkEdge (photos and database settings are KEPT)" }
    else { Write-Host "  %ProgramData%\SmartParkEdge  (database, media, logs)" }
    if ($resetDatabase) { Write-Host ("  ALL parking data in PostgreSQL database '{0}' on {1}" -f $site.database, $site.host) }
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
    "SmartPark Media Service",
    "SmartPark Recognition Worker"
)) {
    Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
}
foreach ($svc in @("SmartParkRecognitionWorker", "SmartParkMediaService", "SmartParkSiteService", "SmartParkHvxHost",
                   "SmartParkPortal", "SmartParkMockPayments")) {
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

if ($resetDatabase) {
    # Before the data folder goes: the database password is in its secret store.
    Write-Host ("Emptying PostgreSQL database '{0}'..." -f $site.database)
    $reset = Invoke-ZirpCli @("db", "reset", "--confirm-name", $ConfirmDatabaseName)
    if (-not $reset -or $reset.Code -ne 0) {
        $why = if ($reset -and $reset.Json) { $reset.Json.error } else { "no answer from the SmartPark program" }
        Write-Host ("Database reset failed: {0}" -f $why)
        Write-Host "Nothing was deleted. Fix the connection or use -SiteData Keep."
        exit 3
    }
    Write-Host ("  dropped {0} tables" -f $reset.Json.tables_dropped)
}

if ($keepSiteData) {
    Write-Host "Keeping site data (photos, database settings); deleting logs and caches..."
    if (Test-Path $dataDir) {
        Get-ChildItem $dataDir -Force | Where-Object { $_.Name -notin @("media", "secrets", "deployment.json") } |
            ForEach-Object { Remove-TreeRetry $_.FullName }
    }
} else {
    Write-Host "Deleting database, media, logs, and caches..."
    Remove-TreeRetry $dataDir
}
$dataRoots = @(
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
    Remove-Item (Join-Path ([Environment]::GetFolderPath("Desktop")) "SmartPark startup check.lnk") -Force -ErrorAction SilentlyContinue
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
if ($keepSiteData) { Write-Host "Wipe complete. Logs and caches are gone; the site database and photos were kept." }
elseif ($resetDatabase) { Write-Host "Wipe complete. The site database, media, logs, and caches are gone." }
else { Write-Host "Wipe complete. Database, media, logs, and caches are gone." }
if ($KeepApp) {
    Write-Host "Program files were kept. Restart Site Service or run Start-SmartPark.bat."
} else {
    Write-Host "Reinstall from the USB kit: double-click Install-SmartPark.bat"
}
exit 0
