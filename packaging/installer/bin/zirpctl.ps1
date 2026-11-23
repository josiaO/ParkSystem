#requires -Version 5.1
<#
.SYNOPSIS
    Zirp release control: activate a version, roll back, manage services, back up.

.DESCRIPTION
    Installed per machine at  C:\Program Files\Zirp\bin\zirpctl.ps1  by Zirp-Setup.exe.

    Layout
        C:\Program Files\Zirp\versions\<version>\   one complete, read-only release
        C:\Program Files\Zirp\current               junction -> the active version
        C:\Program Files\Zirp\bin\                  this tool and the desktop launcher
        C:\ProgramData\SmartParkEdge\               all site data (never touched by upgrades)
            config\zirp.env  config\portal.env     settings
            backups\pre-upgrade\                    database dump taken before every upgrade
            logs\install\                           a log of every zirpctl run

    Services point at ...\current, so switching versions is: stop, switch the
    junction, start, check health. A failed health check switches back.

    Commands
        zirpctl status
        zirpctl activate -Version 1.4.0 [-Role COMBINED|SERVER|EDGE|OPERATOR|KIOSK] [-KioskUser NAME] [-HvxHost service|task]
        zirpctl rollback [-To 1.3.2] [-RestoreDatabase] [-Force]
        zirpctl services start|stop|restart|install|remove
        zirpctl backup [-Label manual]
        zirpctl uninstall            (services, tasks, firewall rules, junction; no data)
        zirpctl purge-data -Force    (deletes C:\ProgramData\SmartParkEdge)
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)][string]$Command = "status",
    [Parameter(Position = 1)][string]$Action = "",
    [string]$Version = "",
    [string]$To = "",
    [ValidateSet("", "COMBINED", "SERVER", "EDGE", "OPERATOR", "KIOSK")][string]$Role = "",
    [string]$KioskUser = "",
    # Plain words, not a [switch]: "powershell -File" passes "$true" as text,
    # which a switch cannot bind (the installer calls us that way).
    [ValidateSet("", "service", "task")][string]$HvxHost = "",
    [switch]$RestoreDatabase,
    [switch]$Force,
    [string]$Label = "manual",
    [string]$Root = "",
    [int]$HealthTimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"
if (-not $Root) { $Root = Split-Path -Parent $PSScriptRoot }
$Root = (Resolve-Path $Root).Path
$Versions = Join-Path $Root "versions"
$Current = Join-Path $Root "current"
$DataDir = Join-Path $env:ProgramData "SmartParkEdge"
$ConfigDir = Join-Path $DataDir "config"
$BackupDir = Join-Path $DataDir "backups\pre-upgrade"
$InstallLogDir = Join-Path $DataDir "logs\install"
$ServiceLogDir = Join-Path $DataDir "logs\services"
$RegKey = "HKLM:\SOFTWARE\Zirp"

$SiteService = "SmartParkSiteService"
$MediaService = "SmartParkMediaService"
$WorkerService = "SmartParkRecognitionWorker"
$HvxService = "SmartParkHvxHost"
$PortalService = "SmartParkPortal"
$CacheService = "SmartParkCache"
# Stopped in this order; the shared cache goes last because the others use it.
$AllServices = @($PortalService, $WorkerService, $MediaService, $HvxService, $SiteService, $CacheService)
# Local Redis for short-lived lane state shared by the Zirp services. Loopback
# only, nothing written to disk (PostgreSQL holds every record). A port away
# from 6379 so it never clashes with another Redis on the PC.
$CachePort = 6391
$HvxTask = "SmartPark HVX Host"
$KioskTask = "Zirp Kiosk"
$LegacyTasks = @("SmartPark Site Service", "SmartPark Recognition Worker", "SmartPark HVX Host", "SmartPark Media Service")

New-Item -ItemType Directory -Force -Path $InstallLogDir | Out-Null
$RunLog = Join-Path $InstallLogDir ("zirpctl-{0}-{1}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"), $Command)
Start-Transcript -Path $RunLog -Force | Out-Null

function Assert-Admin {
    $p = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Run zirpctl from an elevated (Administrator) PowerShell."
    }
}

# ------------------------------------------------------------------ state

$StateFile = Join-Path $DataDir "install\state.json"
$Warnings = New-Object System.Collections.Generic.List[string]

function Write-TextFile([string]$Path, [string]$Text) {
    # UTF-8 without BOM: read by the installer and by people.
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path) | Out-Null
    [IO.File]::WriteAllText($Path, $Text, (New-Object Text.UTF8Encoding $false))
}

function Get-State {
    # The installer writes HKLM\SOFTWARE\Zirp; zirpctl also keeps state.json
    # (authoritative when both exist, and readable without registry rights).
    $s = @{ CurrentVersion = ""; PreviousVersion = ""; Role = ""; KioskUser = ""; HvxAsService = "0"; LastBackup = "" }
    if (Test-Path $RegKey) {
        $k = Get-ItemProperty $RegKey -ErrorAction SilentlyContinue
        foreach ($name in @($s.Keys)) { if ($k -and $null -ne $k.$name -and "$($k.$name)" -ne "") { $s[$name] = [string]$k.$name } }
    }
    if (Test-Path $StateFile) {
        try {
            $j = Get-Content $StateFile -Raw -Encoding UTF8 | ConvertFrom-Json
            foreach ($name in @($s.Keys)) { if ($null -ne $j.$name -and "$($j.$name)" -ne "") { $s[$name] = [string]$j.$name } }
        } catch { Write-Warning "Ignoring unreadable $StateFile" }
    }
    return $s
}

