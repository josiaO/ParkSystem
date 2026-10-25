@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-SmartPark.ps1"
set "INSTALL_RESULT=%ERRORLEVEL%"
if not "%INSTALL_RESULT%"=="0" echo Installation failed. See the PowerShell error and SmartPark-install logs in %%TEMP%%.
pause
exit /b %INSTALL_RESULT%
