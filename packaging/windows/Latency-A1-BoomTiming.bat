@echo off
setlocal
rem Boom timing, with and without live viewers
rem Double-click this file. It asks for administrator rights by itself.
net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
  echo Asking for administrator rights...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b 0
)
cd /d "%~dp0"
title SmartPark latency test A1
echo SmartPark latency test A1: Boom timing, with and without live viewers
echo THIS OPENS THE BOOM 10 TIMES. Keep the lane clear.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-LatencyTest.ps1" -Test A1 %*
set ERR=%ERRORLEVEL%
echo.
if %ERR% NEQ 0 echo The test ended with an error (code %ERR%). Send a screenshot of this window back.
pause
exit /b %ERR%
