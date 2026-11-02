@echo off
rem Updates Capricorn's Python packages after you pull new code (settings and models are kept).
cd /d "%~dp0"
if exist "%CD%\capricon-data\" powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\migrate_name.ps1"
if not exist "capricorn-data\python\Scripts\python.exe" (
  echo Capricorn isn't set up yet - run Setup.exe.
  pause
  exit /b 1
)
echo [....] Closing Capricorn if it's running
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' or Name='python.exe' or Name='Capricorn.exe'\" | Where-Object { ($_.Name -eq 'Capricorn.exe' -or $_.CommandLine -like '*-m capri*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
echo [....] Updating packages
"capricorn-data\python\Scripts\python.exe" -m pip install -r requirements.txt --quiet --upgrade
if errorlevel 1 (
  echo [FAIL] Update failed - check your internet connection.
  pause
  exit /b 1
)
echo [ OK ] Updated. Starting Capricorn...
start "" "%~dp0Capricorn.bat"
timeout /t 3 >nul
