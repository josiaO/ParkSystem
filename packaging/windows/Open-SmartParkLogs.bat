@echo off
setlocal
set "LOGDIR=%ProgramData%\SmartParkEdge\logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
start "" explorer.exe "%LOGDIR%"
