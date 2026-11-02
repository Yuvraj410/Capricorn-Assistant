@echo off
setlocal EnableExtensions
rem ============================================================================
rem  Change voice
rem  Pick how Capri talks: her own voice, the built-in Windows voice, or text only.
rem ============================================================================
cd /d "%~dp0.."
if exist "%CD%\capricon-data\" powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\migrate_name.ps1"
set "PY=%CD%\capricorn-data\python\Scripts\python.exe"
if not exist "%PY%" (
  echo Capricorn isn't installed yet - run Setup.exe first.
  pause
  exit /b 1
)
for /f "delims=" %%m in ('"%PY%" -m capricorn --get voice.engine') do set "CUR=%%m"
echo Current voice: %CUR%
echo.
echo   1  Capri's own voice   (needs commands\install-capri-voice.bat once)
echo   2  Windows voice       (built in, not Capri's)
echo   3  Text only
echo   4  Auto                (Capri's voice if installed, else text)
choice /c 1234 /n /m "Choose 1-4: "
if errorlevel 4 (set "NEW=auto") else if errorlevel 3 (set "NEW=none") else if errorlevel 2 (set "NEW=sapi") else (set "NEW=capri")
"%PY%" -m capricorn --set voice.engine=%NEW%
echo Voice is now: %NEW%
call "%~dp0restart.bat" /quiet
timeout /t 3 >nul
