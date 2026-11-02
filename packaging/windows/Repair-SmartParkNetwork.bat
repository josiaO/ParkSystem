@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Repair-SmartParkNetwork.ps1" %*
if errorlevel 1 (
  echo.
  echo Network repair failed. Re-run this file with Run as administrator.
)
pause
