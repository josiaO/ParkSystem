@echo off
rem Close and start the Zirp desktop app again (runs from this project folder).
rem Add -Installed after the .ps1 path to start the installed copy instead.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\windows\zirp-desktop.ps1" %*
