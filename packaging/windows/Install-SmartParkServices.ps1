#requires -Version 5.1
<#
.SYNOPSIS
    Register SmartPark background processes so parking does not need the Desktop UI.
    The main installer runs this automatically. This scheduled-task path stays
    the supported default until Install-SmartParkWinService.ps1 is verified on
    site hardware — do not remove this file in the same change as SCM.
#>
[CmdletBinding()]
param(
    [string]$InstallDir = "",
    [switch]$RegisterOnly
)

$ErrorActionPreference = "Stop"

if (-not $InstallDir) {
    $InstallDir = [Environment]::GetEnvironmentVariable("SMARTPARK_HOME", "User")
    if (-not $InstallDir) {
        $InstallDir = Join-Path $env:LOCALAPPDATA "Programs\SmartPark Edge"
    }
}
$Py64 = Join-Path $InstallDir "python64\python.exe"
$Py32 = Join-Path $InstallDir "python32\python.exe"
$HostPy = Join-Path $InstallDir "tools\hvx_sdk_host\hvx_host.py"
$MediaMtx = Join-Path $InstallDir "vendor\mediamtx\mediamtx.exe"
$DeploymentPath = Join-Path $env:ProgramData "SmartParkEdge\deployment.json"
if (-not (Test-Path $Py64)) {
    throw "Install SmartPark Edge first. Missing $Py64"
}

# Operator workstations are API clients only.  This guard also makes an
# upgraded install safe when an old server-task registration is still present.
if (Test-Path $DeploymentPath) {
    try {
        $deployment = Get-Content -LiteralPath $DeploymentPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ([string]$deployment.role -eq "OPERATOR_CLIENT") {
            Write-Host "Operator Workstation selected: removing local SmartPark service tasks."
            foreach ($task in @(
                "SmartPark Site Service",
                "SmartPark Recognition Worker",
                "SmartPark HVX Host",
                "SmartPark Media Service"
            )) {
                Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue
            }
            exit 0
        }
        $configured = [bool]$deployment.configured -and (
            -not $deployment.PSObject.Properties['state'] -or
            [string]$deployment.state -eq "CONFIGURED"
        )
        if (-not $configured) {
            Write-Host "Deployment setup is incomplete: registering tasks without starting them."
            $RegisterOnly = $true
        }
    } catch {
        throw "The deployment configuration is invalid: $($_.Exception.Message)"
    }
} else {
    Write-Host "No deployment configuration found: registering tasks without starting them."
    $RegisterOnly = $true
}
$TaskUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name

# Scheduled tasks run as the interactive technician account, while the
# installer may have created ProgramData files from an elevated process.
# Grant that exact account Modify access so services can rotate logs, write
# health state and update the model/cache directories after installation.
$DataDir = Join-Path $env:ProgramData "SmartParkEdge"
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
$dataGrant = "{0}:(OI)(CI)M" -f $TaskUser
& icacls.exe $DataDir /grant $dataGrant /T /C /Q | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Could not grant $TaskUser Modify access to $DataDir. Services may not be able to rotate logs."
}

