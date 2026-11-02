@echo off
setlocal EnableExtensions
rem ============================================================================
rem  Start Capricorn
rem  Starts Capri hidden in the tray (same as Capricorn.bat). Only one copy ever runs.
rem ============================================================================
cd /d "%~dp0.."
if exist "%CD%\capricon-data\" powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\migrate_name.ps1"
set "PY=%CD%\capricorn-data\python\Scripts\python.exe"
if not exist "%PY%" (
  echo Capricorn isn't installed yet - run Setup.exe first.
  pause
  exit /b 1
)
start "" "%CD%\Capricorn.bat"
echo Capricorn started - look for the icon in the tray, then say "Hey Capri".
timeout /t 3 >nul