function Set-State([hashtable]$Values) {
    $s = Get-State
    foreach ($name in $Values.Keys) { $s[$name] = [string]$Values[$name] }
    $s["InstallDir"] = $Root
    Write-TextFile $StateFile ($s | ConvertTo-Json)
    try {
        if (-not (Test-Path $RegKey)) { New-Item -Path $RegKey -Force -ErrorAction Stop | Out-Null }
        foreach ($name in $s.Keys) { Set-ItemProperty -Path $RegKey -Name $name -Value ([string]$s[$name]) -ErrorAction Stop }
    } catch {
        Write-Warning "Could not update HKLM\SOFTWARE\Zirp ($($_.Exception.Message)); state is kept in $StateFile."
    }
}

function Add-History([string]$Event, [hashtable]$Data) {
    $line = @{ utc = (Get-Date).ToUniversalTime().ToString("o"); event = $Event } + $Data
    Add-Content -Path (Join-Path $InstallLogDir "history.jsonl") -Value ($line | ConvertTo-Json -Compress) -Encoding UTF8
}

function Get-InstalledVersions {
    if (-not (Test-Path $Versions)) { return @() }
    return @(Get-ChildItem $Versions -Directory | Where-Object { Test-Path (Join-Path $_.FullName "VERSION") } |
        Sort-Object { try { [version]($_.Name -replace '[^0-9.].*$', '') } catch { [version]"0.0" } } | ForEach-Object { $_.Name })
}

function Get-ActiveVersion {
    if (-not (Test-Path $Current)) { return "" }
    $item = Get-Item $Current -Force
    if ($item.LinkType -eq "Junction" -and $item.Target) { return Split-Path -Leaf ([string]@($item.Target)[0]) }
    return ""
}

function Set-ActiveVersion([string]$Ver) {
    $target = Join-Path $Versions $Ver
    if (-not (Test-Path (Join-Path $target "VERSION"))) { throw "Version $Ver is not installed ($target)." }
    if (Test-Path $Current) {
        $item = Get-Item $Current -Force
        if ($item.LinkType -ne "Junction") { throw "$Current exists and is not a junction; refusing to replace it." }
        # rmdir on a junction removes the link only, never the target's files.
        & cmd.exe /c rmdir "`"$Current`"" | Out-Null
    }
    & cmd.exe /c mklink /J "`"$Current`"" "`"$target`"" | Out-Null
    if ((Get-ActiveVersion) -ne $Ver) { throw "Could not point $Current at $target." }
    Write-Host "Active version: $Ver"
}

function Get-RoleInfo([string]$R) {
    switch ($R) {
        "COMBINED" { return @{ Deployment = "SITE_SERVER"; Station = ""; Services = $true; Cameras = $true } }
        "SERVER"   { return @{ Deployment = "SITE_SERVER"; Station = ""; Services = $true; Cameras = $false } }
        "EDGE"     { return @{ Deployment = "EDGE_NODE"; Station = ""; Services = $true; Cameras = $true } }
        "OPERATOR" { return @{ Deployment = "OPERATOR_CLIENT"; Station = ""; Services = $false; Cameras = $false } }
        "KIOSK"    { return @{ Deployment = "OPERATOR_CLIENT"; Station = "KIOSK"; Services = $false; Cameras = $false } }
        default    { throw "Unknown role '$R'." }
    }
}

function Get-ApiPort {
    $path = Join-Path $DataDir "deployment.json"
    if (Test-Path $path) {
        try { $d = Get-Content $path -Raw -Encoding UTF8 | ConvertFrom-Json; if ($d.server_bind_port) { return [int]$d.server_bind_port } } catch {}
    }
    return 8760
}

# ------------------------------------------------------------------ prerequisites and legacy

function Test-VcX64Installed([string]$Installer) {
    $k = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\X64" -ErrorAction SilentlyContinue
    if (-not $k -or $k.Installed -ne 1) { return $false }
    try {
        $have = [version]("{0}.{1}.{2}" -f $k.Major, $k.Minor, $k.Bld)
        $fv = (Get-Item $Installer).VersionInfo.FileVersion -replace '[^0-9.].*$', ''
        $want = [version](($fv.Split(".") | Select-Object -First 3) -join ".")
        return $have -ge $want
    } catch { return $true }
}

function Test-Vc2005X86Installed {
    return [bool](Get-ChildItem (Join-Path $env:windir "WinSxS") -Directory -Filter "x86_microsoft.vc80.crt_1fc8b3b9a1e18e3b_*" -ErrorAction SilentlyContinue | Select-Object -First 1)
}

function Install-Prerequisites([string]$VersionDir) {
    $vc64 = Join-Path $VersionDir "vendor\vc_redist.x64.exe"
    if (Test-Path $vc64) {
        if (Test-VcX64Installed $vc64) { Write-Host "VC++ x64 runtime: already installed" }
        else {
            Write-Host "Installing the Microsoft VC++ x64 runtime..."
            $p = Start-Process -FilePath $vc64 -ArgumentList "/install", "/quiet", "/norestart" -Wait -PassThru
            if ($p.ExitCode -notin @(0, 1638, 3010)) { throw "The Microsoft VC++ x64 runtime could not be installed (exit $($p.ExitCode)). Install vc_redist.x64.exe from Microsoft and run setup again." }
            if ($p.ExitCode -eq 3010) { $Warnings.Add("Windows asks for a restart to finish the VC++ runtime update. Restart this PC when convenient.") }
        }
    }
    $vc86 = Join-Path $VersionDir "vendor\vc_redist.x86.exe"
    if (Test-Path $vc86) {
        # Visual C++ 2005 SP1 x86, required by the camera vendor's 32-bit SDK.
        if (Test-Vc2005X86Installed) { Write-Host "VC++ 2005 x86 runtime: already installed" }
        else {
            Write-Host "Installing the Microsoft VC++ 2005 x86 runtime (camera SDK)..."
            $p = Start-Process -FilePath $vc86 -ArgumentList "/q" -Wait -PassThru
            if ($p.ExitCode -notin @(0, 1638, 3010)) { $Warnings.Add("The VC++ 2005 x86 runtime returned code $($p.ExitCode): cameras that use the vendor SDK may not connect.") }
        }
    }
}

function Move-LegacyRegistrations {
    <# Older USB kits installed into a user's profile and registered the same
       service names from there. Remove those registrations (files are left in
       place) and carry the old settings file over to ProgramData once. #>
    foreach ($svc in $AllServices + @("SmartParkMockPayments")) {
        $row = Get-CimInstance Win32_Service -Filter "Name='$svc'" -ErrorAction SilentlyContinue
        if (-not $row) { continue }
        $exe = ([string]$row.PathName).Trim().Trim('"')
        if ($exe -like "$Root\*") { continue }
        if ($svc -eq "SmartParkSiteService" -and $exe -match '\\vendor\\nssm\\nssm\.exe$') {
            $oldRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $exe))
            $oldEnv = Join-Path $oldRoot ".env"
            $newEnv = Join-Path $ConfigDir "zirp.env"
            if ((Test-Path $oldEnv) -and -not (Test-Path $newEnv)) {
                New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
                Copy-Item $oldEnv $newEnv
                Write-Host "Settings carried over from $oldEnv to $newEnv"
            }
            $oldPortalEnv = Join-Path $oldRoot "portal\.env.local"
            if ((Test-Path $oldPortalEnv) -and -not (Test-Path (Join-Path $ConfigDir "portal.env"))) {
                Copy-Item $oldPortalEnv (Join-Path $ConfigDir "portal.env")
            }
            Add-History "legacy-install-detached" @{ path = $oldRoot }
            Write-Host "Old per-user install found at $oldRoot. Its services are removed; its files are kept (delete them when the new install is confirmed)."
        }
        Write-Host "Removing legacy service registration $svc ($exe)"
        & sc.exe stop $svc 2>$null | Out-Null
        Start-Sleep -Milliseconds 500
        & sc.exe delete $svc 2>$null | Out-Null
    }
    foreach ($task in $LegacyTasks) {
        $t = Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue
        if ($t -and -not (($t.Actions | ForEach-Object { "$($_.Execute) $($_.Arguments) $($_.WorkingDirectory)" }) -join " ").Contains($Root)) {
            Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue
            Write-Host "Removed legacy scheduled task '$task'"
        }
    }
}

