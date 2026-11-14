#requires -Version 5.1
<#
.SYNOPSIS
    Run SmartPark as real Windows services (default when the kit has NSSM).

.DESCRIPTION
    After a power cut the PC must bring parking back with nobody logged in.
    Scheduled tasks with an AtLogOn trigger cannot do that. This script
    registers Windows services through the bundled NSSM (vendor\nssm\nssm.exe):

      SmartParkSiteService        python64 -m app.site_service
      SmartParkMediaService       python64 -m app.media_service   (owns MediaMTX)
      SmartParkRecognitionWorker  python64 -m app.recognition_worker
      SmartParkHvxHost            python32 tools\hvx_sdk_host\hvx_host.py  (only with -HvxHostAsService)

    Each service:
      * starts automatically at boot (no user logon), as LocalSystem;
      * is restarted by NSSM whenever the process exits, with NSSM's throttle
        backing off a process that keeps dying, and SCM failure actions as a
        second line if NSSM itself fails;
      * writes stdout/stderr to %ProgramData%\SmartParkEdge\logs\services,
        rotated online at 10 MB;
      * starts in dependency order: local PostgreSQL (if present) -> Site
        Service -> Media Service -> Recognition Worker.

    The 32-bit HVX SDK host uses a hidden message-pumped window. Whether the
    vendor SDK works in the non-interactive service session (Session 0) must be
    proven on a site PC first (Test-HvxHostAsService.ps1). Until then it stays a
    logon scheduled task; see docs/WINDOWS-SERVICES.md for the auto-logon
    fallback that keeps it running after a reboot.

    Scheduled-task owners of the same processes are removed first so two
    supervisors never compete for ports or instance locks.
#>
[CmdletBinding()]
param(
    [string]$InstallDir = "",
    [switch]$RegisterOnly,
    [switch]$HvxHostAsService,
    [switch]$FallbackToScheduledTasks
)

$ErrorActionPreference = "Stop"

if (-not $InstallDir) {
    $InstallDir = [Environment]::GetEnvironmentVariable("SMARTPARK_HOME", "User")
    if (-not $InstallDir) {
        $InstallDir = Join-Path $env:LOCALAPPDATA "Programs\SmartPark Edge"
    }
}

$Nssm = Join-Path $InstallDir "vendor\nssm\nssm.exe"
$TaskScript = Join-Path $PSScriptRoot "Install-SmartParkServices.ps1"
$Py64 = Join-Path $InstallDir "python64\python.exe"
$Py32 = Join-Path $InstallDir "python32\python.exe"
$HostPy = Join-Path $InstallDir "tools\hvx_sdk_host\hvx_host.py"
$MediaMtx = Join-Path $InstallDir "vendor\mediamtx\mediamtx.exe"
$DataDir = Join-Path $env:ProgramData "SmartParkEdge"
$ServiceLogDir = Join-Path $DataDir "logs\services"

$ServiceNames = @("SmartParkRecognitionWorker", "SmartParkMediaService", "SmartParkSiteService", "SmartParkHvxHost")
$TaskNames = @("SmartPark Site Service", "SmartPark Recognition Worker", "SmartPark HVX Host", "SmartPark Media Service")

if (-not (Test-Path $Nssm)) {
    Write-Host "nssm.exe is not in this kit; services cannot be registered."
    if ($FallbackToScheduledTasks -and (Test-Path $TaskScript)) {
        & $TaskScript -InstallDir $InstallDir -ScheduledTasksOnly -RegisterOnly:$RegisterOnly
    }
    return
}
if (-not (Test-Path $Py64)) {
    throw "Install SmartPark Edge first. Missing $Py64"
}
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run Install-SmartParkWinService.ps1 from an elevated PowerShell window."
}

function Invoke-Nssm {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $output = & $Nssm @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ("nssm {0} failed ({1}): {2}" -f ($Arguments -join " "), $LASTEXITCODE, ($output -join " "))
    }
}

function Remove-SmartParkService {
    param([string]$Name)
    if (Get-Service -Name $Name -ErrorAction SilentlyContinue) {
        & $Nssm stop $Name 2>$null | Out-Null
        & $Nssm remove $Name confirm 2>$null | Out-Null
    }
}

