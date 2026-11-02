@echo off
setlocal EnableExtensions
rem ============================================================================
rem  Open data folder
rem  Opens capricorn-data: Python env, models, logs, settings, approvals.
rem ============================================================================
cd /d "%~dp0.."
if exist "%CD%\capricon-data\" powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\migrate_name.ps1"
set "PY=%CD%\capricorn-data\python\Scripts\python.exe"
if not exist "%PY%" (
  echo Capricorn isn't installed yet - run Setup.exe first.
  pause
  exit /b 1
)
start "" explorer "%CD%\capricorn-data"
