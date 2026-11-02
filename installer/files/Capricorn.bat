@echo off
rem Starts Capricorn in the background (no console window). Safe to run twice - only one copy runs.
cd /d "%~dp0"
if exist "%CD%\capricon-data\" powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\migrate_name.ps1"
if not exist "capricorn-data\python\Scripts\pythonw.exe" (
  echo Capricorn isn't set up yet - starting Setup.exe.
  start "" "%~dp0Setup.exe"
  exit /b
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\install_launcher.ps1" >nul 2>&1
if exist "capricorn-data\python\Scripts\Capricorn.exe" (
  start "" "capricorn-data\python\Scripts\Capricorn.exe"
) else (
  start "" "capricorn-data\python\Scripts\pythonw.exe" -m capricorn
)