# ------------------------------------------------------------------ services

function Invoke-Nssm {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $nssm = Join-Path $Current "vendor\nssm\nssm.exe"
    & $nssm @Arguments 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "nssm $($Arguments -join ' ') failed with exit $LASTEXITCODE." }
}

function Remove-ZirpService([string]$Name) {
    if (Get-Service -Name $Name -ErrorAction SilentlyContinue) {
        & sc.exe stop $Name 2>$null | Out-Null
        for ($i = 0; $i -lt 30 -and (Get-Service $Name -ErrorAction SilentlyContinue).Status -ne "Stopped"; $i++) { Start-Sleep -Milliseconds 500 }
        & sc.exe delete $Name 2>$null | Out-Null
        Start-Sleep -Milliseconds 500
    }
}

function Register-ZirpService {
    param([string]$Name, [string]$DisplayName, [string]$Exe, [string[]]$Arguments, [string]$WorkDir,
          [string[]]$DependsOn = @(), [string[]]$Environment = @())
    Remove-ZirpService $Name
    Invoke-Nssm install $Name $Exe @Arguments
    Invoke-Nssm set $Name DisplayName $DisplayName
    Invoke-Nssm set $Name Description "Zirp parking runtime. Restarts automatically. Logs: $ServiceLogDir"
    Invoke-Nssm set $Name AppDirectory $WorkDir
    Invoke-Nssm set $Name ObjectName LocalSystem
    Invoke-Nssm set $Name Start SERVICE_AUTO_START
    Invoke-Nssm set $Name AppExit Default Restart
    Invoke-Nssm set $Name AppRestartDelay 2000
    Invoke-Nssm set $Name AppThrottle 15000
    Invoke-Nssm set $Name AppStopMethodConsole 15000
    Invoke-Nssm set $Name AppStopMethodWindow 5000
    Invoke-Nssm set $Name AppStopMethodThreads 5000
    $log = Join-Path $ServiceLogDir "$Name.log"
    Invoke-Nssm set $Name AppStdout $log
    Invoke-Nssm set $Name AppStderr $log
    Invoke-Nssm set $Name AppStdoutCreationDisposition 4
    Invoke-Nssm set $Name AppStderrCreationDisposition 4
    Invoke-Nssm set $Name AppRotateFiles 1
    Invoke-Nssm set $Name AppRotateOnline 0
    Invoke-Nssm set $Name AppRotateBytes 10485760
    if ($Environment.Count) { Invoke-Nssm set $Name AppEnvironmentExtra @Environment }
    if ($DependsOn.Count) { Invoke-Nssm set $Name DependOnService @DependsOn }
    & sc.exe failure $Name reset= 86400 actions= restart/5000/restart/15000/restart/60000 | Out-Null
    & sc.exe failureflag $Name 1 | Out-Null
    # Interactive users (the desktop's repair button) may query/start/stop.
    & sc.exe sdset $Name "D:(A;;CCLCSWRPWPDTLOCRRC;;;SY)(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)(A;;CCLCSWRPWPLOCRRC;;;IU)(A;;CCLCSWLOCRRC;;;SU)" | Out-Null
}

