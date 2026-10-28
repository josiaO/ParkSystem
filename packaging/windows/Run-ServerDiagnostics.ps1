#requires -Version 5.1
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

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$out = Join-Path $env:TEMP "SmartPark-ServerDiagnostics-$stamp"
New-Item -ItemType Directory -Path $out -Force | Out-Null
$logOut = Join-Path $out "logs"
New-Item -ItemType Directory -Path $logOut -Force | Out-Null
$summary = New-Object System.Collections.Generic.List[string]

function Add-Summary([string]$line) {
    $summary.Add($line)
    Write-Host $line
}

function Save-Text([string]$name, [string]$text) {
    $path = Join-Path $out $name
    $text | Out-File -FilePath $path -Encoding UTF8
}

function Save-File([string]$source, [string]$name) {
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $out $name) -Force
    }
}

function Redact-DiagnosticText([string]$text) {
    if ($null -eq $text) { return "" }
    $text = [regex]::Replace($text, '(?im)("(?:password|secret|token|api_key|apikey)"\s*[:=]\s*")[^"]*(")', '$1[REDACTED]$2')
    $text = [regex]::Replace($text, '(?im)((?:password|secret|token|api[_-]?key)\s*[:=]\s*)[^\s,;]+', '$1[REDACTED]')
    $text = [regex]::Replace($text, '(?i)(rtsp://[^:/\s]+:)[^@/\s]+(@)', '$1[REDACTED]$2')
    return $text
}

function Get-ProcessDescription([int]$processId) {
    try {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $processId"
        if ($null -ne $process) {
            return "PID=$processId Name=$($process.Name) CommandLine=$($process.CommandLine)"
        }
    } catch {
        return "PID=$processId process lookup failed: $($_.Exception.Message)"
    }
    return "PID=$processId process not found"
}

function Probe-Http([string]$name, [string]$url) {
    $file = "http-$name.txt"
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 4
        $body = [string]$response.Content
        if ($body.Length -gt 4000) { $body = $body.Substring(0, 4000) }
        $text = "URL: $url`r`nSTATUS: $($response.StatusCode)`r`nBODY:`r`n$body"
        Save-Text $file $text
        Add-Summary "HTTP PASS $url [$($response.StatusCode)]"
        return $true
    } catch {
        $message = $_.Exception.Message
        Save-Text $file "URL: $url`r`nERROR: $message"
        Add-Summary "HTTP FAIL $url [$message]"
        return $false
    }
}

Add-Summary "SmartPark server diagnostics: $stamp"
Add-Summary "InstallDir: $InstallDir"
Add-Summary "Computer: $env:COMPUTERNAME  User: $env:USERNAME"
Save-Text "README.txt" @"
Zirp diagnostics bundle
=======================
Created: $stamp

Send this entire ZIP when reporting a camera, streaming, recognition, or
startup problem. The bundle contains redacted service logs, runtime health
probes, scheduled-task state, port ownership, process/resource snapshots, and
recent Windows Application errors.

The deployment JSON and logs are filtered for common passwords, tokens,
secrets, API keys, and RTSP credentials. Review the files before sharing if
your site uses custom identifiers or private IP addresses.

