@echo off
setlocal EnableExtensions
rem ============================================================================
rem  Settings screen
rem  Every setting with explanations: personality, slang, voice, listening, look... (also in the tray menu
rem  and the chat window, or say "Hey Capri, open settings").
rem ============================================================================
cd /d "%~dp0.."
if exist "%CD%\capricon-data\" powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\migrate_name.ps1"
set "PY=%CD%\capricorn-data\python\Scripts\pythonw.exe"
if not exist "%PY%" (
  echo Capricorn isn't installed yet - run Setup.exe first.
  pause
  exit /b 1
)
if exist "%CD%\capricorn-data\python\Scripts\Capricorn.exe" (
  start "" "%CD%\capricorn-data\python\Scripts\Capricorn.exe" --settings
) else (
  start "" "%PY%" -m capricorn --settings
)
