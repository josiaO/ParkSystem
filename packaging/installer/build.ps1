#requires -Version 5.1
<#
.SYNOPSIS
    Build the Zirp Windows installer (Zirp-Setup-<version>.exe) from this repository.

.DESCRIPTION
    Runs on a Windows build machine. Produces one self-contained installer that
    needs no Python, Node, compiler or internet on the customer's PC.

      1. Stage the release: app, tools, models, embedded CPython 3.11 (64-bit and
         32-bit) with every Python package installed at build time from the
         offline wheel bundle, camera SDK and vendor binaries, the portal as a
         Next.js standalone build with its own node.exe.
      2. Verify: QY SDK hashes against its manifest, import/ONNX smoke test with
         the staged interpreter, and a secret scan (the build fails if any
         settings file, key, database or credential is in the payload).
      3. Sign (only when a code-signing certificate is supplied): our PowerShell
         tools, the installer and the uninstaller.
      4. Compile packaging\installer\Zirp.iss with Inno Setup 6, write SHA-256.

    Inputs that are not in Git (supplied by the build machine):
      -ThirdPartyDir  camera SDK DLLs, ffmpeg, mediamtx, nssm, VC++ redistributables
                      (vendor\...), FastALPR models (models\...), wheels (wheels\, wheels32\).
                      Default: packaging\thirdparty (git-ignored; never commit vendor binaries).
      -CacheDir       python-3.11.9-embed-amd64.zip / -win32.zip (default packaging\cache)

    Signing (optional; never stored in the repository):
      -CertThumbprint <SHA1>   certificate in CurrentUser\My or LocalMachine\My, or
      $env:ZIRP_SIGN_PFX + $env:ZIRP_SIGN_PFX_PASSWORD
      -TimestampUrl            default http://timestamp.digicert.com

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File packaging\installer\build.ps1 -Version 1.4.0
    powershell -ExecutionPolicy Bypass -File packaging\installer\build.ps1 -Version 1.4.0 -CertThumbprint 0123ABCD...
    powershell -ExecutionPolicy Bypass -File packaging\installer\build.ps1 -Version 1.4.0 -StageOnly
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$ThirdPartyDir = "",
    [string]$CacheDir = "",
    [string]$BuildPython = "",
    [string]$NodeExe = "",
    [string]$Iscc = "",
    [string]$OutDir = "",
    [string]$CertThumbprint = "",
    [string]$TimestampUrl = "http://timestamp.digicert.com",
    [switch]$SkipPortal,
    [switch]$StageOnly,
    [switch]$IncludeSource,
    [switch]$AllowUnsigned = $true
)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if ($Version -notmatch '^\d+\.\d+\.\d+([-+][0-9A-Za-z.\-]+)?$') { throw "Version must look like 1.4.0 or 1.4.0-rc1." }
$Numeric = ($Version -replace '[-+].*$', '') + ".0"
if (-not $ThirdPartyDir) { $ThirdPartyDir = Join-Path $Repo "packaging\thirdparty" }
if (-not $CacheDir) { $CacheDir = Join-Path $Repo "packaging\cache" }
if (-not $OutDir) { $OutDir = Join-Path $Repo "dist\installer" }
$Work = Join-Path $Repo "build\installer"
$Stage = Join-Path $Work "stage"
$BinStage = Join-Path $Work "bin"
$PyVer = "3.11.9"

function Step([string]$Text) { Write-Host ""; Write-Host "==> $Text" -ForegroundColor Cyan }
function Need([string]$Path, [string]$What) { if (-not (Test-Path $Path)) { throw "$What not found: $Path" } }

function Find-BuildPython {
    if ($BuildPython) { return $BuildPython }
    $candidates = @()
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) { try { $candidates += (& py.exe -3.11 -c "import sys; print(sys.executable)" 2>$null) } catch {} }
    foreach ($c in $candidates) {
        if ($c -and (Test-Path $c)) {
            $ok = & $c -c "import sys, pip; print(sys.version_info[:2] == (3, 11) and sys.maxsize > 2**32)" 2>$null
            if ($ok -eq "True") { return $c }
        }
    }
    return New-BuildToolchain
}

