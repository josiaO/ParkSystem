<#
.SYNOPSIS
    Timed latency capture on the Windows rig. Writes one folder and one zip to send back.

.DESCRIPTION
    Runs tools\latency_capture.py against the running HVX host, samples CPU,
    disk and process load while it runs, copies the latency traces and the
    relevant logs, runs tools\latency_report.py, and zips everything.

    Every scripted pulse PHYSICALLY OPENS THE BOOM on the chosen camera.
    The capture asks you to type OPEN first (unless -NoPulse).

    Output: %USERPROFILE%\Desktop\SmartParkLatency\capture-<date>-<time>\ and
            %USERPROFILE%\Desktop\SmartParkLatency\capture-<date>-<time>.zip

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\windows\Run-LatencyCapture.ps1
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\windows\Run-LatencyCapture.ps1 -Handle 1 -Beep -PassiveSeconds 300
#>
[CmdletBinding()]
param(
    [int]$Handle = -1,
    [int]$Pulses = 5,
    [double]$Spacing = 10,
    [int]$Viewers = 4,
    [double]$PassiveSeconds = 0,
    [switch]$Saturate,
    [switch]$Beep,
    [int]$PollInput = -1,
    [int]$PulseMs = 500,
    [switch]$NoPulse,
    [string]$HostUrl = "http://127.0.0.1:8765",
    [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path ([IO.Path]::Combine($PSScriptRoot, "..", ".."))).Path
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BaseOut = if ($OutDir) { $OutDir } else { Join-Path ([Environment]::GetFolderPath("Desktop")) "SmartParkLatency" }
$Out = Join-Path $BaseOut "capture-$Stamp"
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$Transcript = Join-Path $Out "console.txt"
Start-Transcript -Path $Transcript | Out-Null
$Started = Get-Date

function Find-Python64 {
    $candidates = @()
    if ($env:SMARTPARK_PYTHON) { $candidates += $env:SMARTPARK_PYTHON }
    $candidates += [IO.Path]::Combine($Root, "python64", "python.exe")
    $candidates += [IO.Path]::Combine($Root, ".venv", "Scripts", "python.exe")
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) { return $candidate }
    }
    throw "No 64-bit app Python found (looked for python64\python.exe and .venv\Scripts\python.exe under $Root). Set SMARTPARK_PYTHON to the Python that runs the Site Service."
}

function Get-LogDirs {
    $dirs = @()
    foreach ($base in @($env:PROGRAMDATA, $env:LOCALAPPDATA)) {
        if ($base) {
            $dir = Join-Path $base "SmartParkEdge\logs"
            if (Test-Path $dir) { $dirs += $dir }
        }
    }
    if ($env:SMARTPARK_LATENCY_TRACE_DIR -and (Test-Path $env:SMARTPARK_LATENCY_TRACE_DIR)) { $dirs += $env:SMARTPARK_LATENCY_TRACE_DIR }
    $local = Join-Path $Root "logs"
    if (Test-Path $local) { $dirs += $local }
    return $dirs | Select-Object -Unique
}

