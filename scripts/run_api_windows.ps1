$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
& .\.venv\Scripts\python.exe -m uvicorn app.api_main:app --host 127.0.0.1 --port 8760
