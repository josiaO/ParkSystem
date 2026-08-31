#requires -Version 5.1
<#
.SYNOPSIS
    Install SmartPark Edge from this USB/folder onto this Windows PC.
    Double-click Install-SmartPark.bat. No project copy and no internet required.
#>
[CmdletBinding()]
param(
    [string]$InstallDir = "",
    [switch]$AllUsers,
    [switch]$StartApp
)

$ErrorActionPreference = "Stop"
$KitRoot = $PSScriptRoot
$Payload = Join-Path $KitRoot "payload"
if (-not (Test-Path (Join-Path $Payload "app"))) {
    throw "This folder is incomplete. Copy the whole SmartParkEdge-Install folder from the flash drive."
}

if (-not $InstallDir) {
    if ($AllUsers) {
        $InstallDir = Join-Path $env:ProgramFiles "SmartPark Edge"
    } else {
        $InstallDir = Join-Path $env:LOCALAPPDATA "Programs\SmartPark Edge"
    }
}

Write-Host "SmartPark Edge installer"
Write-Host "From: $KitRoot"
Write-Host "To:   $InstallDir"
Write-Host ""

function Stop-SmartParkProcesses {
    param([string]$Root)
    $root = ""
    if ($Root) { $root = [IO.Path]::GetFullPath($Root).TrimEnd("\") }
    Write-Host "Stopping any previous SmartPark Edge process..."
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $cmd = [string]$_.CommandLine
        $exe = [string]$_.ExecutablePath
        ($cmd -and (
            $cmd -like "*hvx_host.py*" -or
            $cmd -like "*app.desktop.launch*" -or
            $cmd -like "*app.desktop.main*" -or
            $cmd -like "*app.site_service*" -or
            $cmd -like "*app.media_service*" -or
            $cmd -like "*mediamtx.exe*" -or
            ($root -and $cmd -like "*$root*")
        )) -or ($root -and $exe -and $exe.StartsWith($root, [StringComparison]::OrdinalIgnoreCase))
    } | ForEach-Object {
        Write-Host ("  stopping {0} pid {1}" -f $_.Name, $_.ProcessId)
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 900
}

function Remove-SmartParkTree {
    param([string]$Path, [string]$InstallRoot)
    if (-not (Test-Path $Path)) { return }
    $attempt = 0
    while ($attempt -lt 6) {
        try {
            Remove-Item $Path -Recurse -Force -ErrorAction Stop
            return
        } catch {
            Stop-SmartParkProcesses -Root $InstallRoot
            Start-Sleep -Milliseconds (500 * ($attempt + 1))
            $attempt++
        }
    }
    $bak = "$Path.old-$PID"
    Rename-Item -Path $Path -NewName ([IO.Path]::GetFileName($bak)) -ErrorAction SilentlyContinue
    if (Test-Path $Path) {
        throw "Could not replace '$Path' because Windows still has it open. Close SmartPark Edge, then run Install-SmartPark.bat again."
    }
}

Stop-SmartParkProcesses -Root $InstallDir

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

$copyDirs = @("app", "tools", "vendor", "python64", "python32", "wheels", "models")
foreach ($name in $copyDirs) {
    $src = Join-Path $Payload $name
    if (-not (Test-Path $src)) { continue }
    Write-Host "Copying $name..."
    $dest = Join-Path $InstallDir $name
    if (Test-Path $dest) {
        Remove-SmartParkTree -Path $dest -InstallRoot $InstallDir
    }
    Copy-Item $src $dest -Recurse -Force
}

Copy-Item (Join-Path $Payload "requirements-windows.txt") (Join-Path $InstallDir "requirements-windows.txt") -Force
$docSrc = Join-Path $KitRoot "documentation"
if (Test-Path $docSrc) {
    Write-Host "Copying documentation..."
    $docDest = Join-Path $InstallDir "documentation"
    if (Test-Path $docDest) { Remove-SmartParkTree -Path $docDest -InstallRoot $InstallDir }
    Copy-Item $docSrc $docDest -Recurse -Force
}
$getPip = Join-Path $Payload "get-pip.py"
if (Test-Path $getPip) {
    Copy-Item $getPip (Join-Path $InstallDir "get-pip.py") -Force
}

$Py64 = Join-Path $InstallDir "python64\python.exe"
if (-not (Test-Path $Py64)) {
    throw "64-bit Python is missing from the kit (payload\python64)."
}

$Pth = Get-ChildItem (Join-Path $InstallDir "python64") -Filter "python*._pth" | Select-Object -First 1
if ($Pth) {
    # Embeddable Python ignores PYTHONPATH. ".." puts the install folder (app/) on sys.path.
    $lines = @(
        "python311.zip",
        ".",
        "..",
        "Lib\site-packages",
        "import site"
    )
    Set-Content -Path $Pth.FullName -Value ($lines -join "`r`n") -Encoding ASCII
}
$Pth32 = Get-ChildItem (Join-Path $InstallDir "python32") -Filter "python*._pth" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($Pth32) {
    $lines32 = @(
        "python311.zip",
        ".",
        "..\tools\hvx_sdk_host",
        "import site"
    )
    Set-Content -Path $Pth32.FullName -Value ($lines32 -join "`r`n") -Encoding ASCII
}

$Wheels = Join-Path $InstallDir "wheels"
$Pip = Join-Path $InstallDir "python64\Scripts\pip.exe"
Write-Host "Installing packages (offline, from the flash drive)..."
if (-not (Test-Path $Pip)) {
    $getPipDest = Join-Path $InstallDir "get-pip.py"
    if (-not (Test-Path $getPipDest)) {
        throw "get-pip.py is missing from the kit."
    }
    & $Py64 $getPipDest --no-warn-script-location --no-index --find-links $Wheels
    if ($LASTEXITCODE -ne 0) { throw "get-pip failed." }
}

# Install the bundled wheels as-is. Do not resolve version ranges against PyPI.
# If the USB folder still has two versions of the same package (old kits kept
# both websockets 15 and 17), keep the newest so pip does not fail.
$byDist = @{}
Get-ChildItem -Path $Wheels -Filter *.whl | ForEach-Object {
    $parts = $_.Name.Split("-", 3)
    if ($parts.Count -lt 2) { return }
    $dist = $parts[0].ToLowerInvariant()
    $ver = $null
    try { $ver = [version]$parts[1] } catch { $ver = $null }
    $prev = $byDist[$dist]
    $take = -not $prev
    if ($prev -and $ver -and $prev.Version) { $take = $ver -gt $prev.Version }
    elseif ($prev -and $ver -and -not $prev.Version) { $take = $true }
    if ($take) {
        $byDist[$dist] = @{ Path = $_.FullName; Version = $ver }
    }
}
$wheelFiles = @($byDist.Values | ForEach-Object { $_.Path })
if ($wheelFiles.Count -eq 0) {
    throw "No .whl files found in $Wheels"
}
Write-Host ("Installing {0} bundled wheels..." -f $wheelFiles.Count)
& $Py64 -m pip install --no-index --find-links $Wheels --no-deps @wheelFiles
if ($LASTEXITCODE -ne 0) { throw "Package install failed." }

$StartBat = Join-Path $InstallDir "Start-SmartPark.bat"
$StartCmd = @"
@echo off
cd /d "%~dp0"
set SMARTPARK_HOME=%~dp0
set SMARTPARK_HVX_VENDOR_DIR=%~dp0vendor
set PYTHONPATH=%~dp0
set PATH=%~dp0python64;%~dp0python64\Scripts;%~dp0python64\Lib\site-packages\PySide6;%~dp0python64\Lib\site-packages\shiboken6;%~dp0vendor;%PATH%
set QT_PLUGIN_PATH=%~dp0python64\Lib\site-packages\PySide6\plugins
set QT_QPA_PLATFORM_PLUGIN_PATH=%~dp0python64\Lib\site-packages\PySide6\plugins\platforms
"%~dp0python64\python.exe" -m app.desktop.launch
if errorlevel 1 (
  echo.
  echo SmartPark Edge did not start. See %ProgramData%\SmartParkEdge\logs\launch.log
  pause
)
"@
Set-Content -Path $StartBat -Value $StartCmd -Encoding ASCII

$Py64Dir = Join-Path $InstallDir "python64"
$ScriptsDir = Join-Path $Py64Dir "Scripts"
$PySideDir = Join-Path $Py64Dir "Lib\site-packages\PySide6"
$ShibokenDir = Join-Path $Py64Dir "Lib\site-packages\shiboken6"
$VendorDir = Join-Path $InstallDir "vendor"
$MediaMtxExe = Join-Path $VendorDir "mediamtx\mediamtx.exe"
$PluginsDir = Join-Path $PySideDir "plugins"
$PlatformsDir = Join-Path $PluginsDir "platforms"
$PathDirs = @($Py64Dir, $ScriptsDir, $PySideDir, $ShibokenDir, $VendorDir)

$UserVars = @{
    SMARTPARK_HOME                 = $InstallDir
    SMARTPARK_HVX_VENDOR_DIR       = $VendorDir
    PYTHONPATH                     = $InstallDir
    QT_PLUGIN_PATH                 = $PluginsDir
    QT_QPA_PLATFORM_PLUGIN_PATH    = $PlatformsDir
}
if (Test-Path $MediaMtxExe) {
    $UserVars["SMARTPARK_MEDIAMTX_BIN"] = $MediaMtxExe
}
Write-Host "Setting user environment variables..."
foreach ($name in $UserVars.Keys) {
    [Environment]::SetEnvironmentVariable($name, $UserVars[$name], "User")
    Set-Item -Path "Env:$name" -Value $UserVars[$name]
}

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($null -eq $userPath) { $userPath = "" }
$existing = @($userPath -split ";" | Where-Object { $_ })
$kept = @($existing | Where-Object {
    $entry = $_.TrimEnd("\")
    -not ($PathDirs | Where-Object { $_.TrimEnd("\") -eq $entry })
})
$newUserPath = (@($PathDirs) + $kept) -join ";"
[Environment]::SetEnvironmentVariable("Path", $newUserPath, "User")
$env:Path = (@($PathDirs) + @($env:Path -split ";")) -join ";"

try {
    Add-Type -Namespace SmartPark -Name Native -MemberDefinition @"
[DllImport("user32.dll", SetLastError=true, CharSet=CharSet.Auto)]
public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint Msg, UIntPtr wParam, string lParam, uint fuFlags, uint uTimeout, out UIntPtr lpdwResult);
"@ -ErrorAction SilentlyContinue
    $broadcast = [UIntPtr]::Zero
    [SmartPark.Native]::SendMessageTimeout([IntPtr]0xffff, 0x1A, [UIntPtr]::Zero, "Environment", 2, 5000, [ref]$broadcast) | Out-Null
} catch {}

$StartVbs = Join-Path $InstallDir "Start-SmartPark.vbs"
$Esc = { param($s) $s.Replace("\", "\\") }
$Vbs = @"
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "$(& $Esc $InstallDir)"
sh.Environment("Process")("SMARTPARK_HOME") = "$(& $Esc $InstallDir)"
sh.Environment("Process")("SMARTPARK_HVX_VENDOR_DIR") = "$(& $Esc $VendorDir)"
sh.Environment("Process")("PYTHONPATH") = "$(& $Esc $InstallDir)"
sh.Environment("Process")("PATH") = "$(& $Esc $Py64Dir);$(& $Esc $ScriptsDir);$(& $Esc $PySideDir);$(& $Esc $ShibokenDir);$(& $Esc $VendorDir);" & sh.Environment("Process")("PATH")
sh.Environment("Process")("QT_PLUGIN_PATH") = "$(& $Esc $PluginsDir)"
sh.Environment("Process")("QT_QPA_PLATFORM_PLUGIN_PATH") = "$(& $Esc $PlatformsDir)"
sh.Run """$(& $Esc $InstallDir)\\Start-SmartPark.bat""", 7, False
"@
Set-Content -Path $StartVbs -Value $Vbs -Encoding ASCII

$Programs = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\SmartPark"
New-Item -ItemType Directory -Force -Path $Programs | Out-Null
$Wsh = New-Object -ComObject WScript.Shell
$lnk = $Wsh.CreateShortcut((Join-Path $Programs "SmartPark Edge.lnk"))
$lnk.TargetPath = $StartBat
$lnk.WorkingDirectory = $InstallDir
$lnk.WindowStyle = 7
$lnk.Description = "SmartPark Edge"
$lnk.Save()

$Desktop = [Environment]::GetFolderPath("Desktop")
$desk = $Wsh.CreateShortcut((Join-Path $Desktop "SmartPark Edge.lnk"))
$desk.TargetPath = $StartBat
$desk.WorkingDirectory = $InstallDir
$desk.WindowStyle = 7
$desk.Description = "SmartPark Edge"
$desk.Save()

$Startup = [Environment]::GetFolderPath("Startup")
$boot = $Wsh.CreateShortcut((Join-Path $Startup "SmartPark Edge.lnk"))
$boot.TargetPath = $StartVbs
$boot.WorkingDirectory = $InstallDir
$boot.WindowStyle = 7
$boot.Description = "SmartPark Edge"
$boot.Save()

$Uninstall = Join-Path $InstallDir "Uninstall-SmartPark.ps1"
$UninstallBody = @"
`$ErrorActionPreference = 'Stop'
`$root = '$($InstallDir.Replace("'","''"))'
Unregister-ScheduledTask -TaskName 'SmartPark Site Service' -Confirm:`$false -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName 'SmartPark HVX Host' -Confirm:`$false -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName 'SmartPark Media Service' -Confirm:`$false -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    `$cmd = [string]`$_.CommandLine
    `$exe = [string]`$_.ExecutablePath
    (`$cmd -and (`$cmd -like '*hvx_host.py*' -or `$cmd -like '*app.desktop.launch*' -or `$cmd -like '*app.site_service*' -or `$cmd -like '*app.media_service*' -or `$cmd -like '*mediamtx.exe*' -or `$cmd -like "*`$root*")) -or (`$exe -and `$exe.StartsWith(`$root, [StringComparison]::OrdinalIgnoreCase))
} | ForEach-Object { Stop-Process -Id `$_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 800
`$pathDirs = @(
    '$(($Py64Dir).Replace("'","''"))',
    '$(($ScriptsDir).Replace("'","''"))',
    '$(($PySideDir).Replace("'","''"))',
    '$(($ShibokenDir).Replace("'","''"))',
    '$(($VendorDir).Replace("'","''"))'
)
`$vars = @{
    SMARTPARK_HOME = '$($InstallDir.Replace("'","''"))'
    SMARTPARK_HVX_VENDOR_DIR = '$($VendorDir.Replace("'","''"))'
    PYTHONPATH = '$($InstallDir.Replace("'","''"))'
    QT_PLUGIN_PATH = '$($PluginsDir.Replace("'","''"))'
    QT_QPA_PLATFORM_PLUGIN_PATH = '$($PlatformsDir.Replace("'","''"))'
}
foreach (`$name in `$vars.Keys) {
    `$cur = [Environment]::GetEnvironmentVariable(`$name, 'User')
    if (`$cur -eq `$vars[`$name]) {
        [Environment]::SetEnvironmentVariable(`$name, `$null, 'User')
    }
}
`$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (`$userPath) {
    `$kept = @(`$userPath -split ';' | Where-Object {
        `$entry = `$_.TrimEnd('\')
        -not (`$pathDirs | Where-Object { `$_.TrimEnd('\') -eq `$entry })
    })
    [Environment]::SetEnvironmentVariable('Path', (`$kept -join ';'), 'User')
}
Remove-Item (Join-Path `$env:APPDATA 'Microsoft\Windows\Start Menu\Programs\SmartPark') -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath('Desktop')) 'SmartPark Edge.lnk') -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath('Startup')) 'SmartPark Edge.lnk') -Force -ErrorAction SilentlyContinue
Remove-Item `$root -Recurse -Force
Write-Host 'SmartPark Edge removed. Camera database is still in %ProgramData%\SmartParkEdge'
"@
Set-Content -Path $Uninstall -Value $UninstallBody -Encoding ASCII

$svcScript = Join-Path $KitRoot "Install-SmartParkServices.ps1"
if (Test-Path $svcScript) {
    Copy-Item $svcScript (Join-Path $InstallDir "Install-SmartParkServices.ps1") -Force
}
foreach ($helper in @("Enable-MediaMTX.ps1", "MediaMTX-SoakTest.ps1")) {
    $src = Join-Path $KitRoot $helper
    if (Test-Path $src) {
        Copy-Item $src (Join-Path $InstallDir $helper) -Force
    }
}
if (Test-Path $svcScript) {
    Write-Host "Starting Site Service, HVX host, and Media Service (MediaMTX idle until enabled)..."
    try {
        & $svcScript -InstallDir $InstallDir
    } catch {
        Write-Host ("WARNING: Could not register background tasks: {0}" -f $_)
        Write-Host "The Desktop shortcut still starts the API if the tasks are missing."
    }
}

Write-Host ""
Write-Host "Installed."
Write-Host "  Open: Desktop shortcut 'SmartPark Edge'"
Write-Host "  Background: Site Service + HVX host + Media Service start at Windows logon"
if (Test-Path $MediaMtxExe) {
    Write-Host "  MediaMTX: bundled (off until Enable-MediaMTX.ps1)"
}
Write-Host "  Login: admin  /  SmartPark1!"
Write-Host "  Then: Add site cameras  ->  Connect all"
Write-Host "  Vehicles: register plates that should open the gate"
Write-Host "  If it fails: %ProgramData%\SmartParkEdge\logs\launch.log"
Write-Host "  Documentation: $InstallDir\documentation\index.html"
Write-Host "  Uninstall: $Uninstall"
Write-Host ""

if ($StartApp) {
    Start-Process -FilePath $StartBat -WorkingDirectory $InstallDir
} else {
    $answer = Read-Host "Start SmartPark Edge now? (Y/n)"
    if ($answer -notmatch '^[nN]') {
        Start-Process -FilePath $StartBat -WorkingDirectory $InstallDir
    }
}
