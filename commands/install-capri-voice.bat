@echo off
setlocal EnableExtensions
rem ============================================================================
rem  Install Capri's voice
rem  Free local voice cloning (Chatterbox Turbo). Downloads ~4 GB once (PyTorch + model). Add --cpu to skip the GPU build.
rem ============================================================================
cd /d "%~dp0.."
if exist "%CD%\capricon-data\" powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\migrate_name.ps1"
set "PY=%CD%\capricorn-data\python\Scripts\python.exe"
if not exist "%PY%" (
  echo Capricorn isn't installed yet - run Setup.exe first.
  pause
  exit /b 1
)
title Installing Capri's voice
"%PY%" scripts\install_voice.py %*
if errorlevel 1 (
  echo.
  echo Something went wrong - scroll up for the [FAIL] line. You can run this again any time.
  pause
  exit /b 1
)
call "%~dp0restart.bat" /quiet
pause
