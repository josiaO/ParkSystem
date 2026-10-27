#requires -Version 5.1
<#
.SYNOPSIS
    Install Zirp from this USB/folder onto this Windows PC.
    Double-click Install-SmartPark.bat. No project copy and no internet required.
#>
[CmdletBinding()]
param(
    [string]$InstallDir = "",
    [switch]$AllUsers,
    [switch]$StartApp
)

$ErrorActionPreference = "Stop"

# Keep diagnostics outside the installation tree, which is replaced on upgrades.
$InstallerLog = Join-Path ([IO.Path]::GetTempPath()) ("SmartPark-install-{0}-{1}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'), $PID)
$TranscriptStarted = $false
trap {
    Write-Host ""
    Write-Host "INSTALLATION FAILED" -ForegroundColor Red
    Write-Host ($_ | Format-List * -Force | Out-String)
    Write-Host $_.ScriptStackTrace
    Write-Host "Installer log: $InstallerLog"
    if ($TranscriptStarted) { Stop-Transcript -ErrorAction SilentlyContinue | Out-Null }
    # The elevated PowerShell window otherwise closes before the error is readable.
    Read-Host "Press Enter to close this failed installer"
    exit 1
}
Start-Transcript -Path $InstallerLog -Force | Out-Null
$TranscriptStarted = $true
Write-Host "Installer log: $InstallerLog"

# Task registration must succeed before this installation is reported ready.
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Administrator approval is required to register Zirp background tasks."
    $elevation = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    if ($InstallDir) { $elevation += " -InstallDir `"$InstallDir`"" }
    if ($AllUsers) { $elevation += " -AllUsers" }
    if ($StartApp) { $elevation += " -StartApp" }
    try {
        $elevated = Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $elevation -Wait -PassThru
        if ($null -eq $elevated) { exit 1 }
        exit $elevated.ExitCode
    } catch {
        throw "Installation stopped: administrator approval was not granted. $($_.Exception.Message)"
    }
}
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

Write-Host "Zirp installer"
Write-Host "From: $KitRoot"
Write-Host "To:   $InstallDir"
$buildInfo = Join-Path $KitRoot "BUILD-INFO.txt"
if (Test-Path $buildInfo) {
    Write-Host "Kit build: $((Get-Content -LiteralPath $buildInfo -Raw -Encoding UTF8).Trim())"
}
Write-Host ""

function Stop-SmartParkProcesses {
    param([string]$Root)
    $root = ""
    if ($Root) { $root = [IO.Path]::GetFullPath($Root).TrimEnd("\") }
    Write-Host "Stopping any previous Zirp process..."
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $cmd = [string]$_.CommandLine
        $exe = [string]$_.ExecutablePath
        ($cmd -and (
            $cmd -like "*hvx_host.py*" -or
            $cmd -like "*app.desktop.launch*" -or
            $cmd -like "*app.desktop.main*" -or
            $cmd -like "*app.site_service*" -or
            $cmd -like "*app.media_service*" -or
            $cmd -like "*app.recognition_worker*" -or
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
if (Test-Path $buildInfo) {
    Copy-Item $buildInfo (Join-Path $InstallDir "BUILD-INFO.txt") -Force
}

$copyDirs = @("app", "tools", "vendor", "python64", "python32", "wheels", "wheels32", "models")
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
# Development/build layouts may carry the technician markdown under docs
# instead of the assembled documentation folder. Include the actual database
# and deployment procedures in the installed kit without changing the normal
# operator workflow.
$repoDocs = Join-Path $KitRoot "..\..\docs"
if (-not (Test-Path $repoDocs)) { $repoDocs = Join-Path $KitRoot "..\docs" }
if ((Test-Path $repoDocs) -and -not (Test-Path (Join-Path $InstallDir "documentation\DATABASE_CONFIGURATION.md"))) {
    $docDest = Join-Path $InstallDir "documentation"
    New-Item -ItemType Directory -Force -Path $docDest | Out-Null
    Copy-Item (Join-Path $repoDocs "DATABASE_CONFIGURATION.md") $docDest -Force -ErrorAction SilentlyContinue
    Copy-Item (Join-Path $repoDocs "DEPLOYMENT.md") $docDest -Force -ErrorAction SilentlyContinue
}
$getPip = Join-Path $Payload "get-pip.py"
if (Test-Path $getPip) {
    Copy-Item $getPip (Join-Path $InstallDir "get-pip.py") -Force
}

$Py64 = Join-Path $InstallDir "python64\python.exe"
if (-not (Test-Path $Py64)) {
    throw "64-bit Python is missing from the kit (payload\python64)."
}
foreach ($runtimeDll in @("msvcp140.dll", "msvcp140_1.dll", "vcruntime140.dll", "vcruntime140_1.dll")) {
    if (-not (Test-Path (Join-Path $InstallDir "python64\$runtimeDll"))) {
        throw "The bundled 64-bit C++ runtime is incomplete: python64\$runtimeDll is missing. Rebuild the installation kit."
    }
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
        "Lib\site-packages",
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
& $Py64 -m pip check
if ($LASTEXITCODE -ne 0) { throw "Installed Python dependencies are incompatible. Rebuild the offline wheel bundle." }

$Py32 = Join-Path $InstallDir "python32\python.exe"
$Wheels32 = Join-Path $InstallDir "wheels32"
if ((Test-Path $Py32) -and (Test-Path $Wheels32)) {
    $pillow32 = Get-ChildItem -Path $Wheels32 -Filter "pillow-*-win32.whl" | Select-Object -First 1
    if ($pillow32) {
        $site32 = Join-Path $InstallDir "python32\Lib\site-packages"
        New-Item -ItemType Directory -Force -Path $site32 | Out-Null
        # The 32-bit host only needs Pillow. Extracting this wheel avoids
        # installing a second pip stack into the vendor-compatible interpreter.
        $pillowZip = Join-Path ([IO.Path]::GetTempPath()) ("SmartPark-Pillow32-{0}.zip" -f $PID)
        Copy-Item $pillow32.FullName $pillowZip -Force
        Expand-Archive -LiteralPath $pillowZip -DestinationPath $site32 -Force
        Remove-Item -LiteralPath $pillowZip -Force -ErrorAction SilentlyContinue
    } else {
        Write-Warning "32-bit Pillow wheel missing; HVX runtime will be unavailable until the server kit is repaired."
    }
} else {
    Write-Host "32-bit HVX runtime not present; this is valid for an Operator Workstation and generic RTSP Site Server."
}

$RuntimeCheck = Join-Path $InstallDir "tools\hvx_sdk_host\check_runtime.py"
if ((Test-Path $Py32) -and (Test-Path $RuntimeCheck)) {
    & $Py32 $RuntimeCheck --vendor-dir (Join-Path $InstallDir "vendor")
    if ($LASTEXITCODE -ne 0) { Write-Warning "Vendor DLL load check failed. HVX cameras will remain unavailable until the Site Server runtime is repaired." }
}

$StartBat = Join-Path $InstallDir "Start-SmartPark.bat"
$StartCmd = @"
@echo off
cd /d "%~dp0"
set SMARTPARK_HOME=%~dp0
set SMARTPARK_HVX_VENDOR_DIR=%~dp0vendor
set SMARTPARK_DEPLOYMENT_PROFILE=PRODUCTION
set PYTHONPATH=%~dp0
set PATH=%~dp0python64;%~dp0python64\Scripts;%~dp0python64\Lib\site-packages\PySide6;%~dp0python64\Lib\site-packages\shiboken6;%~dp0vendor;%PATH%
set QT_PLUGIN_PATH=%~dp0python64\Lib\site-packages\PySide6\plugins
set QT_QPA_PLATFORM_PLUGIN_PATH=%~dp0python64\Lib\site-packages\PySide6\plugins\platforms
"%~dp0python64\python.exe" -m app.desktop.launch
if errorlevel 1 (
  echo.
  echo Zirp did not start. See %ProgramData%\SmartParkEdge\logs\launch.log
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
sh.Environment("Process")("SMARTPARK_DEPLOYMENT_PROFILE") = "PRODUCTION"
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
$IconFile = Join-Path $InstallDir "app\assets\zirp.ico"
$lnk = $Wsh.CreateShortcut((Join-Path $Programs "SmartPark Edge.lnk"))
$lnk.TargetPath = $StartBat
$lnk.WorkingDirectory = $InstallDir
$lnk.WindowStyle = 7
$lnk.Description = "Zirp"
if (Test-Path $IconFile) { $lnk.IconLocation = "$IconFile,0" }
$lnk.Save()

$Desktop = [Environment]::GetFolderPath("Desktop")
$desk = $Wsh.CreateShortcut((Join-Path $Desktop "SmartPark Edge.lnk"))
$desk.TargetPath = $StartBat
$desk.WorkingDirectory = $InstallDir
$desk.WindowStyle = 7
$desk.Description = "Zirp"
if (Test-Path $IconFile) { $desk.IconLocation = "$IconFile,0" }
$desk.Save()

$CheckBat = Join-Path $InstallDir "Run-StartupCheck.bat"
$checkMenu = $Wsh.CreateShortcut((Join-Path $Programs "SmartPark startup check.lnk"))
$checkMenu.TargetPath = $CheckBat
$checkMenu.WorkingDirectory = $InstallDir
$checkMenu.Description = "Check video, recognition, and a gate dry-run. Does not open the barrier."
$checkMenu.Save()
$checkDesk = $Wsh.CreateShortcut((Join-Path $Desktop "SmartPark startup check.lnk"))
$checkDesk.TargetPath = $CheckBat
$checkDesk.WorkingDirectory = $InstallDir
$checkDesk.Description = "Check video, recognition, and a gate dry-run. Does not open the barrier."
$checkDesk.Save()

$logsShortcut = $Wsh.CreateShortcut((Join-Path $Desktop "SmartPark logs.lnk"))
$logsShortcut.TargetPath = Join-Path $InstallDir "Open-SmartParkLogs.bat"
$logsShortcut.WorkingDirectory = $InstallDir
$logsShortcut.Description = "Open SmartPark service and camera logs"
$logsShortcut.Save()

# Background tasks own parking. Do not auto-launch the heavier desktop UI.
$Startup = [Environment]::GetFolderPath("Startup")
Remove-Item (Join-Path $Startup "SmartPark Edge.lnk") -Force -ErrorAction SilentlyContinue
$WebShortcut = "[InternetShortcut]`r`nURL=http://127.0.0.1:8760/`r`n"
Set-Content (Join-Path $Desktop "SmartPark Edge Web.url") $WebShortcut -Encoding ASCII
Set-Content (Join-Path $Programs "SmartPark Edge Web.url") $WebShortcut -Encoding ASCII

$Uninstall = Join-Path $InstallDir "Uninstall-SmartPark.ps1"
$UninstallBody = @"
`$ErrorActionPreference = 'Stop'
`$root = '$($InstallDir.Replace("'","''"))'
Unregister-ScheduledTask -TaskName 'SmartPark Site Service' -Confirm:`$false -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName 'SmartPark HVX Host' -Confirm:`$false -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName 'SmartPark Media Service' -Confirm:`$false -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName 'SmartPark Recognition Worker' -Confirm:`$false -ErrorAction SilentlyContinue
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
Remove-Item (Join-Path ([Environment]::GetFolderPath('Desktop')) 'SmartPark startup check.lnk') -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath('Desktop')) 'SmartPark logs.lnk') -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath('Desktop')) 'SmartPark Edge Web.url') -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath('Startup')) 'SmartPark Edge.lnk') -Force -ErrorAction SilentlyContinue
Remove-Item `$root -Recurse -Force
Write-Host 'SmartPark Edge removed. Camera database is still in %ProgramData%\SmartParkEdge unless you run Wipe-SmartPark.bat'
"@
Set-Content -Path $Uninstall -Value $UninstallBody -Encoding ASCII

$svcScript = Join-Path $KitRoot "Install-SmartParkServices.ps1"
$deploymentPath = Join-Path $env:ProgramData "SmartParkEdge\deployment.json"
$databasePath = Join-Path $env:ProgramData "SmartParkEdge\smartpark.db"
$freshDeployment = -not (Test-Path $deploymentPath) -and -not (Test-Path $databasePath)
$configuredRole = ""
$deploymentConfigured = $false
if (Test-Path $deploymentPath) {
    try {
        $deployment = Get-Content -LiteralPath $deploymentPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $configuredRole = [string]$deployment.role
        # A previous wizard attempt can leave deployment.json and a database
        # behind while the role/setup is still incomplete.  Do not start the
        # API against that partial state: it exits immediately and leaves the
        # installer looking healthy until the later MediaMTX step fails.
        $deploymentConfigured = [bool]$deployment.configured -and (
            -not $deployment.PSObject.Properties['state'] -or
            [string]$deployment.state -eq "CONFIGURED"
        )
    } catch {
        throw "The existing SmartPark deployment configuration is invalid: $($_.Exception.Message)"
    }
}
$setupRequired = $freshDeployment -or -not $deploymentConfigured
if (Test-Path $svcScript) {
    Copy-Item $svcScript (Join-Path $InstallDir "Install-SmartParkServices.ps1") -Force
}
foreach ($helper in @("Install-SmartParkWinService.ps1", "Enable-MediaMTX.ps1", "MediaMTX-SoakTest.ps1", "Run-FieldAcceptanceTest.ps1", "Run-FieldAcceptanceTest.bat", "Run-StartupCheck.ps1", "Run-StartupCheck.bat", "Open-SmartParkLogs.bat", "Run-CameraLab.ps1", "Run-CameraLab.bat", "Wipe-SmartPark.ps1", "Wipe-SmartPark.bat")) {
    $src = Join-Path $KitRoot $helper
    if (Test-Path $src) {
        Copy-Item $src (Join-Path $InstallDir $helper) -Force
    }
}
if ((Test-Path $svcScript) -and $configuredRole -ne "OPERATOR_CLIENT") {
    if ($setupRequired) {
        Write-Host "Registering background tasks; startup is deferred until the native wizard completes deployment setup..."
    } else {
        Write-Host "Starting Site Service, HVX host, Media Service and Recognition Worker..."
    }
    try {
        if ($setupRequired) {
            & $svcScript -InstallDir $InstallDir -RegisterOnly
        } else {
            & $svcScript -InstallDir $InstallDir
        }
    } catch {
        throw "Background task registration failed: $_"
    }
}
$enableMedia = Join-Path $InstallDir "Enable-MediaMTX.ps1"
if ((Test-Path $enableMedia) -and -not $setupRequired -and $configuredRole -ne "OPERATOR_CLIENT") {
    & $enableMedia -InstallDir $InstallDir -LiveView
}

Write-Host ""
$env:SMARTPARK_HOME = $InstallDir
$env:PYTHONPATH = $InstallDir
$env:SMARTPARK_HVX_VENDOR_DIR = Join-Path $InstallDir "vendor"
if (-not $setupRequired -and $configuredRole -ne "OPERATOR_CLIENT") {
    Write-Host "Setting the sign-in password to the install password..."
    & $Py64 -m app.cli reset-admin
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Could not set the admin password. The file is %ProgramData%\SmartParkEdge\bootstrap_password.txt"
    }
} elseif ($setupRequired) {
    Write-Host "Deployment setup is incomplete: role setup and service startup are deferred to the native wizard."
} else {
    Write-Host "Operator Workstation detected: no local database, camera, gate or recognition services will be started."
}

$AdminStart = Join-Path $InstallDir "Start-SmartPark-Admin.ps1"
$AdminBody = @"
`$ErrorActionPreference = 'Continue'
`$root = '$($InstallDir.Replace("'","''"))'
`$services = Join-Path `$root 'Install-SmartParkServices.ps1'
if (Test-Path `$services) {
    try { & `$services -InstallDir `$root } catch { Write-Host `$_ }
}
`$start = Join-Path `$root 'Start-SmartPark.bat'
Start-Process -FilePath 'cmd.exe' -ArgumentList ('/c start `"SmartPark Edge`" `"' + `$start + '`"') -WorkingDirectory `$root
Start-Sleep -Seconds 3
Start-Process 'http://127.0.0.1:8760/'
"@
Set-Content -Path $AdminStart -Value $AdminBody -Encoding ASCII

function Test-SmartParkAdmin {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Start-SmartParkFromInstaller {
    Write-Host "Opening the desktop and the browser..."
    $startArgs = '/c start "SmartPark Edge" "' + $StartBat + '"'
    if (Test-SmartParkAdmin) {
        Start-Process -FilePath "cmd.exe" -ArgumentList $startArgs -WorkingDirectory $InstallDir
        Start-Sleep -Seconds 3
        if (-not $setupRequired -and $configuredRole -ne "OPERATOR_CLIENT") {
            Start-Process "http://127.0.0.1:8760/"
        }
        return
    }
    Write-Host ""
    Write-Host "Windows will ask to start SmartPark Edge from an administrator prompt."
    Write-Host "Approve it so Site Service, the HVX host, and Media Service can register."
    try {
        Start-Process -FilePath "powershell.exe" -Verb RunAs -Wait -ArgumentList @(
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $AdminStart
        )
    } catch {
        Write-Host "The administrator prompt was not approved. Background services were not registered."
        Write-Host "Run this again and approve the prompt, or right-click Start-SmartPark-Admin.ps1 and choose Run as administrator."
    }
}

Write-Host ""
Write-Host "Installed."
Write-Host "  Open: Zirp (desktop operator UI). Zirp Web is for administration/remote access."
Write-Host "  Background: Site Service + HVX host + Media Service + Recognition Worker start at Windows logon"
if (Test-Path $MediaMtxExe) {
    Write-Host "  MediaMTX: enabled for RTSP cameras; SDK cameras use their SDK JPEG path"
}
Write-Host "  Login: admin. Use the password printed above. It is also in %ProgramData%\SmartParkEdge\bootstrap_password.txt"
Write-Host "  Then: Add site cameras  ->  Connect all"
Write-Host "  Startup check (after the app is open): double-click SmartPark startup check"
Write-Host "  Field test (cars passing): double-click Run-FieldAcceptanceTest.bat"
Write-Host "  Camera picture test: double-click Run-CameraLab.bat in this install folder"
Write-Host "  Factory reset (DB + cache + app): double-click Wipe-SmartPark.bat"
Write-Host "  Vehicles: register plates that should open the gate"
Write-Host "  If it fails: %ProgramData%\SmartParkEdge\logs\launch.log"
Write-Host "  Documentation: $InstallDir\documentation\index.html"
Write-Host "  Uninstall: $Uninstall"
Write-Host ""

if ($StartApp) {
    Start-SmartParkFromInstaller
} else {
    $answer = Read-Host "Start SmartPark Edge from an administrator prompt now? (Y/n)"
    if ($answer -notmatch '^[nN]') {
        Start-SmartParkFromInstaller
    }
}
Write-Host "Installer log: $InstallerLog"
Stop-Transcript | Out-Null