function New-BuildToolchain {
    <# No suitable Python on this machine: make a private build interpreter from
       the cached embedded CPython and the cached pip wheel. Offline, kept in
       build\toolchain, never shipped. #>
    $tc = Join-Path $Repo "build\toolchain\python"
    $exe = Join-Path $tc "python.exe"
    if (Test-Path $exe) {
        $ok = & $exe -c "import pip; print('ok')" 2>$null
        if ($ok -eq "ok") { return $exe }
    }
    $pipWheel = Get-ChildItem (Join-Path $CacheDir "wheels-win64"), (Join-Path $ThirdPartyDir "wheels") -Filter "pip-*.whl" -ErrorAction SilentlyContinue |
        Sort-Object { [version]($_.Name.Split("-")[1]) } -Descending | Select-Object -First 1
    if (-not $pipWheel) { throw "No Python 3.11 with pip on this machine and no cached pip wheel to bootstrap one (-BuildPython)." }
    Write-Host "Bootstrapping a private build Python in $tc"
    if (Test-Path $tc) { Remove-Item $tc -Recurse -Force }
    Expand-Archive -LiteralPath (Join-Path $CacheDir "python-$PyVer-embed-amd64.zip") -DestinationPath $tc -Force
    $site = Join-Path $tc "Lib\site-packages"
    New-Item -ItemType Directory -Force -Path $site | Out-Null
    Set-Content -Path (Join-Path $tc "python311._pth") -Value "python311.zip`r`n.`r`nLib\site-packages`r`nimport site`r`n" -Encoding ASCII -NoNewline
    $zip = Join-Path $tc "pip.zip"; Copy-Item $pipWheel.FullName $zip
    Expand-Archive -LiteralPath $zip -DestinationPath $site -Force; Remove-Item $zip
    $ok = & $exe -c "import pip; print('ok')" 2>$null
    if ($ok -ne "ok") { throw "Could not bootstrap the build Python." }
    return $exe
}

function Find-SignTool {
    $kits = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
    $tool = Get-ChildItem $kits -Filter signtool.exe -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match '\\x64\\' } | Sort-Object FullName -Descending | Select-Object -First 1
    if (-not $tool) { throw "Signing requested but signtool.exe (Windows SDK) is not installed." }
    return $tool.FullName
}

function Find-Iscc {
    if ($Iscc) { return $Iscc }
    foreach ($c in @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
                     "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe")) {
        if (Test-Path $c) { return $c }
    }
    throw "Inno Setup 6 is not installed (winget install JRSoftware.InnoSetup), or pass -Iscc."
}

function Copy-Tree([string]$From, [string]$To) {
    New-Item -ItemType Directory -Force -Path $To | Out-Null
    & robocopy.exe $From $To /E /NFL /NDL /NJH /NJS /NP /XD __pycache__ .pytest_cache /XF *.pyc *.pyo | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy $From -> $To failed ($LASTEXITCODE)" }
    $global:LASTEXITCODE = 0
}

# ---------------------------------------------------------------------------- inputs
Step "Checking inputs"
Need $ThirdPartyDir "Third-party payload"
Need (Join-Path $ThirdPartyDir "vendor\NetSDK.dll") "QY camera SDK"
Need (Join-Path $ThirdPartyDir "vendor\nssm\nssm.exe") "NSSM"
Need (Join-Path $ThirdPartyDir "vendor\ffmpeg\bin\ffmpeg.exe") "FFmpeg (vendor\ffmpeg\bin\ffmpeg.exe)"
Need (Join-Path $ThirdPartyDir "vendor\mediamtx\mediamtx.exe") "MediaMTX (vendor\mediamtx\mediamtx.exe)"
# Redis for Windows is optional: with it, camera PCs get the "Zirp Shared Cache"
# service; without it Zirp keeps lane state in each process's memory.
if (Test-Path (Join-Path $ThirdPartyDir "vendor\redis\redis-server.exe")) {
    Write-Host "  Redis: bundled (vendor\redis)"
} else {
    Write-Host "  Redis: not bundled (put redis-server.exe and its DLLs in vendor\redis to include it)" -ForegroundColor Yellow
}
Need (Join-Path $ThirdPartyDir "models\fastalpr\detector\yolo-v9-t-384-license-plates-end2end.onnx") "FastALPR detector model"
Need (Join-Path $ThirdPartyDir "wheels") "Offline wheel bundle"
Need (Join-Path $CacheDir "python-$PyVer-embed-amd64.zip") "Embedded Python x64"
Need (Join-Path $CacheDir "python-$PyVer-embed-win32.zip") "Embedded Python x86"
$BuildPy = Find-BuildPython
Write-Host "Build Python: $BuildPy"
$git = (& git -C $Repo rev-parse --short HEAD 2>$null)
$dirty = [bool](& git -C $Repo status --porcelain 2>$null)

