@echo off
setlocal
where py >nul 2>&1 || (echo Python launcher not found. Install 32-bit Python and the py launcher. & exit /b 1)
for %%S in (-3.11-32 -3.12-32 -3.10-32 -3-32) do (
  py %%S -c "import struct,sys; sys.exit(0 if struct.calcsize('P')*8==32 else 1)" >nul 2>&1
  if not errorlevel 1 (
    echo Using 32-bit Python: py %%S
    py %%S "%~dp0hvx_host.py"
    exit /b %ERRORLEVEL%
  )
)
echo A 32-bit Python is required to load NetSDK.dll.
echo Install Python 3.11 32-bit and confirm with:
echo   py -3.11-32 -c "import struct; print(struct.calcsize('P')*8)"
exit /b 1