function Get-PythonEnvironment([string]$NodeRole) {
    $vars = @(
        "SMARTPARK_DEPLOYMENT_PROFILE=PRODUCTION",
        "SMARTPARK_NODE_ROLE=$NodeRole",
        "SMARTPARK_HOME=$Current",
        "SMARTPARK_LOG_DIR=$DataDir\logs",
        "PYTHONPATH=$Current",
        "PYTHONUNBUFFERED=1",
        "SMARTPARK_HVX_VENDOR_DIR=$Current\vendor"
    )
    $mediamtx = Join-Path $Current "vendor\mediamtx\mediamtx.exe"
    if (Test-Path $mediamtx) { $vars += "SMARTPARK_MEDIAMTX_BIN=$mediamtx" }
    if (Test-Path (Get-RedisExe)) { $vars += "SMARTPARK_REDIS_URL=redis://127.0.0.1:$CachePort/0" }
    return $vars
}

function Get-RedisExe { return (Join-Path $Current "vendor\redis\redis-server.exe") }

function Register-CacheService {
    # Returns $true when the shared cache service was registered.
    $exe = Get-RedisExe
    if (-not (Test-Path $exe)) {
        Write-Host "No bundled Redis in this release; Zirp keeps lane state in memory."
        return $false
    }
    $conf = Join-Path $ConfigDir "redis.conf"
    $lines = @(
        "# Written by zirpctl on every install: Zirp's shared lane cache.",
        "bind 127.0.0.1",
        "protected-mode yes",
        "port $CachePort",
        'save ""',
        "appendonly no",
        "maxmemory 64mb",
        "maxmemory-policy allkeys-lru",
        "databases 4",
        "loglevel notice"
    )
    Set-Content -Path $conf -Value $lines -Encoding ascii
    Register-ZirpService -Name $CacheService -DisplayName "Zirp Shared Cache (Redis)" -Exe $exe `
        -Arguments @($conf) -WorkDir (Split-Path $exe)
    return $true
}

function Get-PortalEnvironment([int]$ApiPort) {
    $vars = @("NODE_ENV=production", "NEXT_TELEMETRY_DISABLED=1", "PORT=3000", "HOSTNAME=0.0.0.0",
             "ZIRP_API_URL=http://127.0.0.1:$ApiPort")
    $file = Join-Path $ConfigDir "portal.env"
    if (Test-Path $file) {
        foreach ($line in Get-Content $file -Encoding UTF8) {
            $t = $line.Trim()
            if (-not $t -or $t.StartsWith("#") -or -not $t.Contains("=")) { continue }
            $key = $t.Split("=", 2)[0].Trim()
            $vars = @($vars | Where-Object { -not $_.StartsWith("$key=") }) + $t
        }
    }
    return $vars
}

function Register-HvxLogonTask {
    $py32 = Join-Path $Current "python32\python.exe"
    $work = Join-Path $Current "tools\hvx_sdk_host"
    $taskAction = New-ScheduledTaskAction -Execute $py32 -Argument "hvx_host.py" -WorkingDirectory $work
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
    $principal = New-ScheduledTaskPrincipal -GroupId "S-1-5-32-545" -RunLevel Limited
    Register-ScheduledTask -TaskName $HvxTask -Action $taskAction -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
}

function Register-FirewallRules([bool]$Cameras) {
    $rules = @(@{ Name = "Zirp Site API"; Protocol = "TCP"; Port = (Get-ApiPort) },
               @{ Name = "Zirp Portal"; Protocol = "TCP"; Port = 3000 })
    if ($Cameras -and (Test-Path (Join-Path $Current "vendor\mediamtx\mediamtx.exe"))) {
        $rules += @(@{ Name = "Zirp MediaMTX WebRTC"; Protocol = "TCP"; Port = 8889 },
                    @{ Name = "Zirp MediaMTX ICE"; Protocol = "UDP"; Port = 8189 },
                    @{ Name = "Zirp MediaMTX ICE TCP"; Protocol = "TCP"; Port = 8189 })
    }
    foreach ($rule in $rules) {
        Remove-NetFirewallRule -DisplayName $rule.Name -ErrorAction SilentlyContinue
        New-NetFirewallRule -DisplayName $rule.Name -Group "Zirp" -Direction Inbound -Action Allow -Protocol $rule.Protocol `
            -LocalPort $rule.Port -Profile Any -RemoteAddress LocalSubnet | Out-Null
    }
}