try {
    Write-Host "SmartPark latency capture -> $Out"
    $Python = Find-Python64
    Write-Host "Python: $Python"

    # 1. The host must be running the instrumented code.
    try {
        Invoke-RestMethod -Uri "$HostUrl/metrics" -TimeoutSec 5 | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $Out "metrics-before.json") -Encoding UTF8
    } catch {
        throw "The HVX host at $HostUrl has no /metrics endpoint (old code or not running). Update the checkout, restart the SmartParkHvxHost service (or the host window), then run this again. Error: $($_.Exception.Message)"
    }

    # 2. Machine facts that bear on H7 (CPU/disk starvation). Read-only.
    $system = [ordered]@{}
    try {
        $os = Get-CimInstance Win32_OperatingSystem
        $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
        $system.os = "$($os.Caption) $($os.Version) build $($os.BuildNumber)"
        $system.cpu = "$($cpu.Name) cores=$($cpu.NumberOfCores) logical=$($cpu.NumberOfLogicalProcessors)"
        $system.ram_gb = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
        $system.free_ram_gb = [math]::Round($os.FreePhysicalMemory / 1MB, 1)
    } catch { $system.system_error = $_.Exception.Message }
    try { $system.power_plan = (powercfg /getactivescheme) -join " " } catch { }
    try {
        $mp = Get-MpComputerStatus
        $system.defender_realtime = $mp.RealTimeProtectionEnabled
        $system.defender_exclusions_readable = $true
    } catch { $system.defender_realtime = "unknown" }
    try {
        $system.services = @(Get-Service -Name "SmartPark*" -ErrorAction SilentlyContinue | ForEach-Object { "$($_.Name)=$($_.Status)" })
    } catch { }
    $system.python = $Python
    $system.root = $Root
    try { $system.git_head = (& git -C $Root rev-parse --short HEAD 2>$null) } catch { }
    $system | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $Out "system.json") -Encoding UTF8

    # 3. Background load sampling while the capture runs.
    $countersFile = Join-Path $Out "counters.csv"
    $processesFile = Join-Path $Out "processes.csv"
    $sampler = Start-Job -ArgumentList $countersFile, $processesFile -ScriptBlock {
        param($countersFile, $processesFile)
        "time,cpu_total_pct,available_mb,disk_time_pct,processor_queue" | Set-Content $countersFile
        "time,name,id,cpu_seconds,working_set_mb,threads" | Set-Content $processesFile
        $paths = @('\Processor(_Total)\% Processor Time', '\Memory\Available MBytes', '\PhysicalDisk(_Total)\% Disk Time', '\System\Processor Queue Length')
        while ($true) {
            $now = (Get-Date).ToString("o")
            try {
                $values = (Get-Counter -Counter $paths -ErrorAction Stop).CounterSamples | ForEach-Object { [math]::Round($_.CookedValue, 1) }
                "$now,$($values -join ',')" | Add-Content $countersFile
            } catch { "$now,counter-error,,," | Add-Content $countersFile }
            Get-Process -Name python, pythonw, mediamtx, ffmpeg, MsMpEng -ErrorAction SilentlyContinue | ForEach-Object {
                "$now,$($_.ProcessName),$($_.Id),$([math]::Round($_.CPU, 1)),$([math]::Round($_.WorkingSet64 / 1MB, 1)),$($_.Threads.Count)" | Add-Content $processesFile
            }
            Start-Sleep -Seconds 2
        }
    }

    # 4. The scripted capture (asks you to type OPEN before pulsing the boom).
    $captureArgs = @([IO.Path]::Combine($Root, "tools", "latency_capture.py"), "--host-url", $HostUrl, "--out", $Out,
        "--pulses", $Pulses, "--spacing", $Spacing, "--viewers", $Viewers, "--pulse-ms", $PulseMs,
        "--passive-seconds", $PassiveSeconds)
    if ($Handle -ge 0) { $captureArgs += @("--handle", $Handle) }
    if ($Saturate) { $captureArgs += "--saturate" }
    if ($Beep) { $captureArgs += "--beep" }
    if ($PollInput -ge 0) { $captureArgs += @("--poll-input", $PollInput) }
    if ($NoPulse) { $captureArgs += "--no-pulse" }
    Write-Host "Running: $Python $($captureArgs -join ' ')"
    & $Python @captureArgs
    $captureExit = $LASTEXITCODE

    Stop-Job $sampler | Out-Null
    Remove-Job $sampler -Force | Out-Null

    # 5. Collect traces and logs written since the capture started.
    $logsOut = Join-Path $Out "logs"
    New-Item -ItemType Directory -Force -Path $logsOut | Out-Null
    $since = $Started.AddMinutes(-2)
    foreach ($dir in Get-LogDirs) {
        $tag = ($dir -replace '[:\\/ ]', '_').Trim('_')
        Get-ChildItem -Path $dir -Filter "latency-trace-*.jsonl*" -ErrorAction SilentlyContinue |
            Where-Object { $_.LastWriteTime -ge $since } |
            ForEach-Object { Copy-Item $_.FullName (Join-Path $logsOut "$tag--$($_.Name)") }
        foreach ($name in @("hvx-host.log", "site-service.log", "recognition-worker.log", "media-service.log")) {
            $file = Join-Path $dir $name
            if (Test-Path $file) {
                Get-Content $file -Tail 4000 | Set-Content (Join-Path $logsOut "$tag--$name.tail.txt") -Encoding UTF8
            }
        }
    }
    try {
        Invoke-RestMethod -Uri "$HostUrl/metrics" -TimeoutSec 5 | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $Out "metrics-after.json") -Encoding UTF8
    } catch { "metrics after capture unavailable: $($_.Exception.Message)" | Set-Content (Join-Path $Out "metrics-after.txt") }

    # 6. Report (the trace files in the capture folder plus the copied logs).
    # Out-File -Encoding utf8: Windows PowerShell's ">" would write UTF-16.
    & $Python ([IO.Path]::Combine($Root, "tools", "latency_report.py")) $Out "--json" (Join-Path $Out "report.json") | Out-File -FilePath (Join-Path $Out "report.txt") -Encoding utf8
    Write-Host ""
    Get-Content (Join-Path $Out "report.txt") -TotalCount 60
    if ($captureExit -ne 0) { Write-Warning "latency_capture.py exited with $captureExit (see console.txt)." }
}
finally {
    Stop-Transcript | Out-Null
    $zip = "$Out.zip"
    if (Test-Path $zip) { Remove-Item $zip -Force }
    Compress-Archive -Path (Join-Path $Out "*") -DestinationPath $zip
    Write-Host ""
    Write-Host "Send this file back: $zip"
}