$Cert = $null
if ($CertThumbprint) {
    $Cert = Get-ChildItem Cert:\CurrentUser\My, Cert:\LocalMachine\My -CodeSigningCert |
        Where-Object { $_.Thumbprint -eq $CertThumbprint } | Select-Object -First 1
    if (-not $Cert) { throw "Code-signing certificate $CertThumbprint not found in the certificate store." }
} elseif ($env:ZIRP_SIGN_PFX) {
    $Cert = Get-PfxCertificate -FilePath $env:ZIRP_SIGN_PFX
}
$Signing = [bool]$Cert -or [bool]$env:ZIRP_SIGN_PFX
if (-not $Signing -and -not $AllowUnsigned) { throw "No signing certificate supplied." }

# ---------------------------------------------------------------------------- stage
Step "Staging release $Version"
if (Test-Path $Work) { Remove-Item $Work -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Stage, $BinStage, $OutDir | Out-Null

Copy-Tree (Join-Path $Repo "app") (Join-Path $Stage "app")
Remove-Item (Join-Path $Stage "app\mock_services") -Recurse -Force -ErrorAction SilentlyContinue  # test-only payment mock
$tools = Join-Path $Stage "tools"
New-Item -ItemType Directory -Force -Path (Join-Path $tools "hvx_sdk_host") | Out-Null
foreach ($f in @("__init__.py", "startup_check.py", "boot_health_check.py", "field_acceptance_test.py",
                 "field_realtime_report.py", "camera_lab.py", "camera_lab_replay.py", "soak_monitor.py",
                 "latency_report.py", "latency_capture.py")) {
    $src = Join-Path $Repo "tools\$f"
    if (Test-Path $src) { Copy-Item $src $tools }
}
foreach ($f in @("hvx_host.py", "hvx_sdk.py", "check_runtime.py", "hvx_bindings.json")) {
    Copy-Item (Join-Path $Repo "tools\hvx_sdk_host\$f") (Join-Path $tools "hvx_sdk_host")
}
Copy-Tree (Join-Path $Repo "tools\hvx_sdk_host\hvx_sdk_parts") (Join-Path $tools "hvx_sdk_host\hvx_sdk_parts")
Copy-Tree (Join-Path $ThirdPartyDir "models") (Join-Path $Stage "models")
Copy-Tree (Join-Path $ThirdPartyDir "vendor") (Join-Path $Stage "vendor")
Copy-Tree (Join-Path $Repo "packaging\licenses") (Join-Path $Stage "licenses")   # third-party licence texts
Set-Content -Path (Join-Path $Stage "VERSION") -Value $Version -Encoding ASCII -NoNewline

Step "Verifying the camera SDK against its manifest"
$manifest = Join-Path $Stage "vendor\QY-SDK-MANIFEST.txt"
Need $manifest "QY SDK manifest"
foreach ($line in Get-Content $manifest) {
    if ($line -match '^(REQUIRED|OPTIONAL) (\S+\.(dll|exe|ocx)) SHA256 ([0-9a-f]{64})$') {
        $name = $Matches[2]; $want = $Matches[4]
        $path = @(Get-ChildItem (Join-Path $Stage "vendor") -Recurse -Filter $name | Select-Object -First 1)
        if (-not $path) {
            if ($Matches[1] -eq "REQUIRED" -and $name -notlike "vc_redist*") { throw "SDK file missing: $name" }
            continue
        }
        $have = (Get-FileHash $path[0].FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($have -ne $want) { throw "SDK file $name does not match its manifest (mixed SDK generations break loading)." }
    }
}
Write-Host "Camera SDK files match the manifest."

Step "Embedded Python 3.11 (64-bit) with packages"
$py64 = Join-Path $Stage "python64"
Expand-Archive -LiteralPath (Join-Path $CacheDir "python-$PyVer-embed-amd64.zip") -DestinationPath $py64 -Force
Set-Content -Path (Join-Path $py64 "python311._pth") -Value "python311.zip`r`n.`r`n..`r`nLib\site-packages`r`nimport site`r`n" -Encoding ASCII -NoNewline
$site64 = Join-Path $py64 "Lib\site-packages"
New-Item -ItemType Directory -Force -Path $site64 | Out-Null
# Newest wheel per distribution (old kits carried two versions of some packages).
$wheelDir = Join-Path $ThirdPartyDir "wheels"
$byDist = @{}
foreach ($w in Get-ChildItem $wheelDir -Filter *.whl) {
    $parts = $w.Name.Split("-", 3)
    $dist = $parts[0].ToLowerInvariant()
    if ($dist -in @("pip", "setuptools", "wheel")) { continue }   # never ship the installer toolchain
    $ver = $null; try { $ver = [version]($parts[1] -replace '[^0-9.].*$', '') } catch {}
    $prev = $byDist[$dist]
    if (-not $prev -or ($ver -and $prev.Version -and $ver -gt $prev.Version)) { $byDist[$dist] = @{ Path = $w.FullName; Version = $ver } }
}
$wheels = @($byDist.Values | ForEach-Object { $_.Path })
& $BuildPy -m pip install --disable-pip-version-check --no-index --no-deps --no-compile --target $site64 @wheels
if ($LASTEXITCODE -ne 0) { throw "Installing wheels into the staged runtime failed." }
Remove-Item (Join-Path $site64 "bin") -Recurse -Force -ErrorAction SilentlyContinue

Step "Embedded Python 3.11 (32-bit) for the camera SDK host"
$py32 = Join-Path $Stage "python32"
Expand-Archive -LiteralPath (Join-Path $CacheDir "python-$PyVer-embed-win32.zip") -DestinationPath $py32 -Force
Set-Content -Path (Join-Path $py32 "python311._pth") -Value "python311.zip`r`n.`r`n..\tools\hvx_sdk_host`r`nLib\site-packages`r`nimport site`r`n" -Encoding ASCII -NoNewline
$site32 = Join-Path $py32 "Lib\site-packages"
New-Item -ItemType Directory -Force -Path $site32 | Out-Null
$pillow32 = Get-ChildItem (Join-Path $ThirdPartyDir "wheels32") -Filter "pillow-*-win32.whl" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $pillow32) { throw "32-bit Pillow wheel missing from wheels32." }
$zip = Join-Path $Work "pillow32.zip"; Copy-Item $pillow32.FullName $zip
Expand-Archive -LiteralPath $zip -DestinationPath $site32 -Force; Remove-Item $zip

if (-not $IncludeSource) {
    # Like the classic parking systems: install compiled code, not the source.
    # Compiled with the staged runtime so the bytecode matches what loads it.
    # Compiled files cannot be text-scanned, so look for keys in the source first.
    $srcKeys = @(Get-ChildItem (Join-Path $Stage "app") -Recurse -File -Include *.py |
        Select-String -Pattern '-----BEGIN [A-Z ]*PRIVATE KEY-----', 'SMARTPARK_[A-Z_]*(SECRET|TOKEN|PASSWORD|API_KEY)\s*=\s*\S{6,}' -List)
    if ($srcKeys.Count) {
        $srcKeys | ForEach-Object { Write-Host "  text: $($_.Path):$($_.LineNumber)" -ForegroundColor Red }
        throw "Secret scan failed: the application source contains a key or credential."
    }
    Step "Compiling the application (no readable source in the installer)"
    $out = & (Join-Path $py64 "python.exe") (Join-Path $PSScriptRoot "compile_app.py") (Join-Path $Stage "app") 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Compiling the application failed:`n$($out | Out-String)" }
    Write-Host ($out | Select-Object -Last 1)
    $left = @(Get-ChildItem (Join-Path $Stage "app") -Recurse -Filter *.py |
        Where-Object { $_.FullName -notlike "*\app\migrations\alembic\*" })
    if ($left.Count) { throw "Source files left in the staged app: $($left.FullName -join ', ')" }
}

Step "Smoke test of the staged runtime"
$probe = @'
import sys, importlib
mods = ["fastapi", "uvicorn", "sqlalchemy", "alembic", "psycopg", "pydantic_settings", "numpy", "cv2",
        "onnxruntime", "PySide6.QtCore", "PySide6.QtWidgets", "fast_alpr", "argon2", "qrcode", "PIL"]
for m in mods:
    importlib.import_module(m)
import onnxruntime as ort
assert "CPUExecutionProvider" in ort.get_available_providers()
import app.api_main  # the whole Site Service imports
import app.desktop.launch
# Every split module (source or compiled parts) and the migration chain.
for m in ["app.site_service", "app.media_service", "app.recognition_worker", "app.services.media_gateway",
          "app.services.captures", "app.services.alpr", "app.services.simulation", "app.desktop.main",
          "app.desktop.setup", "app.release_tool", "app.cli"]:
    importlib.import_module(m)
from app.migrations.runner import head_revision
assert head_revision(), "Alembic migrations did not load"
print("ok", sys.version.split()[0], ort.__version__)
'@
$probeFile = Join-Path $Work "probe.py"; Set-Content $probeFile $probe -Encoding UTF8
$env:SMARTPARK_HOME = $Stage; $env:SMARTPARK_LATENCY_TRACE = "0"
Push-Location $Stage
try {
    $out = & (Join-Path $py64 "python.exe") $probeFile 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Staged runtime smoke test failed:`n$($out | Out-String)" }
    Write-Host ($out | Select-Object -Last 1)
    $out32 = & (Join-Path $py32 "python.exe") -c "import struct, PIL; print(struct.calcsize('P') * 8)" 2>&1
    if ("$out32".Trim() -ne "32") { throw "32-bit runtime check failed: $out32" }
} finally { Pop-Location; Remove-Item Env:\SMARTPARK_HOME -ErrorAction SilentlyContinue }

# ---------------------------------------------------------------------------- portal
if (-not $SkipPortal) {
    Step "Portal (Next.js standalone) with bundled Node"
    if (-not $NodeExe) { $cmd = Get-Command node.exe -ErrorAction SilentlyContinue; if ($cmd) { $NodeExe = $cmd.Source } }
    Need $NodeExe "node.exe (Node 20.9+ on the build machine)"
    $nodeVer = (& $NodeExe --version).TrimStart("v")
    if ([version]($nodeVer -replace '[^0-9.].*$', '') -lt [version]"20.9") { throw "Node $nodeVer is too old for the portal (need 20.9+)." }
    $portalSrc = Join-Path $Repo "portal"
    $dist = ".next-release"
    Push-Location $portalSrc
    try {
        if (-not (Test-Path "node_modules")) { & npm.cmd ci; if ($LASTEXITCODE -ne 0) { throw "npm ci failed" } }
        $env:ZIRP_PORTAL_DIST_DIR = $dist; $env:NEXT_TELEMETRY_DISABLED = "1"
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw "Portal build failed." }
    } finally { Pop-Location; Remove-Item Env:\ZIRP_PORTAL_DIST_DIR -ErrorAction SilentlyContinue }
    $standalone = Join-Path $portalSrc "$dist\standalone"
    $server = Get-ChildItem $standalone -Recurse -Filter server.js -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch '\\node_modules\\' } | Sort-Object { $_.FullName.Length } | Select-Object -First 1
    if (-not $server) { throw "Portal standalone server.js not found in $standalone." }
    $portalStage = Join-Path $Stage "portal"
    Copy-Tree $server.DirectoryName $portalStage
    Copy-Tree (Join-Path $portalSrc "$dist\static") (Join-Path $portalStage "$dist\static")
    if (Test-Path (Join-Path $portalSrc "public")) { Copy-Tree (Join-Path $portalSrc "public") (Join-Path $portalStage "public") }
    Get-ChildItem $portalStage -Recurse -Force -Filter ".env*" | Remove-Item -Force
    New-Item -ItemType Directory -Force -Path (Join-Path $Stage "vendor\node") | Out-Null
    Copy-Item $NodeExe (Join-Path $Stage "vendor\node\node.exe")
    Set-Content (Join-Path $Stage "vendor\node\PROVENANCE.txt") "Node.js $nodeVer (MIT) copied from $NodeExe at build time." -Encoding ASCII
}