function Install-RoleServices([string]$R, [bool]$HvxSvc) {
    $info = Get-RoleInfo $R
    foreach ($name in $AllServices) { Remove-ZirpService $name }
    Unregister-ScheduledTask -TaskName $HvxTask -Confirm:$false -ErrorAction SilentlyContinue
    if (-not $info.Services) {
        Write-Host "Role $R runs no background services on this PC."
        return
    }
    New-Item -ItemType Directory -Force -Path $ServiceLogDir | Out-Null
    & icacls.exe (Join-Path $DataDir "logs") /grant "*S-1-5-32-545:(OI)(CI)M" /T /C /Q | Out-Null
    $py64 = Join-Path $Current "python64\python.exe"
    # Roles with cameras run the Site Service and the Recognition Worker side
    # by side; the cache lets them count the same car. Not a dependency: if
    # it's stopped, Zirp falls back to memory.
    if ($info.Cameras) { Register-CacheService | Out-Null }
    $nodeRole = "SERVER"   # the persisted deployment role decides; CLIENT here would disable local runtime
    $pyEnv = Get-PythonEnvironment $nodeRole
    $siteDepends = @()
    $pg = Get-Service -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "postgresql*" } | Select-Object -First 1
    if ($pg) { $siteDepends += $pg.Name; Write-Host "Site Service will start after $($pg.Name)." }
    Register-ZirpService -Name $SiteService -DisplayName "Zirp Site Service" -Exe $py64 -Arguments @("-m", "app.site_service") `
        -WorkDir $Current -DependsOn $siteDepends -Environment $pyEnv
    if ($info.Cameras) {
        $workerDepends = @($SiteService)
        if (Test-Path (Join-Path $Current "vendor\mediamtx\mediamtx.exe")) {
            Register-ZirpService -Name $MediaService -DisplayName "Zirp Media Service (MediaMTX)" -Exe $py64 `
                -Arguments @("-m", "app.media_service") -WorkDir $Current -DependsOn @($SiteService) -Environment $pyEnv
            $workerDepends = @($MediaService)
        }
        Register-ZirpService -Name $WorkerService -DisplayName "Zirp Recognition Worker" -Exe $py64 `
            -Arguments @("-m", "app.recognition_worker") -WorkDir $Current -DependsOn $workerDepends -Environment $pyEnv
        if (Test-Path (Join-Path $Current "python32\python.exe")) {
            if ($HvxSvc) {
                Register-ZirpService -Name $HvxService -DisplayName "Zirp Camera SDK Host (32-bit)" `
                    -Exe (Join-Path $Current "python32\python.exe") -Arguments @("hvx_host.py") `
                    -WorkDir (Join-Path $Current "tools\hvx_sdk_host") -Environment $pyEnv
            } else {
                Register-HvxLogonTask
                Write-Host "Camera SDK host runs at user sign-in (scheduled task '$HvxTask')."
            }
        }
    }
    $node = Join-Path $Current "vendor\node\node.exe"
    $server = Join-Path $Current "portal\server.js"
    if ($info.Deployment -eq "SITE_SERVER" -and (Test-Path $node) -and (Test-Path $server)) {
        Register-ZirpService -Name $PortalService -DisplayName "Zirp Portal (pay page + back office)" -Exe $node `
            -Arguments @("server.js") -WorkDir (Join-Path $Current "portal") -DependsOn @($SiteService) `
            -Environment (Get-PortalEnvironment (Get-ApiPort))
    }
    Register-FirewallRules $info.Cameras
}

function Start-ZirpServices {
    # sc.exe returns at once; Start-Service waited for every service in turn.
    foreach ($name in @($CacheService, $SiteService, $MediaService, $WorkerService, $HvxService, $PortalService)) {
        if (Get-Service -Name $name -ErrorAction SilentlyContinue) {
            & sc.exe start $name | Out-Null
            Write-Host "Starting $name"
        }
    }
    if (Get-ScheduledTask -TaskName $HvxTask -ErrorAction SilentlyContinue) {
        Start-ScheduledTask -TaskName $HvxTask -ErrorAction SilentlyContinue
    }
}

function Stop-ZirpServices {
    foreach ($name in $AllServices) {
        if (Get-Service -Name $name -ErrorAction SilentlyContinue) {
            & sc.exe stop $name 2>$null | Out-Null
        }
    }
    Stop-ScheduledTask -TaskName $HvxTask -ErrorAction SilentlyContinue
    $deadline = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $deadline) {
        $running = @($AllServices | ForEach-Object { Get-Service $_ -ErrorAction SilentlyContinue } | Where-Object { $_.Status -ne "Stopped" })
        if (-not $running.Count) { break }
        Start-Sleep -Milliseconds 500
    }
    # Anything still running from this installation (desktop, stray workers).
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $p = [string]$_.ExecutablePath; $p -and ($p -like "$Root\*")
    } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

function Get-SiteServiceError {
    # Last lines of the Site Service's own log: the real reason it did not start.
    $log = Join-Path $ServiceLogDir "$SiteService.log"
    if (-not (Test-Path $log)) { return "" }
    $tail = @(Get-Content $log -Tail 200 -ErrorAction SilentlyContinue)
    $err = @($tail | Where-Object { $_ -match '(Error|Exception|failed)' -and $_ -notmatch '^\s+File ' } | Select-Object -Last 4)
    return ($err -join " | ")
}

function Invoke-HealthProbe([string]$Url) {
    # The bundled Python (no proxies) decides health; PowerShell's
    # Invoke-WebRequest proved unable to reach a healthy API on site PCs.
    $py = Join-Path $Current "python64\python.exe"
    Push-Location $Current
    try { $out = & $py -m app.release_tool health --url $Url --timeout 4 2>&1; $code = $LASTEXITCODE } finally { Pop-Location }
    return @{ Ok = ($code -eq 0); Detail = ("$out" -replace '\s+', ' ').Trim() }
}

function Test-Health([string]$R) {
    $info = Get-RoleInfo $R
    if (-not $info.Services) { return $true }
    $url = "http://127.0.0.1:$(Get-ApiPort)/health/live"
    $deadline = (Get-Date).AddSeconds($HealthTimeoutSeconds)
    $log = Join-Path $ServiceLogDir "$SiteService.log"
    $since = Get-Date
    $notRunningSince = $null
    $lastNote = Get-Date
    Write-Host "Waiting for the Site Service to answer at $url (first start runs database upgrades)..."
    while ((Get-Date) -lt $deadline) {
        $probe = Invoke-HealthProbe $url
        if ($probe.Ok) { Write-Host ("Health check passed after {0} s: {1}" -f [int]((Get-Date) - $since).TotalSeconds, $url); return $true }
        if (((Get-Date) - $lastNote).TotalSeconds -ge 30) {
            Write-Host ("  still waiting ({0} s): {1}" -f [int]((Get-Date) - $since).TotalSeconds, $probe.Detail)
            $lastNote = Get-Date
        }
        $svc = Get-Service $SiteService -ErrorAction SilentlyContinue
        if (-not $svc) { return $false }
        # Fail fast when the Site Service reports that it cannot start, or NSSM
        # stopped restarting it (Paused/Stopped) for more than 20 s.
        if ((Test-Path $log) -and (Get-Item $log).LastWriteTime -gt $since) {
            $tail = (Get-Content $log -Tail 5 -ErrorAction SilentlyContinue) -join "`n"
            if ($tail -match 'Application startup failed') {
                Write-Warning "The Site Service failed to start: $(Get-SiteServiceError)"
                return $false
            }
        }
        if ($svc.Status -in @("Paused", "Stopped")) {
            if (-not $notRunningSince) { $notRunningSince = Get-Date }
            elseif (((Get-Date) - $notRunningSince).TotalSeconds -gt 20) {
                Write-Warning "The Site Service is $($svc.Status). $(Get-SiteServiceError)"
                return $false
            }
        } else { $notRunningSince = $null }
        Start-Sleep -Seconds 2
    }
    Write-Warning "No healthy answer from $url within $HealthTimeoutSeconds s ($($probe.Detail)). $(Get-SiteServiceError)"
    return $false
}

