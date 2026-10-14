@echo off
setlocal
cd /d "%~dp0"
echo SmartPark startup check
echo Start SmartPark first. This window watches video, runs recognition, and dry-runs the gate.
echo The barrier is not opened.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-StartupCheck.ps1" %*
set ERR=%ERRORLEVEL%
if %ERR% NEQ 0 (
  echo.
  echo RESULT: FAIL. See %%ProgramData%%\SmartParkEdge\logs\startup_check_*.txt
  pause
  exit /b %ERR%
)
echo.
echo RESULT: PASS or WARN. Report saved under %%ProgramData%%\SmartParkEdge\logs\
pause
exit /b 0
