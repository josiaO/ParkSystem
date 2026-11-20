@echo off
rem Close and start the Zirp desktop app again (runs from this project checkout).
rem Pass -Installed to start the installed copy instead.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0zirp-desktop.ps1" %*
