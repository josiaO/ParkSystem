$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Test-Url($url) {
    try {
        Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2 | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Find-Python32 {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) { return $null }
    foreach ($spec in @("-3.11-32", "-3.12-32", "-3.10-32", "-3-32")) {
        try {
            $bits = & py $spec -c "import struct; print(struct.calcsize('P') * 8)" 2>$null
            if ("$bits".Trim() -eq "32") { return $spec }
        } catch {}
    }
    return $null
}

$hvxInfo = "http://127.0.0.1:8765/info"
if (-not (Test-Url $hvxInfo)) {
    $py32 = Find-Python32
    if ($py32) {
        Write-Host "Starting 32-bit HVX SDK host..."
        Start-Process -FilePath "py" -ArgumentList @($py32, "tools\hvx_sdk_host\hvx_host.py") -WorkingDirectory $root
        $ready = $false
        for ($i = 0; $i -lt 30; $i++) {
            if (Test-Url $hvxInfo) { $ready = $true; break }
            Start-Sleep -Milliseconds 300
        }
        if (-not $ready) {
            Write-Warning "HVX host did not answer $hvxInfo yet. SDK Connect will fail until it does."
        }
    } else {
        Write-Warning "No 32-bit Python found (py -3.11-32). SDK login needs that host. API/UI will still start."
    }
} else {
    Write-Host "HVX SDK host already running."
}

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Missing .venv. Create it with: py -3.11 -m venv .venv ; .\.venv\Scripts\Activate.ps1 ; pip install -r requirements.txt"
}

Write-Host "Starting SmartPark API at http://127.0.0.1:8760"
Write-Host "Sign in as admin / SmartPark1!"
Write-Host "Then: Discover or Add site cameras, then Connect all."

Start-Job -ScriptBlock {
    for ($i = 0; $i -lt 40; $i++) {
        try {
            Invoke-WebRequest -Uri "http://127.0.0.1:8760/health" -UseBasicParsing -TimeoutSec 2 | Out-Null
            Start-Process "http://127.0.0.1:8760"
            return
        } catch {
            Start-Sleep -Milliseconds 250
        }
    }
} | Out-Null

& $python -m uvicorn app.api_main:app --host 127.0.0.1 --port 8760
