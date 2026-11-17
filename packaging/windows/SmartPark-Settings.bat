@echo off
setlocal
cd /d "%~dp0"
rem Zirp settings (.env). Examples:
rem   SmartPark-Settings.bat                       show settings you changed
rem   SmartPark-Settings.bat list --filter payment
rem   SmartPark-Settings.bat set SITE_NAME="Rock City Mall" --restart
rem   SmartPark-Settings.bat preset mock-payments --lan-ip 192.168.1.240
rem   SmartPark-Settings.bat check
if "%~1"=="" (
  "%~dp0python64\python.exe" -m app.cli env list --changed
  echo.
  echo Use: SmartPark-Settings.bat list ^| get NAME ^| set NAME=VALUE ^| unset NAME ^| check ^| preset mock-payments
  pause
  exit /b 0
)
"%~dp0python64\python.exe" -m app.cli env %*
