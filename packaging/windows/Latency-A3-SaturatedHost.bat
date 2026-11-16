@echo off
setlocal
rem Saturated HVX host (optional)
rem Double-click this file. It asks for administrator rights by itself.
net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
  echo Asking for administrator rights...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b 0
)
cd /d "%~dp0"
title SmartPark latency test A3
echo SmartPark latency test A3: Saturated HVX host (optional)
echo THIS OPENS THE BOOM 3 TIMES, POSSIBLY LATE. Keep the lane clear.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-LatencyTest.ps1" -Test A3 %*
set ERR=%ERRORLEVEL%
echo.
if %ERR% NEQ 0 echo The test ended with an error (code %ERR%). Send a screenshot of this window back.
pause
exit /b %ERR%
