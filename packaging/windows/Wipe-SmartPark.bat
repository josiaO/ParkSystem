@echo off
setlocal
cd /d "%~dp0"
echo SmartPark factory reset
echo This deletes the database, media, logs, FastALPR cache, and the installed app.
echo Stopping the Desktop window is not enough.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Wipe-SmartPark.ps1" %*
set ERR=%ERRORLEVEL%
if %ERR% NEQ 0 (
  echo.
  echo Wipe did not finish. Close SmartPark Edge and run this again as Administrator if files stay locked.
  pause
  exit /b %ERR%
)
echo.
pause
exit /b 0