function Register-SmartParkService {
    param(
        [string]$Name,
        [string]$DisplayName,
        [string]$Exe,
        [string]$Arguments,
        [string]$WorkDir,
        [string[]]$DependsOn = @()
    )
    Remove-SmartParkService -Name $Name
    Invoke-Nssm install $Name $Exe $Arguments
    Invoke-Nssm set $Name DisplayName $DisplayName
    Invoke-Nssm set $Name Description "SmartPark Edge parking runtime. Restarts automatically; logs in $ServiceLogDir."
    Invoke-Nssm set $Name AppDirectory $WorkDir
    Invoke-Nssm set $Name ObjectName LocalSystem
    Invoke-Nssm set $Name Start SERVICE_AUTO_START
    # Restart whenever the process exits. A process that dies within
    # AppThrottle ms is restarted after an increasing delay (NSSM backoff).
    Invoke-Nssm set $Name AppExit Default Restart
    Invoke-Nssm set $Name AppRestartDelay 2000
    Invoke-Nssm set $Name AppThrottle 15000
    # Give Python time to close sockets, MediaMTX and SDK sessions cleanly.
    Invoke-Nssm set $Name AppStopMethodConsole 15000
    Invoke-Nssm set $Name AppStopMethodWindow 5000
    Invoke-Nssm set $Name AppStopMethodThreads 5000
    $log = Join-Path $ServiceLogDir "$Name.log"
    Invoke-Nssm set $Name AppStdout $log
    Invoke-Nssm set $Name AppStderr $log
    Invoke-Nssm set $Name AppStdoutCreationDisposition 4
    Invoke-Nssm set $Name AppStderrCreationDisposition 4
    Invoke-Nssm set $Name AppRotateFiles 1
    Invoke-Nssm set $Name AppRotateOnline 1
    Invoke-Nssm set $Name AppRotateBytes 10485760
    $profile = [Environment]::GetEnvironmentVariable("SMARTPARK_DEPLOYMENT_PROFILE", "User")
    if (-not $profile) { $profile = "PRODUCTION" }
    $nodeRole = [Environment]::GetEnvironmentVariable("SMARTPARK_NODE_ROLE", "User")
    if (-not $nodeRole) { $nodeRole = "SERVER" }
    $environment = @(
        "SMARTPARK_DEPLOYMENT_PROFILE=$profile",
        "SMARTPARK_NODE_ROLE=$nodeRole",
        "SMARTPARK_HOME=$InstallDir",
        "SMARTPARK_LOG_DIR=$DataDir\logs",
        "PYTHONPATH=$InstallDir",
        "PYTHONUNBUFFERED=1",
        "SMARTPARK_HVX_VENDOR_DIR=$InstallDir\vendor"
    )
    if (Test-Path $MediaMtx) { $environment += "SMARTPARK_MEDIAMTX_BIN=$MediaMtx" }
    Invoke-Nssm set $Name AppEnvironmentExtra @environment
    if ($DependsOn.Count -gt 0) {
        Invoke-Nssm set $Name DependOnService @DependsOn
    }
    # Second line of defence if nssm.exe itself exits: SCM restarts the
    # service after 5 s, 15 s, then every 60 s; the counter resets daily.
    & sc.exe failure $Name reset= 86400 actions= restart/5000/restart/15000/restart/60000 | Out-Null
    & sc.exe failureflag $Name 1 | Out-Null
    # Let interactive users (the desktop's repair button) query, start and
    # stop these services without administrator rights. Nothing else changes.
    & sc.exe sdset $Name "D:(A;;CCLCSWRPWPDTLOCRRC;;;SY)(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)(A;;CCLCSWRPWPLOCRRC;;;IU)(A;;CCLCSWLOCRRC;;;SU)" | Out-Null
}

Write-Host "Removing scheduled-task owners before registering Windows services..."
foreach ($task in $TaskNames) {
    Stop-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue
}
foreach ($name in $ServiceNames) {
    Remove-SmartParkService -Name $name
}
Start-Sleep -Seconds 1
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $cmd = [string]$_.CommandLine
    $cmd -and (
        $cmd -like "*hvx_host.py*" -or
        $cmd -like "*app.site_service*" -or
        $cmd -like "*app.media_service*" -or
        $cmd -like "*app.recognition_worker*" -or
        $cmd -like "*mediamtx.exe*"
    ) -and $cmd -like "*$InstallDir*"
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Milliseconds 800

