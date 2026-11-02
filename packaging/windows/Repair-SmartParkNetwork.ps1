#requires -Version 5.1
<#
.SYNOPSIS
    Repairs SmartPark LAN firewall rules after a Windows update.

.DESCRIPTION
    This is intentionally a network-only repair. It does not delete the
    database, reset deployment.json, change camera settings, or edit PostgreSQL
    authentication. It repairs the API/WebRTC rules and prints the listener and
    PostgreSQL checks needed when a Processing Node cannot connect.
#>
[CmdletBinding()]
param(
    [string]$InstallDir = ""
)

$ErrorActionPreference = "Continue"

if ([string]::IsNullOrWhiteSpace($InstallDir)) {
    $InstallDir = [Environment]::GetEnvironmentVariable("SMARTPARK_HOME", "User")
}
if ([string]::IsNullOrWhiteSpace($InstallDir)) {
    $InstallDir = Join-Path $env:LOCALAPPDATA "Programs\SmartPark Edge"
}
$InstallDir = [Environment]::ExpandEnvironmentVariables($InstallDir)

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run Repair-SmartParkNetwork.bat as Administrator. No application data has been changed."
}

function Repair-Rule {
    param(
        [string]$Name,
        [string]$Protocol,
        [int]$Port
    )
    $rules = @(Get-NetFirewallRule -DisplayName $Name -ErrorAction SilentlyContinue)
    if ($rules.Count -eq 0) {
        New-NetFirewallRule -DisplayName $Name -Direction Inbound -Action Allow -Protocol $Protocol -LocalPort $Port -Profile Any -RemoteAddress LocalSubnet | Out-Null
        Write-Host "CREATED  $Name  $Protocol/$Port  LocalSubnet"
        return
    }
    $rules | Set-NetFirewallRule -Enabled True -Direction Inbound -Action Allow -Profile Any | Out-Null
    $rules | Get-NetFirewallAddressFilter | Set-NetFirewallAddressFilter -RemoteAddress LocalSubnet | Out-Null
    $rules | Get-NetFirewallPortFilter | Set-NetFirewallPortFilter -Protocol $Protocol -LocalPort $Port | Out-Null
    Write-Host "REPAIRED $Name  $Protocol/$Port  LocalSubnet"
}

Write-Host "SmartPark network repair (no database/configuration wipe)"
Write-Host "InstallDir: $InstallDir"
Get-NetConnectionProfile -ErrorAction SilentlyContinue | Format-Table Name, InterfaceAlias, NetworkCategory, IPv4Connectivity -AutoSize
Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
    Format-Table IPAddress, InterfaceAlias, PrefixLength -AutoSize

Repair-Rule -Name "SmartPark Site API" -Protocol TCP -Port 8760
if (Test-Path (Join-Path $InstallDir "vendor\mediamtx\mediamtx.exe")) {
    Repair-Rule -Name "SmartPark MediaMTX WebRTC" -Protocol TCP -Port 8889
    Repair-Rule -Name "SmartPark MediaMTX ICE" -Protocol UDP -Port 8189
    Repair-Rule -Name "SmartPark MediaMTX ICE TCP" -Protocol TCP -Port 8189
}

Write-Host "`nCurrent listeners:"
foreach ($port in @(8760, 5432)) {
    try {
        Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction Stop |
            Format-Table LocalAddress, LocalPort, OwningProcess -AutoSize
    } catch {
        Write-Host "NOT LISTENING: TCP $port"
    }
}

Write-Host "`nLocal API check:"
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8760/health/live" -UseBasicParsing -TimeoutSec 4 -ErrorAction Stop
    Write-Host "PASS: Site API returned HTTP $($response.StatusCode)"
} catch {
    Write-Warning "Site API local check failed: $($_.Exception.Message)"
}

Write-Host "`nIf TCP 5432 is not listening on 0.0.0.0 or the server LAN IP, PostgreSQL is still loopback-only; update PostgreSQL listen_addresses and pg_hba.conf for the LAN, then restart PostgreSQL."
Write-Host "The repair intentionally does not open TCP 5432 automatically because that rule must match the site's PostgreSQL policy."
