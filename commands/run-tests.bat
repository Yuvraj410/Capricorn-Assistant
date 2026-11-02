@echo off
setlocal EnableExtensions
rem ============================================================================
rem  Run tests
rem  Runs the automated test suite (for developers).
rem ============================================================================
cd /d "%~dp0.."
if exist "%CD%\capricon-data\" powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\migrate_name.ps1"
set "PY=%CD%\capricorn-data\python\Scripts\python.exe"
if not exist "%PY%" (
  echo Capricorn isn't installed yet - run Setup.exe first.
  pause
  exit /b 1
)
"%PY%" -m pip install pytest --quiet
"%PY%" -m pytest -q tests
pause
