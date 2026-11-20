<#
.SYNOPSIS
    Payment kiosk runner (started hidden at sign-in of the kiosk account by the "Zirp Kiosk" task).
    Starts the Zirp desktop full screen in kiosk mode and starts it again if it is closed or crashes.
#>
$ErrorActionPreference = "Continue"
$root = Join-Path (Split-Path -Parent $PSScriptRoot) "current"
$pythonw = Join-Path $root "python64\pythonw.exe"
$log = Join-Path $env:ProgramData "SmartParkEdge\logs\kiosk-runner.log"
$env:SMARTPARK_STATION = "KIOSK"
$env:SMARTPARK_ROLE_LOCKED = "OPERATOR_CLIENT"
$env:SMARTPARK_DEPLOYMENT_PROFILE = "PRODUCTION"
$failures = 0
while ($true) {
    if (-not (Test-Path $pythonw)) {
        Add-Content $log "$(Get-Date -Format o) missing $pythonw; waiting"
        Start-Sleep -Seconds 30
        continue
    }
    $started = Get-Date
    $p = Start-Process -FilePath $pythonw -ArgumentList "-m", "app.desktop.launch" -WorkingDirectory $root -PassThru -Wait
    $ran = ((Get-Date) - $started).TotalSeconds
    Add-Content $log "$(Get-Date -Format o) kiosk desktop exited code=$($p.ExitCode) after $([int]$ran) s"
    # Quick crashes back off so a broken install does not spin the CPU.
    if ($ran -lt 30) { $failures++ } else { $failures = 0 }
    Start-Sleep -Seconds ([Math]::Min(60, 3 + 5 * $failures))
}
