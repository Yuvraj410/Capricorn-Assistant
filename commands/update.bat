@echo off
setlocal EnableExtensions
rem ============================================================================
rem  Update packages
rem  After pulling new code: updates Python packages and restarts Capri (settings, approvals and models are kept).
rem ============================================================================
cd /d "%~dp0.."
if exist "%CD%\capricon-data\" powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\migrate_name.ps1"
set "PY=%CD%\capricorn-data\python\Scripts\python.exe"
if not exist "%PY%" (
  echo Capricorn isn't installed yet - run Setup.exe first.
  pause
  exit /b 1
)
call "%CD%\update.bat"
