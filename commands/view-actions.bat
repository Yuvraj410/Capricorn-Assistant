@echo off
setlocal EnableExtensions
rem ============================================================================
rem  Action history
rem  Opens actions.log: every app, file, folder, site and system action Capri ran (or was denied).
rem ============================================================================
cd /d "%~dp0.."
if exist "%CD%\capricon-data\" powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\migrate_name.ps1"
set "PY=%CD%\capricorn-data\python\Scripts\python.exe"
if not exist "%PY%" (
  echo Capricorn isn't installed yet - run Setup.exe first.
  pause
  exit /b 1
)
if not exist "capricorn-data\logs\actions.log" (echo Capri hasn't done anything yet. & pause & exit /b 0)
notepad "capricorn-data\logs\actions.log"