# ------------------------------------------------------------------ database backup

function Invoke-ReleaseTool([string]$VersionDir, [string[]]$Arguments) {
    $py = Join-Path $VersionDir "python64\python.exe"
    $old = @{ SMARTPARK_HOME = $env:SMARTPARK_HOME; PYTHONPATH = $env:PYTHONPATH }
    $env:SMARTPARK_HOME = $VersionDir; $env:PYTHONPATH = $VersionDir
    Push-Location $VersionDir
    try {
        $out = & $py -m app.release_tool @Arguments 2>&1
        $code = $LASTEXITCODE
    } finally {
        Pop-Location
        $env:SMARTPARK_HOME = $old.SMARTPARK_HOME; $env:PYTHONPATH = $old.PYTHONPATH
    }
    return @{ Code = $code; Output = ($out | Out-String).Trim() }
}

function Backup-Database([string]$VersionDir, [string]$Name) {
    New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
    & icacls.exe $BackupDir /inheritance:r /grant:r "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" /Q | Out-Null
    $file = Join-Path $BackupDir "$Name.sql"
    $res = Invoke-ReleaseTool $VersionDir @("backup", "--out", $file)
    if ($res.Code -ne 0) { throw "Database backup failed; nothing was changed.`n$($res.Output)" }
    Write-Host "Database backup: $file"
    return $file
}

function Invoke-Preflight([string]$VersionDir, [string]$R) {
    <# Checks before anything is stopped or changed. A problem stops setup with
       a plain explanation; the running version stays as it is. #>
    $problems = New-Object System.Collections.Generic.List[string]
    $info = Get-RoleInfo $R
    $drive = Get-PSDrive -Name ($DataDir.Substring(0, 1)) -ErrorAction SilentlyContinue
    if ($drive -and $drive.Free -lt 2GB) {
        $problems.Add(("Only {0:N1} GB is free on drive {1}: (photos, database backups). Free at least 2 GB and run setup again." -f ($drive.Free / 1GB), $drive.Name))
    }
    $report = $null
    if ($info.Services) {
        $res = Invoke-ReleaseTool $VersionDir @("check")
        $json = ($res.Output -split "`r?`n" | Where-Object { $_.Trim().StartsWith("{") } | Select-Object -Last 1)
        if ($json) { try { $report = $json | ConvertFrom-Json } catch {} }
        if ($report) {
            foreach ($p in @($report.problems)) { if ($p) { $problems.Add([string]$p) } }
            foreach ($w in @($report.warnings)) { if ($w) { $Warnings.Add([string]$w) } }
        } elseif ($res.Code -ne 0) {
            $problems.Add("The new version could not check this PC's setup: $($res.Output)")
        }
        foreach ($port in @((Get-ApiPort), 3000)) {
            foreach ($l in @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)) {
                $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($l.OwningProcess)" -ErrorAction SilentlyContinue
                $path = [string]$proc.ExecutablePath
                $ours = (-not $path) -or ($path -like "$Root\*") -or ($proc.Name -in @("python.exe", "node.exe", "nssm.exe"))
                if (-not $ours) { $problems.Add("Port $port is already used by $($proc.Name) (process $($l.OwningProcess), $path). Zirp needs it: stop or reconfigure that program and run setup again.") }
            }
        }
    }
    if ($problems.Count) {
        throw ("Setup stopped before changing anything:`n - " + ($problems -join "`n - "))
    }
    Write-Host "Pre-checks passed."
    return $report
}

function Clear-OldVersions([string]$Keep1, [string]$Keep2) {
    foreach ($v in Get-InstalledVersions) {
        if ($v -eq $Keep1 -or $v -eq $Keep2) { continue }
        Write-Host "Removing old version $v"
        Remove-Item -LiteralPath (Join-Path $Versions $v) -Recurse -Force -ErrorAction SilentlyContinue
    }
    Get-ChildItem $BackupDir -Filter "*.sql" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending |
        Select-Object -Skip 5 | ForEach-Object { Remove-Item $_.FullName, "$($_.FullName).json" -Force -ErrorAction SilentlyContinue }
}

function Write-LauncherConfig([string]$R) {
    # Read by app/desktop/launch.py at start-up (shortcuts run pythonw directly).
    $info = Get-RoleInfo $R
    $dir = Join-Path $DataDir "install"
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $body = [ordered]@{ installer_role = $R; deployment_role = $info.Deployment; station = $info.Station
                        deployment_profile = "PRODUCTION" }
    Set-Content -Path (Join-Path $dir "role.json") -Value ($body | ConvertTo-Json) -Encoding UTF8
}

