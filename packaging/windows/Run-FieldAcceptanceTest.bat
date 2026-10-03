@echo off
setlocal
cd /d "%~dp0"
echo SmartPark field acceptance test
echo Leave this window open and send cars through the lanes.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-FieldAcceptanceTest.ps1" %*
set ERR=%ERRORLEVEL%
if %ERR% NEQ 0 (
  echo.
  echo RESULT: FAIL or could not reach Site Service. See %%ProgramData%%\SmartParkEdge\logs\
  pause
  exit /b %ERR%
)
echo.
echo RESULT: PASS or WARN. Report saved under %%ProgramData%%\SmartParkEdge\logs\
pause
exit /b 0