# ---------------------------------------------------------------------------- secret scan
Step "Secret scan of the payload"
$bannedNames = @(".env", "zirp.env", "portal.env", ".env.local", "deployment.json", "kiosk_device.json",
                 "smartpark.db", "id_rsa", "id_ed25519")
$bannedExt = @(".pfx", ".p12", ".pem", ".key", ".sqlite", ".sqlite3", ".db", ".bin")
$hits = @(Get-ChildItem $Stage -Recurse -Force -File | Where-Object {
    ($bannedNames -contains $_.Name.ToLowerInvariant()) -or
    (($bannedExt -contains $_.Extension.ToLowerInvariant()) -and $_.FullName -notmatch '\\(site-packages|python64|python32|vendor\\ffmpeg|vendor\\mediamtx|models)\\') -or
    ($_.FullName -match '\\secrets\\' -and $_.Extension -notin @(".py", ".pyi", ".pyc") -and $_.FullName -notmatch '\\site-packages\\')
})
$keyText = @(Get-ChildItem (Join-Path $Stage "app"), (Join-Path $Stage "tools"), (Join-Path $Stage "portal") -Recurse -File -Include *.py, *.js, *.json, *.txt, *.ini, *.toml -ErrorAction SilentlyContinue |
    Select-String -Pattern '-----BEGIN [A-Z ]*PRIVATE KEY-----', 'SMARTPARK_[A-Z_]*(SECRET|TOKEN|PASSWORD|API_KEY)\s*=\s*\S{6,}' -List)
