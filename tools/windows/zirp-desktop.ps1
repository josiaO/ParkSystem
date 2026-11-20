<#
.SYNOPSIS
  Start or restart the Zirp desktop app in one step.

.DESCRIPTION
  Closes the running Zirp desktop (asks Windows for permission once if it
  was started as administrator), then starts it again.

  By default the desktop runs straight from the project folder
  (C:\SmartParkEdge), so a desktop change takes effect on the next restart
  without copying files into the installed app. The installed Python, Qt and
  the Site Server services are used as they are. Use -Installed to start the
  installed copy instead.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\windows\zirp-desktop.ps1
  powershell -ExecutionPolicy Bypass -File tools\windows\zirp-desktop.ps1 -Installed
#>
param(
    [switch]$Installed,
    [switch]$NoElevate
)

$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

function Resolve-ZirpInstall {
    <# Find the installed runtime whichever Windows user installed it.
       1. Per-machine install (new installer): HKLM\SOFTWARE\Zirp InstallDir\current
       2. Where the running Site Service actually lives (NSSM: <root>\vendor\nssm\nssm.exe)
       3. Old per-user installs: this user's, then any user's LOCALAPPDATA #>
    $candidates = @()
    try {
        $key = Get-ItemProperty -Path 'HKLM:\SOFTWARE\Zirp' -ErrorAction Stop
        if ($key.InstallDir) { $candidates += (Join-Path $key.InstallDir 'current') }
    } catch {}
    foreach ($svc in @('ZirpSiteService', 'SmartParkSiteService')) {
        $row = Get-CimInstance Win32_Service -Filter "Name='$svc'" -ErrorAction SilentlyContinue
        if ($row -and $row.PathName) {
            $exe = $row.PathName.Trim().Trim('"')
            if ($exe -match '\\vendor\\nssm\\nssm\.exe$') {
                $candidates += (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $exe)))
            }
        }
    }
    $candidates += (Join-Path $env:LOCALAPPDATA 'Programs\SmartPark Edge')
    $candidates += Get-ChildItem 'C:\Users' -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { Join-Path $_.FullName 'AppData\Local\Programs\SmartPark Edge' }
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path (Join-Path $candidate 'python64\python.exe'))) { return $candidate }
    }
    throw "No installed Zirp runtime found. Looked in: $($candidates -join '; ')"
}

$install = Resolve-ZirpInstall
$python = Join-Path $install 'python64\python.exe'
$lockPid = Join-Path $env:ProgramData 'SmartParkEdge\locks\desktop.lock'

function Get-DesktopProcess {
    $ids = @()
    if (Test-Path $lockPid) {
        $raw = (Get-Content $lockPid -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($raw -match '^\d+$') { $ids += [int]$raw }
    }
    $ids += Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like '*app.desktop.launch*' } | ForEach-Object { [int]$_.ProcessId }
    $ids | Select-Object -Unique | ForEach-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue } |
        Where-Object { $_.ProcessName -eq 'python' }
}

$running = @(Get-DesktopProcess)
foreach ($proc in $running) {
    try {
        Stop-Process -Id $proc.Id -Force -ErrorAction Stop
    } catch {
        $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
            [Security.Principal.WindowsBuiltInRole]::Administrator)
        if ($isAdmin -or $NoElevate) { throw "Could not close the running Zirp desktop (process $($proc.Id)): $_" }
        # Started as administrator: closing it needs the same rights. Ask once, then run this script again.
        $args = @('-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"", '-NoElevate')
        if ($Installed) { $args += '-Installed' }
        Start-Process powershell -Verb RunAs -ArgumentList $args
        exit 0
    }
}
if ($running.Count) { Start-Sleep -Seconds 1 }

if (-not (Test-Path $python)) { throw "Installed Python not found at $python" }
$root = if ($Installed) { $install } else { $project }
$site = Join-Path $install 'python64\Lib\site-packages'
$env:SMARTPARK_DEPLOYMENT_PROFILE = 'PRODUCTION'
$env:SMARTPARK_ROLE_LOCKED = 'SITE_SERVER'
if (-not $env:SMARTPARK_NODE_ROLE) { $env:SMARTPARK_NODE_ROLE = 'SERVER' }
$env:SMARTPARK_HVX_VENDOR_DIR = Join-Path $install 'vendor'
$env:PYTHONPATH = $root
$env:PATH = "$install\python64;$install\python64\Scripts;$site\PySide6;$site\shiboken6;$install\vendor;$env:PATH"
$env:QT_PLUGIN_PATH = "$site\PySide6\plugins"
$env:QT_QPA_PLATFORM_PLUGIN_PATH = "$site\PySide6\plugins\platforms"
Start-Process -FilePath $python -ArgumentList '-m', 'app.desktop.launch' -WorkingDirectory $root -WindowStyle Hidden
Write-Host "Zirp desktop started from $root"