function Register-KioskTask([string]$User) {
    if (-not $User) { throw "A kiosk needs the Windows account that runs it (-KioskUser)." }
    $script = Join-Path $Root "bin\Zirp-Kiosk.ps1"
    $taskAction = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`"" -WorkingDirectory (Join-Path $Root "bin")
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $User
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
    $principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $KioskTask -Action $taskAction -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
    Write-Host "Kiosk starts full screen when '$User' signs in. Set that account to sign in automatically (see the kiosk guide)."
}

# ------------------------------------------------------------------ commands

function Invoke-Activate {
    Assert-Admin
    if (-not $Version) { throw "activate needs -Version." }
    $state = Get-State
    $R = if ($Role) { $Role } elseif ($state.Role) { $state.Role } else { "COMBINED" }
    $hvx = if ($HvxHost) { $HvxHost -eq "service" } else { $state.HvxAsService -eq "1" -or [bool](Get-Service $HvxService -ErrorAction SilentlyContinue) }
    $kioskAccount = if ($KioskUser) { $KioskUser } else { $state.KioskUser }
    $info = Get-RoleInfo $R
    $newDir = Join-Path $Versions $Version
    if (-not (Test-Path (Join-Path $newDir "VERSION"))) { throw "Version $Version is not installed in $Versions." }
    $previous = Get-ActiveVersion
    Write-Host "Activating Zirp $Version (role $R; previous: $(if ($previous) { $previous } else { 'none' }))"

    New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
    Move-LegacyRegistrations
    $pre = Invoke-Preflight $newDir $R
    $revisionBefore = if ($pre) { [string]$pre.schema_revision } else { "" }
    Install-Prerequisites $newDir

    $backup = ""
    if ($info.Services -and (Test-Path (Join-Path $DataDir "deployment.json"))) {
        $from = if ($previous -and $previous -ne $Version) { Join-Path $Versions $previous } else { $newDir }
        Stop-ZirpServices
        $backup = Backup-Database $from ("{0}-before-{1}" -f (Get-Date -Format "yyyyMMdd-HHmmss"), $Version)
    } else {
        Stop-ZirpServices
    }

    Set-ActiveVersion $Version
    Write-LauncherConfig $R
    try {
        Install-RoleServices $R $hvx
        if ($info.Services -and (Test-Path (Join-Path $DataDir "deployment.json"))) {
            Start-ZirpServices
            if (-not (Test-Health $R)) { throw "Zirp $Version did not become healthy." }
        } elseif ($info.Services) {
            Write-Host "First installation: services are registered and start after the setup wizard (open Zirp)."
        }
    } catch {
        $err = $_.Exception.Message
        Add-History "activate-failed" @{ version = $Version; previous = $previous; error = $err; backup = $backup }
        if ($previous -and $previous -ne $Version) {
            Write-Warning "Activation failed: $err"
            Stop-ZirpServices
            # The previous version cannot run on a database the new one already
            # upgraded: put back the dump taken moments before the switch.
            $revisionNow = ""
            $rv = Invoke-ReleaseTool $newDir @("revision")
            if ($rv.Code -eq 0) { $revisionNow = ($rv.Output -split "`r?`n" | Select-Object -Last 1).Trim() }
            if ($backup -and $revisionBefore -and $revisionNow -and $revisionNow -ne $revisionBefore) {
                Write-Warning "The database was upgraded ($revisionBefore -> $revisionNow); restoring $backup for $previous."
                $rs = Invoke-ReleaseTool $newDir @("restore", "--in", $backup, "--yes")
                if ($rs.Code -ne 0) { Write-Warning "Database restore failed: $($rs.Output)" }
                else { $err = "$err (the database was restored to its state before the upgrade)" }
            }
            Write-Warning "Switching back to $previous."
            Set-ActiveVersion $previous
            Install-RoleServices $R $hvx
            Start-ZirpServices
            [void](Test-Health $R)
        } else {
            # Nothing to go back to: do not leave services restarting in a loop.
            Stop-ZirpServices
        }
        $why = Get-SiteServiceError
        if ($why) { $err = "$err Site Service: $why" }
        throw "Activation of $Version failed: $err. Log: $RunLog"
    }

    if ($R -eq "KIOSK") { Register-KioskTask $kioskAccount } else { Unregister-ScheduledTask -TaskName $KioskTask -Confirm:$false -ErrorAction SilentlyContinue }
    $keepPrevious = if ($previous -and $previous -ne $Version) { $previous } else { $state.PreviousVersion }
    Set-State @{ CurrentVersion = $Version; PreviousVersion = $keepPrevious; Role = $R; KioskUser = $kioskAccount
                 HvxAsService = $(if ($hvx) { "1" } else { "0" }); LastBackup = $backup }
    Add-History "activated" @{ version = $Version; previous = $previous; role = $R; backup = $backup }
    if ($Warnings.Count) {
        Write-TextFile (Join-Path $InstallLogDir "last-warnings.txt") ($Warnings -join "`r`n")
        foreach ($w in $Warnings) { Write-Warning $w }
    }
    Clear-OldVersions $Version $keepPrevious
    Write-Host "Zirp $Version is active."
}

function Invoke-Rollback {
    Assert-Admin
    $state = Get-State
    $active = Get-ActiveVersion
    $target = if ($To) { $To } else { $state.PreviousVersion }
    if (-not $target) { throw "No previous version is recorded. Use -To <version> (installed: $((Get-InstalledVersions) -join ', '))." }
    if ($target -eq $active) { throw "$target is already active." }
    $R = if ($state.Role) { $state.Role } else { "COMBINED" }
    $restoreFile = ""
    if ($RestoreDatabase) {
        $candidates = Get-ChildItem $BackupDir -Filter "*-before-$active.sql" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending
        if (-not $candidates) { throw "No pre-upgrade backup for $active was found in $BackupDir." }
        $restoreFile = $candidates[0].FullName
        if (-not $Force) {
            Write-Host "This replaces the current database with $restoreFile."
            Write-Host "Visits and payments recorded since that upgrade will be removed (the current database is kept as another backup)."
            if ((Read-Host "Type RESTORE to continue") -ne "RESTORE") { throw "Rollback cancelled." }
        }
    }
    Write-Host "Rolling back $active -> $target"
    Stop-ZirpServices
    Set-ActiveVersion $target
    if ($restoreFile) {
        $res = Invoke-ReleaseTool (Join-Path $Versions $target) @("restore", "--in", $restoreFile, "--yes")
        if ($res.Code -ne 0) { throw "Database restore failed: $($res.Output)" }
        Write-Host $res.Output
    }
    Install-RoleServices $R ($state.HvxAsService -eq "1")
    Start-ZirpServices
    $healthy = Test-Health $R
    Set-State @{ CurrentVersion = $target; PreviousVersion = $active }
    Add-History "rolled-back" @{ from = $active; to = $target; database_restored = [bool]$restoreFile; healthy = $healthy }
    if (-not $healthy) { throw "Rolled back to $target but it is not healthy. Log: $RunLog" }
    Write-Host "Zirp $target is active again. $active is still installed; 'zirpctl rollback -To $active' returns to it."
}

function Show-Status {
    $state = Get-State
    Write-Host "Install root : $Root"
    Write-Host "Active       : $(Get-ActiveVersion)"
    Write-Host "Previous     : $($state.PreviousVersion)"
    Write-Host "Role         : $($state.Role)"
    Write-Host "Installed    : $((Get-InstalledVersions) -join ', ')"
    foreach ($name in $AllServices) {
        $s = Get-Service $name -ErrorAction SilentlyContinue
        if ($s) { Write-Host ("  {0,-28} {1}" -f $name, $s.Status) }
    }
    foreach ($task in @($HvxTask, $KioskTask)) {
        $t = Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue
        if ($t) { Write-Host ("  {0,-28} task ({1})" -f $task, $t.State) }
    }
    if ((Get-State).Role -and (Get-RoleInfo (Get-State).Role).Services) {
        try { $h = Invoke-WebRequest "http://127.0.0.1:$(Get-ApiPort)/health/live" -UseBasicParsing -TimeoutSec 5; Write-Host "Health       : $($h.StatusCode)" }
        catch { Write-Host "Health       : not answering" }
    }
}

function Invoke-Uninstall {
    Assert-Admin
    Stop-ZirpServices
    foreach ($name in $AllServices) { Remove-ZirpService $name }
    foreach ($task in @($HvxTask, $KioskTask)) { Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue }
    Get-NetFirewallRule -Group "Zirp" -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue
    if ((Test-Path $Current) -and (Get-Item $Current -Force).LinkType -eq "Junction") { & cmd.exe /c rmdir "`"$Current`"" | Out-Null }
    Remove-Item $RegKey -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item $StateFile -Force -ErrorAction SilentlyContinue
    Add-History "uninstalled" @{}
    Write-Host "Zirp services removed. Site data is kept in $DataDir."
}

