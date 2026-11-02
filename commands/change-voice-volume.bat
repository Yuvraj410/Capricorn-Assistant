@echo off
setlocal EnableExtensions
rem ============================================================================
rem  Capri's voice volume
rem  Makes Capri's spoken voice louder or quieter (doesn't touch Windows or music volume).
rem ============================================================================
cd /d "%~dp0.."
if exist "%CD%\capricon-data\" powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\migrate_name.ps1"
set "PY=%CD%\capricorn-data\python\Scripts\python.exe"
if not exist "%PY%" (
  echo Capricorn isn't installed yet - run Setup.exe first.
  pause
  exit /b 1
)
for /f "delims=" %%m in ('"%PY%" -m capricorn --get voice.volume') do set "CUR=%%m"
echo Current voice volume: %CUR%   (1.0 = normal)
echo.
echo   1  Quiet   (0.6)
echo   2  Normal  (1.0)
echo   3  Loud    (1.5)
echo   4  Louder  (2.0)
echo   5  Max     (3.0)
choice /c 12345 /n /m "Choose 1-5: "
if errorlevel 5 (set "NEW=3.0") else if errorlevel 4 (set "NEW=2.0") else if errorlevel 3 (set "NEW=1.5") else if errorlevel 2 (set "NEW=1.0") else (set "NEW=0.6")
"%PY%" -m capricorn --set voice.volume=%NEW%
echo Voice volume is now: %NEW%
call "%~dp0restart.bat" /quiet
timeout /t 3 >nul
