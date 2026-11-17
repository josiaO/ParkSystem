#requires -Version 5.1
<#
.SYNOPSIS
    Start the Zirp portal (and, for test sites, the mock ClickPesa) at boot.
.DESCRIPTION
    Registers Windows services with the same NSSM settings as the other
    SmartPark services:
      SmartParkPortal        Next.js public pay page + back office (port 3000)
      SmartParkMockPayments  mock ClickPesa for test sites (port 9100);
                             never install it where real payments are taken
    Both start automatically, restart on failure, log to
    %ProgramData%\SmartParkEdge\logs\services, and can be started/stopped by
    signed-in users without admin rights (like the other SmartPark services).
    The portal must be built first (start-portal.bat once, or npm run build).
.EXAMPLE
    .\Register-PortalServices.ps1 -PortalDir C:\SmartParkEdge\portal
    .\Register-PortalServices.ps1 -PortalDir C:\SmartParkEdge\portal -NoMock
    .\Register-PortalServices.ps1 -Remove
#>
[CmdletBinding()]
param(
    [string]$InstallDir = "",
    [string]$PortalDir = "",
    [string]$NodeExe = "",
    [int]$Port = 3000,
    [int]$MockPort = 9100,
    [switch]$NoMock,
    [switch]$Remove
)
$ErrorActionPreference = "Stop"
if (-not $InstallDir) { $InstallDir = $PSScriptRoot }
if (-not $PortalDir) { $PortalDir = Join-Path $InstallDir "portal" }
$Nssm = Join-Path $InstallDir "vendor\nssm\nssm.exe"
$Py64 = Join-Path $InstallDir "python64\python.exe"
$DataDir = Join-Path $env:ProgramData "SmartParkEdge"
$LogDir = Join-Path $DataDir "logs\services"
$Portal = "SmartParkPortal"
$Mock = "SmartParkMockPayments"

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this from an elevated PowerShell window."
}
if (-not (Test-Path $Nssm)) { throw "Missing $Nssm" }

function Invoke-Nssm {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $output = & $Nssm @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw ("nssm {0} failed ({1}): {2}" -f ($Arguments -join " "), $LASTEXITCODE, ($output -join " ")) }
}

function Remove-SmartParkService([string]$Name) {
    if (Get-Service -Name $Name -ErrorAction SilentlyContinue) {
        & $Nssm stop $Name 2>$null | Out-Null
        & $Nssm remove $Name confirm 2>$null | Out-Null
        Start-Sleep -Seconds 2
    }
}

function Set-CommonOptions([string]$Name, [string]$Directory) {
    Invoke-Nssm set $Name AppDirectory $Directory
    Invoke-Nssm set $Name ObjectName LocalSystem
    Invoke-Nssm set $Name Start SERVICE_DELAYED_AUTO_START
    Invoke-Nssm set $Name AppExit Default Restart
    Invoke-Nssm set $Name AppRestartDelay 3000
    Invoke-Nssm set $Name AppThrottle 15000
    Invoke-Nssm set $Name AppStopMethodConsole 5000
    Invoke-Nssm set $Name AppStopMethodWindow 3000
    Invoke-Nssm set $Name AppStopMethodThreads 3000
    $log = Join-Path $LogDir "$Name.log"
    Invoke-Nssm set $Name AppStdout $log
    Invoke-Nssm set $Name AppStderr $log
    Invoke-Nssm set $Name AppStdoutCreationDisposition 4
    Invoke-Nssm set $Name AppStderrCreationDisposition 4
    Invoke-Nssm set $Name AppRotateFiles 1
    Invoke-Nssm set $Name AppRotateOnline 0     # online rotation left NSSM stuck in StopPending
    Invoke-Nssm set $Name AppRotateBytes 10485760
    & sc.exe failure $Name reset= 86400 actions= restart/5000/restart/15000/restart/60000 | Out-Null
    & sc.exe failureflag $Name 1 | Out-Null
    & sc.exe sdset $Name "D:(A;;CCLCSWRPWPDTLOCRRC;;;SY)(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)(A;;CCLCSWRPWPLOCRRC;;;IU)(A;;CCLCSWLOCRRC;;;SU)" | Out-Null
}

function Wait-Http([string]$Url, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try { Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3 | Out-Null; return $true } catch { Start-Sleep -Seconds 1 }
    }
    return $false
}

Remove-SmartParkService $Portal
Remove-SmartParkService $Mock
if ($Remove) {
    Write-Host "$Portal and $Mock removed."
    return
}

# --- portal ------------------------------------------------------------------
if (-not $NodeExe) {
    $cmd = Get-Command node -ErrorAction SilentlyContinue
    $NodeExe = if ($cmd) { $cmd.Source } else { Join-Path $env:ProgramFiles "nodejs\node.exe" }
}
if (-not (Test-Path $NodeExe)) { throw "Node.js not found ($NodeExe). Install it: winget install OpenJS.NodeJS.LTS" }
$nextBin = Join-Path $PortalDir "node_modules\next\dist\bin\next"
if (-not (Test-Path $nextBin)) { throw "Portal packages missing in $PortalDir. Run start-portal.bat there once." }
if (-not (Test-Path (Join-Path $PortalDir ".next\BUILD_ID"))) { throw "Portal not built. Run 'npm run build' in $PortalDir." }
if (-not (Test-Path (Join-Path $PortalDir ".env.local"))) { throw "Missing $PortalDir\.env.local. Run start-portal.bat once (it creates it)." }

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
# Relative script path: PowerShell 5.1 drops embedded quotes on native calls.
Invoke-Nssm install $Portal $NodeExe "node_modules\next\dist\bin\next" "start" "-p" "$Port"
Invoke-Nssm set $Portal DisplayName "SmartPark Portal (pay page + back office)"
Invoke-Nssm set $Portal Description "Zirp Next.js portal: public receipt/pay page and back office over the Site Service API. Port $Port."
Set-CommonOptions $Portal $PortalDir
Invoke-Nssm set $Portal AppEnvironmentExtra "NODE_ENV=production" "NEXT_TELEMETRY_DISABLED=1" "PORT=$Port"
Invoke-Nssm start $Portal
if (Wait-Http "http://127.0.0.1:$Port/" 60) { Write-Host "$Portal answers on port $Port." }
else { Write-Warning "$Portal did not answer within 60 s. Check $LogDir\$Portal.log" }

# --- mock ClickPesa (test sites only) ----------------------------------------------
if (-not $NoMock) {
    if (-not (Test-Path $Py64)) { throw "Missing $Py64" }
    Invoke-Nssm install $Mock $Py64 "-m" "app.mock_services.clickpesa" "--host" "0.0.0.0" "--port" "$MockPort"
    Invoke-Nssm set $Mock DisplayName "SmartPark Mock Payments (TEST ONLY)"
    Invoke-Nssm set $Mock Description "Mock ClickPesa for rehearsals. No real money. Do not run on a live site."
    Set-CommonOptions $Mock $InstallDir
    Invoke-Nssm set $Mock AppEnvironmentExtra "SMARTPARK_HOME=$InstallDir" "PYTHONPATH=$InstallDir" "PYTHONUNBUFFERED=1"
    Invoke-Nssm start $Mock
    if (Wait-Http "http://127.0.0.1:$MockPort/health" 45) { Write-Host "$Mock answers on port $MockPort (phone: /phone)." }
    else { Write-Warning "$Mock did not answer within 45 s. Check $LogDir\$Mock.log" }
}
Write-Host "Phones on the LAN also need inbound TCP $Port$(if (-not $NoMock) { " and $MockPort" }) allowed in Windows Firewall."
