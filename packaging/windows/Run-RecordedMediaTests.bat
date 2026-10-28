@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-RecordedMediaTests.ps1" %*
if errorlevel 1 (
  echo.
  echo Recorded-media tests failed to run. Keep the console output and check the Zirp logs.
  pause
  exit /b 1
)
pause