function Write-SmartParkLauncher {
    param(
        [string]$BatName,
        [string]$PythonExe,
        [string]$Arguments,
        [switch]$WaitForSite
    )
    $bat = Join-Path $InstallDir $BatName
    $mtxLine = ""
    if (Test-Path $MediaMtx) {
        $mtxLine = "set `"SMARTPARK_MEDIAMTX_BIN=$MediaMtx`""
    }
    $waitForSiteLines = ""
    if ($WaitForSite) {
        # AtLogOn tasks are scheduled concurrently. Dependent workers must
        # wait for the Site Service to finish migrations and expose HTTP 200;
        # otherwise they can open the same SQLite file before tables exist.
        $waitForSiteLines = @'
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(180); do { try { $r=Invoke-WebRequest -Uri 'http://127.0.0.1:8760/health/live' -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop; if ([int]$r.StatusCode -eq 200) { exit 0 } } catch {}; Start-Sleep -Seconds 1 } while ((Get-Date) -lt $deadline); exit 1"
if errorlevel 1 exit /b 1
'@
    }
    @"
@echo off
setlocal
cd /d "$InstallDir"
set "SMARTPARK_HOME=$InstallDir"
set "PYTHONPATH=%SMARTPARK_HOME%"
set "SMARTPARK_HVX_VENDOR_DIR=%SMARTPARK_HOME%\vendor"
if not defined SMARTPARK_DEPLOYMENT_PROFILE set "SMARTPARK_DEPLOYMENT_PROFILE=PRODUCTION"
$mtxLine
set "PATH=%SMARTPARK_HOME%\python64;%SMARTPARK_HOME%\python64\Scripts;%SMARTPARK_HOME%\vendor;%PATH%"
$waitForSiteLines
"$PythonExe" $Arguments
"@ | Set-Content -Path $bat -Encoding ASCII
    return $bat
}

function Register-SmartParkTask {
    param(
        [string]$Name,
        [string]$Launcher,
        [string]$WorkingDirectory
    )
    Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue
    # Quote the launcher. "SmartPark Edge" has a space; an unquoted set-chain
    # makes Start-ScheduledTask fail and the installer never opens the app.
    $action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument ("/c `"{0}`"" -f $Launcher) -WorkingDirectory $WorkingDirectory
    $triggerLogon = New-ScheduledTaskTrigger -AtLogOn -User $taskUser
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
    try {
        $principal = New-ScheduledTaskPrincipal -UserId $taskUser -LogonType Interactive -RunLevel Limited
        Register-ScheduledTask -TaskName $Name -Action $action -Trigger $triggerLogon -Settings $settings -Principal $principal -Force | Out-Null
    } catch {
        Register-ScheduledTask -TaskName $Name -Action $action -Trigger $triggerLogon -Settings $settings -Force | Out-Null
    }
}

function Start-SmartParkTask {
    param([string]$Name)
    try {
        Start-ScheduledTask -TaskName $Name -ErrorAction Stop
    } catch {
        throw "registered, but Windows did not start '$Name': $($_.Exception.Message)"
    }
}

function Register-SmartParkFirewall {
    # Only the Site Server needs inbound rules. Keep PostgreSQL, HVX, RTSP and
    # MediaMTX's control/metrics ports local; operators need the API and the
    # WebRTC signaling/ICE ports only.
    $rules = @(
        @{ Name = "SmartPark Site API"; Protocol = "TCP"; Port = 8760 }
    )
    if (Test-Path $MediaMtx) {
        $rules += @(
            @{ Name = "SmartPark MediaMTX WebRTC"; Protocol = "TCP"; Port = 8889 },
            @{ Name = "SmartPark MediaMTX ICE"; Protocol = "UDP"; Port = 8189 },
            @{ Name = "SmartPark MediaMTX ICE TCP"; Protocol = "TCP"; Port = 8189 }
        )
    }
    foreach ($rule in $rules) {
        if (-not (Get-NetFirewallRule -DisplayName $rule.Name -ErrorAction SilentlyContinue)) {
            try {
                New-NetFirewallRule -DisplayName $rule.Name -Direction Inbound -Action Allow -Protocol $rule.Protocol -LocalPort $rule.Port -Profile Private -RemoteAddress LocalSubnet | Out-Null
                Write-Host ("Firewall: opened {0}/{1} to LocalSubnet on Private networks." -f $rule.Protocol, $rule.Port)
            } catch {
                Write-Warning ("Could not create firewall rule {0}: {1}" -f $rule.Name, $_.Exception.Message)
            }
        }
    }
}

function Wait-SmartParkHttp {
    param(
        [string]$Url,
        [string]$Label,
        [int]$TimeoutSeconds = 30
    )
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $lastStatus = ""
    $lastError = ""
    do {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            $lastStatus = [string]$response.StatusCode
            # Readiness endpoints must be owned by the expected service. A
            # 3xx/4xx response can come from an unrelated process already
            # holding the port and must never let installation continue.
            if ([int]$response.StatusCode -eq 200) {
                return
            }
        } catch {
            $lastError = $_.Exception.Message
            # The process may still be starting. Keep polling until the bounded deadline.
        }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    $logDir = Join-Path $env:ProgramData "SmartParkEdge\logs"
    $details = @()
    foreach ($name in @("site-service.log", "site-service-launch.log", "launch.log")) {
        $path = Join-Path $logDir $name
        if (Test-Path $path) {
            $tail = @(Get-Content -LiteralPath $path -Tail 8 -ErrorAction SilentlyContinue)
            if ($tail.Count -gt 0) {
                $details += "${name}: " + (($tail -join " | ").Substring(0, [Math]::Min(900, ($tail -join " | ").Length)))
            }
        }
    }
    $suffix = if ($details.Count) { "`n" + ($details -join "`n") } else { "" }
    $portMatch = [regex]::Match($Url, ':(\d+)(?:/|$)')
    $owner = ""
    if ($portMatch.Success) {
        $port = [int]$portMatch.Groups[1].Value
        $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
        foreach ($listener in $listeners) {
            $process = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
            $owner += " PID $($listener.OwningProcess)=$($process.ProcessName)"
        }
    }
    $diagnostic = "Last HTTP status: $lastStatus. Last error: $lastError. Listening process:$owner"
    throw "$Label did not return HTTP 200 from $Url within $TimeoutSeconds seconds. $diagnostic Check $logDir.$suffix"
}

$siteBat = Write-SmartParkLauncher -BatName "run-site-service.bat" -PythonExe $Py64 -Arguments "-m app.site_service"
$recognitionBat = Write-SmartParkLauncher -BatName "run-recognition-worker.bat" -PythonExe $Py64 -Arguments "-m app.recognition_worker" -WaitForSite
$hostBat = ""
if (Test-Path $Py32) {
    $hostBat = Write-SmartParkLauncher -BatName "run-hvx-host.bat" -PythonExe $Py32 -Arguments "`"$HostPy`""
}
$mediaBat = ""
if (Test-Path $MediaMtx) {
$mediaBat = Write-SmartParkLauncher -BatName "run-media-service.bat" -PythonExe $Py64 -Arguments "-m app.media_service" -WaitForSite
}

Write-Host "Registering SmartPark background tasks..."
$failed = @()
$registered = @()
try {
    Register-SmartParkTask -Name "SmartPark Site Service" -Launcher $siteBat -WorkingDirectory $InstallDir
    $registered += "SmartPark Site Service"
} catch {
    $failed += "Site Service: $_"
}
try {
    Register-SmartParkTask -Name "SmartPark Recognition Worker" -Launcher $recognitionBat -WorkingDirectory $InstallDir
    $registered += "SmartPark Recognition Worker"
} catch {
    $failed += "Recognition Worker: $_"
}
if ($hostBat) {
    try {
        Register-SmartParkTask -Name "SmartPark HVX Host" -Launcher $hostBat -WorkingDirectory (Join-Path $InstallDir "tools\hvx_sdk_host")
        $registered += "SmartPark HVX Host"
    } catch {
        $failed += "HVX host: $_"
    }
} else {
    Write-Host "HVX host skipped: 32-bit Python is not in this kit."
}
if ($mediaBat) {
    try {
        Register-SmartParkTask -Name "SmartPark Media Service" -Launcher $mediaBat -WorkingDirectory $InstallDir
        $registered += "SmartPark Media Service"
    } catch {
        $failed += "Media Service: $_"
    }
} else {
    Write-Host "Media Service skipped: vendor\mediamtx\mediamtx.exe not in this kit."
}
if ($failed.Count -gt 0) {
    throw ($failed -join "; ")
}

# A first-run installer registers the tasks before the role is selected, but
# deliberately leaves them stopped. The native wizard starts the current
# server session; the AtLogOn trigger takes over after the next sign-in.
if ($RegisterOnly) {
    Write-Host "Background tasks registered; first start is deferred until deployment setup completes."
    exit 0
}

Register-SmartParkFirewall

# Start in dependency order. The tasks remain registered with an AtLogOn
# trigger, so the same sequence is repeated automatically after the next
# Windows sign-in. Site Service is the dependency root: it must complete
# schema migration and return HTTP 200 before workers inspect the database.
foreach ($name in @("SmartPark Site Service")) {
    if ($registered -contains $name) {
        Write-Host "Starting $name..."
        Start-SmartParkTask -Name $name
    }
}

if ($registered -contains "SmartPark Site Service") {
    # First boot may run migrations and warm the offline FastALPR models on a
    # slower Windows CPU.  Match the desktop supervisor's bounded startup
    # window so a healthy service is not reported as failed during upgrades.
    Wait-SmartParkHttp -Url "http://127.0.0.1:8760/health/live" -Label "Site Service" -TimeoutSeconds 120
}

foreach ($name in @("SmartPark HVX Host", "SmartPark Media Service", "SmartPark Recognition Worker")) {
    if ($registered -contains $name) {
        Write-Host "Starting $name..."
        Start-SmartParkTask -Name $name
    }
}

if ($registered -contains "SmartPark HVX Host") {
    try {
        Wait-SmartParkHttp -Url "http://127.0.0.1:8765/info" -Label "HVX SDK host" -TimeoutSeconds 30
    } catch {
        # HVX/NetSDK is conditional hardware. A Windows site using RTSP,
        # ONVIF, Dahua or Hikvision cameras must still complete installation
        # when the optional 32-bit SDK host is unavailable. The scheduled
        # task remains registered so a technician can repair the vendor
        # runtime and restart it later; the Site Service and local recognition
        # pipeline are independent of this host.
        Write-Warning "HVX SDK host is not ready: $_"
        Write-Warning "Installation will continue. HVX camera features remain unavailable until the 32-bit host is repaired."
    }
}

Write-Host ""
Write-Host "Background tasks:"
Write-Host "  SmartPark Site Service   (API + camera events, port 8760)"
Write-Host "  SmartPark Recognition Worker (warm models and local MediaMTX decoders)"
Write-Host "  SmartPark HVX Host       (32-bit NetSDK, port 8765)"
if (Test-Path $MediaMtx) {
    Write-Host "  SmartPark Media Service  (MediaMTX realtime gateway when enabled by effective site flags)"
}
Write-Host "Desktop is only a client. Parking continues if the UI is closed."
Write-Host "Fresh installs prefer MediaMTX/WebRTC when the bundled binary is available; upgraded sites keep their stored rollout flags."
Write-Host "To promote an upgraded site explicitly, run Enable-MediaMTX.ps1 -LiveView."
Write-Host "Recovery: Windows restarts each task up to 3 times, 1 minute apart."
Write-Host "Automatic startup: tasks run for $taskUser at Windows logon; no manual Start-SmartPark.bat is required."
