@echo off
setlocal
cd /d "%~dp0"
echo SmartPark server diagnostics
echo This captures installed build, scheduled tasks, listening ports, HTTP health, and recent logs.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-ServerDiagnostics.ps1" %*
set ERR=%ERRORLEVEL%
echo.
if %ERR% NEQ 0 echo Diagnostics failed with exit code %ERR%.
echo Send the generated SmartPark-ServerDiagnostics-*.zip from %%TEMP%% to support.
pause
exit /b %ERR%