if ($hits.Count -or $keyText.Count) {
    $hits | ForEach-Object { Write-Host "  file: $($_.FullName)" -ForegroundColor Red }
    $keyText | ForEach-Object { Write-Host "  text: $($_.Path):$($_.LineNumber)" -ForegroundColor Red }
    throw "Secret scan failed: the payload must not contain settings, keys, databases or credentials."
}
Write-Host "No secrets found."

# ---------------------------------------------------------------------------- tools + build info
Copy-Item (Join-Path $PSScriptRoot "bin\*") $BinStage
$info = [ordered]@{
    product = "Zirp"; version = $Version; git_commit = $git; git_dirty = $dirty
    built_utc = (Get-Date).ToUniversalTime().ToString("o"); build_host = $env:COMPUTERNAME
    python = $PyVer; node = $(if ($SkipPortal) { $null } else { $nodeVer }); signed = $Signing
}
$info | ConvertTo-Json | Set-Content (Join-Path $Stage "BUILD-INFO.json") -Encoding UTF8
if ($dirty) { Write-Warning "Building from a working tree with uncommitted changes (recorded in BUILD-INFO.json)." }

if ($Signing) {
    Step "Signing PowerShell tools"
    foreach ($ps in Get-ChildItem $BinStage -Filter *.ps1) {
        $sig = Set-AuthenticodeSignature -FilePath $ps.FullName -Certificate $Cert -TimestampServer $TimestampUrl -HashAlgorithm SHA256
        if ($sig.Status -ne "Valid") { throw "Signing $($ps.Name) failed: $($sig.StatusMessage)" }
    }
}

