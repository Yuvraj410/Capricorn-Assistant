@echo off
setlocal EnableExtensions
rem ============================================================================
rem  Edit permissions
rem  Opens permissions.yaml (what Capri may open, browser choice). Capri restarts when you close Notepad.
rem ============================================================================
cd /d "%~dp0.."
if exist "%CD%\capricon-data\" powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\migrate_name.ps1"
set "PY=%CD%\capricorn-data\python\Scripts\python.exe"
if not exist "%PY%" (
  echo Capricorn isn't installed yet - run Setup.exe first.
  pause
  exit /b 1
)
if not exist "capricorn-data\permissions.yaml" "%PY%" -m capricorn --get ui.scale >nul
notepad "capricorn-data\permissions.yaml"
powershell -NoProfile -Command "if (Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' or Name='python.exe' or Name='Capricorn.exe'\" | Where-Object { ($_.Name -eq 'Capricorn.exe' -or $_.CommandLine -like '*-m capri*') }) { exit 0 } else { exit 1 }" >nul 2>&1
if not errorlevel 1 (
  echo Restarting Capricorn so the change takes effect...
  powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' or Name='python.exe' or Name='Capricorn.exe'\" | Where-Object { ($_.Name -eq 'Capricorn.exe' -or $_.CommandLine -like '*-m capri*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
  timeout /t 1 /nobreak >nul
  start "" "%CD%\Capricorn.bat"
)
