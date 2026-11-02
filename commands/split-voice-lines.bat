@echo off
setlocal EnableExtensions
rem ============================================================================
rem  Import Capri voice lines
rem  Cuts line packs (lines-*.mp3 + lines-*.txt) into one clip per line using Whisper word timestamps, verifies each, and adds them to the voice cache.
rem ============================================================================
cd /d "%~dp0.."
if exist "%CD%\capricon-data\" powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\migrate_name.ps1"
set "PY=%CD%\capricorn-data\python\Scripts\python.exe"
if not exist "%PY%" (
  echo Capricorn isn't installed yet - run Setup.exe first.
  pause
  exit /b 1
)
echo Folder with your recordings (lines-1.mp3 + lines-1.txt ...).
echo Tip: drag the folder onto this window, then press Enter.
set "SRC="
set /p "SRC=Folder: "
if not defined SRC exit /b 0
set SRC=%SRC:"=%
"%PY%" tools\split_voice_lines.py "%SRC%" --transcribe-missing
pause