if ($StageOnly) {
    Write-Host ""; Write-Host "Staged (not compiled): $Stage" -ForegroundColor Green
    return
}

# ---------------------------------------------------------------------------- compile
Step "Compiling installer with Inno Setup"
$isccExe = Find-Iscc
$isccArgs = @("/Q", "/DAppVersion=$Version", "/DAppVersionNumeric=$Numeric", "/DStageDir=$Stage",
              "/DBinDir=$BinStage", "/DOutputDir=$OutDir")
if ($Signing) {
    $signtool = Find-SignTool
    $who = if ($CertThumbprint) { "/sha1 $CertThumbprint" } else { "/f `"$env:ZIRP_SIGN_PFX`" /p `"$env:ZIRP_SIGN_PFX_PASSWORD`"" }
    $isccArgs += "/Szirpsign=`"$signtool`" sign /fd sha256 /tr $TimestampUrl /td sha256 $who `$f"
    $isccArgs += "/DSignTool=zirpsign"
}
& $isccExe @isccArgs (Join-Path $PSScriptRoot "Zirp.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed ($LASTEXITCODE)." }
$setup = Join-Path $OutDir "Zirp-Setup-$Version.exe"
$hash = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content "$setup.sha256" "$hash  Zirp-Setup-$Version.exe" -Encoding ASCII
Copy-Item (Join-Path $Stage "BUILD-INFO.json") (Join-Path $OutDir "Zirp-Setup-$Version.BUILD-INFO.json")
if ($Signing) {
    $sig = Get-AuthenticodeSignature $setup
    if ($sig.Status -ne "Valid") { throw "Installer signature is not valid: $($sig.StatusMessage)" }
}
Write-Host ""
Write-Host "Built: $setup" -ForegroundColor Green
Write-Host "SHA-256: $hash"
Write-Host "Signed: $Signing"