try {
    switch ($Command.ToLowerInvariant()) {
        "status" { Show-Status }
        "activate" { Invoke-Activate }
        "rollback" { Invoke-Rollback }
        "backup" {
            Assert-Admin
            Backup-Database $Current ("{0}-{1}" -f (Get-Date -Format "yyyyMMdd-HHmmss"), $Label) | Out-Null
        }
        "services" {
            Assert-Admin
            $state = Get-State
            switch ($Action.ToLowerInvariant()) {
                "start" { Start-ZirpServices }
                "stop" { Stop-ZirpServices }
                "restart" { Stop-ZirpServices; Start-ZirpServices }
                "install" { Install-RoleServices $(if ($state.Role) { $state.Role } else { "COMBINED" }) ($state.HvxAsService -eq "1") }
                "remove" { Stop-ZirpServices; foreach ($n in $AllServices) { Remove-ZirpService $n } }
                default { throw "services start|stop|restart|install|remove" }
            }
        }
        "uninstall" { Invoke-Uninstall }
        "purge-data" {
            Assert-Admin
            if (-not $Force) { throw "purge-data deletes every Zirp database, setting, photo and log on this PC. Add -Force." }
            # Deleting only the files on a PostgreSQL site leaves visit records
            # that point at missing photos. Ask the app what this PC holds first.
            $facts = $null
            if (Test-Path (Join-Path $Current "python64\python.exe")) {
                $py = Join-Path $Current "python64\python.exe"
                Push-Location $Current
                try { $raw = & $py -m app.cli db status 2>$null; $facts = ($raw | Select-Object -Last 1) | ConvertFrom-Json } catch {} finally { Pop-Location }
            }
            if ($facts -and $facts.may_reset_database) {
                Write-Host "This Site Server's visits are in PostgreSQL database '$($facts.database)' on $($facts.host)."
                Write-Host "A factory reset empties that database too (every visit, payment and vehicle of the site)."
                $typed = Read-Host "Type the database name to reset it and delete all data"
                Stop-ZirpServices   # nothing may hold the tables while they are dropped
                Push-Location $Current
                try { $out = & $py -m app.cli db reset --confirm-name $typed 2>&1; $code = $LASTEXITCODE } finally { Pop-Location }
                if ($code -ne 0) { throw "Database not reset; nothing deleted. $($out | Out-String)" }
                Write-Host "Database '$($facts.database)' emptied."
            } elseif ($facts -and $facts.local_photos_referenced_externally) {
                throw "The site database (on $($facts.host)) still references the photos on this PC. Reset the site from its Site Server, or configure shared media, before deleting this PC's data."
            }
            Stop-ZirpServices
            Stop-Transcript | Out-Null
            Remove-Item -LiteralPath $DataDir -Recurse -Force
            Write-Host "Deleted $DataDir"
            exit 0
        }
        default { throw "Unknown command '$Command'. See: Get-Help $PSCommandPath" }
    }
    Stop-Transcript | Out-Null
    exit 0
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    # The installer shows this text in its error box.
    try { Write-TextFile (Join-Path $InstallLogDir "last-error.txt") $_.Exception.Message } catch {}
    Write-Host "Log: $RunLog"
    Stop-Transcript | Out-Null
    exit 1
}
