@echo off
setlocal
cd /d "%~dp0"
echo SmartPark camera lab
echo.
echo SmartPark must already be open. This window only watches the cameras.
echo It does not open the gate, print a ticket, or create a parking session.
echo.
echo Double-click            = all cameras, 15 minutes
echo Run-CameraLab.bat -Camera 1 -Duration 600   = camera 1, 10 minutes
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-CameraLab.ps1" %*
set ERR=%ERRORLEVEL%
echo.
if %ERR% EQU 0 (
  echo RESULT: PASS
) else if %ERR% EQU 2 (
  echo RESULT: DEGRADED. Send the log file.
) else (
  echo RESULT: FAIL. Send the log file.
)
echo Log folder: %ProgramData%\SmartParkEdge\logs\
pause
exit /b %ERR%
