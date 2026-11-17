@echo off
setlocal
cd /d "%~dp0"
echo Mock ClickPesa: test payments only, no real money.
echo Phone simulator: http://THIS-PC:9100/phone   Faults: http://THIS-PC:9100/admin
echo First time: SmartPark-Settings.bat preset mock-payments --lan-ip ^<this PC IP^> --restart
echo.
"%~dp0python64\python.exe" -m app.mock_services.clickpesa --host 0.0.0.0 %*
pause
