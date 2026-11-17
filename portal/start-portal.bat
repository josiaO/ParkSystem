@echo off
setlocal
cd /d "%~dp0"
rem Zirp portal (public pay page + back office).
rem   start-portal.bat                         build if needed, then start on port 3000
rem   start-portal.bat --api http://host:8760  point at another Zirp server first
rem   start-portal.bat --rebuild               rebuild after updating the code

where node >nul 2>nul
if errorlevel 1 (
  if exist "%ProgramFiles%\nodejs\node.exe" (set "PATH=%ProgramFiles%\nodejs;%PATH%") else (
    echo Node.js 20 or newer is required: winget install OpenJS.NodeJS.LTS
    pause
    exit /b 1
  )
)

set "REBUILD="
set "APIARG="
:args
if "%~1"=="" goto run
if /i "%~1"=="--rebuild" set "REBUILD=1"
if /i "%~1"=="--api" (set "APIARG=--api %~2" & shift)
shift
goto args

:run
call node scripts\check-env.mjs %APIARG%
if not exist node_modules (call npm ci --no-audit --no-fund || exit /b 1)
if defined REBUILD (call npm run build || exit /b 1)
if not exist .next\BUILD_ID (call npm run build || exit /b 1)
if "%PORT%"=="" set "PORT=3000"
echo.
echo Portal: http://localhost:%PORT%   (pay page: /p/^<ticket code^>, back office: /admin)
call npx next start -p %PORT%