New-Item -ItemType Directory -Force -Path $ServiceLogDir | Out-Null

# A Site Server with a local PostgreSQL must not start before the database.
$siteDepends = @()
$postgres = Get-Service -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "postgresql*" } | Select-Object -First 1
if ($postgres) {
    $siteDepends += $postgres.Name
    Write-Host "Site Service will start after local PostgreSQL service '$($postgres.Name)'."
}

Write-Host "Registering Windows services via NSSM..."
Register-SmartParkService -Name "SmartParkSiteService" -DisplayName "SmartPark Site Service" `
    -Exe $Py64 -Arguments "-m app.site_service" -WorkDir $InstallDir -DependsOn $siteDepends
$workerDepends = @("SmartParkSiteService")
if (Test-Path $MediaMtx) {
    Register-SmartParkService -Name "SmartParkMediaService" -DisplayName "SmartPark Media Service (MediaMTX)" `
        -Exe $Py64 -Arguments "-m app.media_service" -WorkDir $InstallDir -DependsOn @("SmartParkSiteService")
    $workerDepends = @("SmartParkMediaService")
} else {
    Write-Host "Media Service skipped: vendor\mediamtx\mediamtx.exe not in this kit."
}
Register-SmartParkService -Name "SmartParkRecognitionWorker" -DisplayName "SmartPark Recognition Worker" `
    -Exe $Py64 -Arguments "-m app.recognition_worker" -WorkDir $InstallDir -DependsOn $workerDepends

$hvxMode = "none"
if (Test-Path $Py32) {
    if ($HvxHostAsService) {
        Register-SmartParkService -Name "SmartParkHvxHost" -DisplayName "SmartPark HVX SDK Host (32-bit)" `
            -Exe $Py32 -Arguments "`"$HostPy`"" -WorkDir (Join-Path $InstallDir "tools\hvx_sdk_host")
        $hvxMode = "service"
    } elseif (Test-Path $TaskScript) {
        # Not yet proven in Session 0: keep the vendor SDK in the interactive
        # session until Test-HvxHostAsService.ps1 passes on site hardware.
        & $TaskScript -InstallDir $InstallDir -ScheduledTasksOnly -Only "SmartPark HVX Host" -RegisterOnly:$RegisterOnly
        $hvxMode = "logon task"
    }
} else {
    Write-Host "HVX host skipped: 32-bit Python is not in this kit."
}

function Register-SmartParkFirewall {
    # Same LAN-only rules as the scheduled-task installer.
    $rules = @(@{ Name = "SmartPark Site API"; Protocol = "TCP"; Port = 8760 })
    if (Test-Path $MediaMtx) {
        $rules += @(
            @{ Name = "SmartPark MediaMTX WebRTC"; Protocol = "TCP"; Port = 8889 },
            @{ Name = "SmartPark MediaMTX ICE"; Protocol = "UDP"; Port = 8189 },
            @{ Name = "SmartPark MediaMTX ICE TCP"; Protocol = "TCP"; Port = 8189 }
        )
    }
    foreach ($rule in $rules) {
        try {
            if (-not @(Get-NetFirewallRule -DisplayName $rule.Name -ErrorAction SilentlyContinue).Count) {
                New-NetFirewallRule -DisplayName $rule.Name -Direction Inbound -Action Allow -Protocol $rule.Protocol `
                    -LocalPort $rule.Port -Profile Any -RemoteAddress LocalSubnet | Out-Null
            }
        } catch {
            Write-Warning ("Could not create firewall rule {0}: {1}" -f $rule.Name, $_.Exception.Message)
        }
    }
}
Register-SmartParkFirewall

if ($RegisterOnly) {
    Write-Host "Services registered; first start is deferred until deployment setup completes."
    return
}
foreach ($name in @("SmartParkHvxHost", "SmartParkSiteService", "SmartParkMediaService", "SmartParkRecognitionWorker")) {
    if (Get-Service -Name $name -ErrorAction SilentlyContinue) {
        Start-Service -Name $name -ErrorAction Continue
    }
}
Write-Host "SmartPark services registered and started (HVX host: $hvxMode). Logs: $ServiceLogDir"
if ($hvxMode -eq "logon task") {
    Write-Host "HVX cameras need a signed-in session until Test-HvxHostAsService.ps1 passes; see docs\WINDOWS-SERVICES.md."
}
