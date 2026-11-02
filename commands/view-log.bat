@echo off
setlocal EnableExtensions
rem ============================================================================
rem  Live log
rem  Follows capricorn.log live: what Capri heard, which rule or AI reply she used, errors. Ctrl+C to stop.
rem ============================================================================
cd /d "%~dp0.."
if exist "%CD%\capricon-data\" powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\migrate_name.ps1"
set "PY=%CD%\capricorn-data\python\Scripts\python.exe"
if not exist "%PY%" (
  echo Capricorn isn't installed yet - run Setup.exe first.
  pause
  exit /b 1
)
if not exist "capricorn-data\logs\capricorn.log" (echo No log yet - start Capricorn first. & pause & exit /b 0)
powershell -NoProfile -Command "Get-Content -Path 'capricorn-data\logs\capricorn.log' -Tail 40 -Wait"
