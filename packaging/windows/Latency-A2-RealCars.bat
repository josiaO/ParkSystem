@echo off
setlocal
rem 15 minutes of real cars, recognition and display staleness
rem Double-click this file. It asks for administrator rights by itself.
net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
  echo Asking for administrator rights...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b 0
)
cd /d "%~dp0"
title SmartPark latency test A2
echo SmartPark latency test A2: 15 minutes of real cars, recognition and display staleness
echo The script does not open the boom. Drive the cars through the lane.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-LatencyTest.ps1" -Test A2 %*
set ERR=%ERRORLEVEL%
echo.
if %ERR% NEQ 0 echo The test ended with an error (code %ERR%). Send a screenshot of this window back.
pause
exit /b %ERR%
