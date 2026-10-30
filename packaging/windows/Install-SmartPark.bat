@echo off
setlocal
cd /d "%~dp0"
choice /C SCNP /N /D P /T 10 /M "Install role: [S] Site Server [C] Operator Workstation [N] Processing Node [P] Preserve existing role (default P): "
if errorlevel 4 set "SMARTPARK_ROLE="
if errorlevel 3 if not errorlevel 4 set "SMARTPARK_ROLE=EDGE_NODE"
if errorlevel 2 if not errorlevel 3 set "SMARTPARK_ROLE=OPERATOR_CLIENT"
if errorlevel 1 if not errorlevel 2 set "SMARTPARK_ROLE=SITE_SERVER"
if defined SMARTPARK_ROLE (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-SmartPark.ps1" -Role "%SMARTPARK_ROLE%"
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-SmartPark.ps1"
)
set "INSTALL_RESULT=%ERRORLEVEL%"
if not "%INSTALL_RESULT%"=="0" echo Installation failed. See the PowerShell error and SmartPark-install logs in %%TEMP%%.
pause
exit /b %INSTALL_RESULT%