Useful files:
  summary.txt              first triage result
  logs/*                   recent service and crash logs
  http-*.txt               health/control endpoint responses
  process-snapshot.txt     command lines, memory, and CPU snapshots
  ports.txt                listener ownership for Site/HVX/MediaMTX
  windows-application-errors.txt  recent matching Windows event records
"@
try {
    $os = Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber, OSArchitecture, LastBootUpTime
    $computer = Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer, Model, TotalPhysicalMemory, NumberOfLogicalProcessors
    Save-Text "system.txt" (("===== Operating system =====`r`n" + ($os | Format-List | Out-String)) + ("===== Computer =====`r`n" + ($computer | Format-List | Out-String)))
} catch {
    Save-Text "system.txt" "System inventory failed: $($_.Exception.Message)"
}
Save-File (Join-Path $InstallDir "BUILD-INFO.txt") "BUILD-INFO.txt"
Save-File (Join-Path $InstallDir "payload\BUILD-INFO.txt") "payload-BUILD-INFO.txt"

$Py64 = Join-Path $InstallDir "python64\python.exe"
if (Test-Path -LiteralPath $Py64) {
    $env:SMARTPARK_HOME = $InstallDir
    $env:PATH = "$InstallDir\python64;$InstallDir\python64\Scripts;$InstallDir\vendor;$env:PATH"
    $ortImport = & $Py64 -c "import onnxruntime as ort; print(ort.__version__)" 2>&1 | Out-String
    Save-Text "onnxruntime-import.txt" $ortImport
    if ($LASTEXITCODE -eq 0) {
        Add-Summary "ONNX Runtime import PASS: $($ortImport.Trim())"
    } else {
        Add-Summary "ONNX Runtime import FAIL: $($ortImport.Trim())"
    }
} else {
    Add-Summary "ONNX Runtime import SKIPPED: bundled Python was not found."
}

$deploymentPaths = @(
    (Join-Path $env:ProgramData "SmartParkEdge\deployment.json"),
    (Join-Path $env:ProgramData "SmartParkEdge\config\deployment.json"),
    (Join-Path $InstallDir "config\deployment.json"),
    (Join-Path $InstallDir "payload\config\deployment.json")
)
foreach ($deploymentPath in $deploymentPaths) {
    if (Test-Path -LiteralPath $deploymentPath) {
        $safeName = "deployment-" + ([IO.Path]::GetFileNameWithoutExtension($deploymentPath)) + ".json"
        $deploymentText = Get-Content -LiteralPath $deploymentPath -Raw
        # Keep diagnostics safe to share even if a future config adds credentials.
        $deploymentText = [regex]::Replace($deploymentText, '(?im)("(?:password|secret|token|api_key|apikey)"\s*:\s*")[^"]*(")', '$1[REDACTED]$2')
        Save-Text $safeName $deploymentText
        Add-Summary "Deployment config found: $deploymentPath"
    }
}

$taskNames = @(
    "SmartPark Site Service",
    "SmartPark HVX Host",
    "SmartPark Media Service",
    "SmartPark Recognition Worker"
)
$taskReport = New-Object System.Collections.Generic.List[string]
foreach ($taskName in $taskNames) {
    $taskReport.Add("===== $taskName =====")
    try {
        $task = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
        $info = Get-ScheduledTaskInfo -TaskName $taskName -ErrorAction SilentlyContinue
        $taskReport.Add("State: $($task.State)")
        $taskReport.Add("Principal: $($task.Principal.UserId)  LogonType: $($task.Principal.LogonType)  RunLevel: $($task.Principal.RunLevel)")
        foreach ($action in $task.Actions) {
            $taskReport.Add("Action: Execute=$($action.Execute) Arguments=$($action.Arguments) WorkingDirectory=$($action.WorkingDirectory)")
        }
        if ($null -ne $info) {
            $taskReport.Add("LastRunTime: $($info.LastRunTime)  LastTaskResult: $($info.LastTaskResult)  NextRunTime: $($info.NextRunTime)")
        }
        $lastResult = if ($null -ne $info) { [string]$info.LastTaskResult } else { "unknown" }
        Add-Summary "TASK ${taskName}: state=$($task.State) result=$lastResult"
    } catch {
        $taskReport.Add("NOT FOUND/ACCESS ERROR: $($_.Exception.Message)")
        Add-Summary "TASK ${taskName}: unavailable"
    }
}
Save-Text "scheduled-tasks.txt" ($taskReport -join "`r`n")

$portReport = New-Object System.Collections.Generic.List[string]
$ports = @(8760, 8765, 8554, 9997, 9998)
foreach ($port in $ports) {
    $portReport.Add("===== TCP $port =====")
    try {
        $connections = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction Stop)
        if ($connections.Count -eq 0) { $portReport.Add("NOT LISTENING") }
        foreach ($connection in $connections) {
            $description = Get-ProcessDescription ([int]$connection.OwningProcess)
            $portReport.Add("Local=$($connection.LocalAddress):$($connection.LocalPort) PID=$($connection.OwningProcess) $description")
        }
    } catch {
        $portReport.Add("Lookup failed or not listening: $($_.Exception.Message)")
    }
}
Save-Text "ports.txt" ($portReport -join "`r`n")

$siteOk = Probe-Http "site-health" "http://127.0.0.1:8760/health/live"
$deploymentOk = Probe-Http "site-deployment" "http://127.0.0.1:8760/deployment/info"
$hvxOk = Probe-Http "hvx-info" "http://127.0.0.1:8765/info"
$mediaOk = Probe-Http "mediamtx-control" "http://127.0.0.1:9997/v3/config/global/get"

$logRoots = @(
    (Join-Path $env:ProgramData "SmartParkEdge\logs"),
    (Join-Path $InstallDir "logs")
)
$logNames = @(
    "site-service.log", "site-service-launch.log", "launch.log", "crash-SmartParkSiteService.log",
    "crash-SmartParkRecognitionWorker.log",
    "hvx-host.log", "media-service.log", "media-service-launch.log",
    "recognition-worker.log", "recognition-worker-launch.log", "crash-SmartParkMediaService.log"
)
foreach ($root in ($logRoots | Select-Object -Unique)) {
    $sources = @(Get-ChildItem -LiteralPath $root -File -ErrorAction SilentlyContinue | Where-Object {
        $_.Extension -in @('.log', '.txt') -or $_.Name -like 'crash-*'
    })
    foreach ($source in $sources) {
        $safeRoot = if ($root -like "*$env:ProgramData*") { "programdata" } else { "install" }
        $destination = Join-Path $logOut "$safeRoot-$($source.Name)"
        $tail = Get-Content -LiteralPath $source.FullName -Tail 1000 -Raw
        Redact-DiagnosticText $tail | Out-File -FilePath $destination -Encoding UTF8
    }
}

try {
    $processes = Get-Process | Where-Object {
        $_.ProcessName -match 'python|mediamtx|ffmpeg|SmartPark|Zirp'
    } | Sort-Object ProcessName | Select-Object Id, ProcessName, CPU, PM, WS, StartTime, Path
    Save-Text "process-snapshot.txt" ($processes | Format-List | Out-String)
} catch {
    Save-Text "process-snapshot.txt" "Process inventory failed: $($_.Exception.Message)"
}

try {
    $events = Get-WinEvent -LogName Application -MaxEvents 300 -ErrorAction Stop | Where-Object {
        $_.ProviderName -match 'Application Error|Windows Error Reporting|Python|Zirp|SmartPark|FFmpeg|MediaMTX'
    } | Select-Object TimeCreated, ProviderName, Id, LevelDisplayName, Message
    Save-Text "windows-application-errors.txt" ($events | Format-List | Out-String)
} catch {
    Save-Text "windows-application-errors.txt" "Windows Application event lookup failed: $($_.Exception.Message)"
}

if (-not $siteOk) {
    Add-Summary "PRIMARY FAILURE: Site API 8760 is unavailable. Desktop WinError 10061 is expected until the Site Service task starts and stays running."
} elseif (-not $hvxOk) {
    Add-Summary "HVX FAILURE: Site API 8760 is healthy, but HVX host 8765 is unavailable."
} elseif (-not $deploymentOk) {
    Add-Summary "DEPLOYMENT FAILURE: Site API is alive but deployment metadata endpoint failed."
} else {
    Add-Summary "CORE SERVICES PASS: Site API 8760 and HVX host 8765 responded."
    if (-not $mediaOk) { Add-Summary "MEDIA WARNING: MediaMTX control endpoint 9997 is unavailable." }
    Add-Summary "If the desktop still shows WinError, run Run-StartupCheck.bat and inspect the desktop build/version against BUILD-INFO.txt."
}

Save-Text "summary.txt" ($summary -join "`r`n")
$archive = "$out.zip"
Compress-Archive -Path (Join-Path $out "*") -DestinationPath $archive -Force
Write-Host ""
Write-Host "Diagnostics saved to: $archive"
