@echo off
setlocal EnableExtensions
rem ============================================================================
rem  Minimal mode
rem  Switch between normal mode (full Capri + chat bubbles) and minimal mode (animated visor face, no bubbles).
rem ============================================================================
cd /d "%~dp0.."
if exist "%CD%\capricon-data\" powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\migrate_name.ps1"
set "PY=%CD%\capricorn-data\python\Scripts\python.exe"
if not exist "%PY%" (
  echo Capricorn isn't installed yet - run Setup.exe first.
  pause
  exit /b 1
)
for /f "delims=" %%m in ('"%PY%" -m capricorn --get ui.mode') do set "CUR=%%m"
if /i "%CUR%"=="minimal" (set "NEW=normal") else (set "NEW=minimal")
"%PY%" -m capricorn --set ui.mode=%NEW%
echo Capri's look is now: %NEW%
echo (You can also just say "Hey Capri, minimal mode" or "normal mode".)
powershell -NoProfile -Command "if (Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' or Name='python.exe' or Name='Capricorn.exe'\" | Where-Object { ($_.Name -eq 'Capricorn.exe' -or $_.CommandLine -like '*-m capri*') }) { exit 0 } else { exit 1 }" >nul 2>&1
if not errorlevel 1 (
  echo Restarting Capricorn so the change takes effect...
  powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' or Name='python.exe' or Name='Capricorn.exe'\" | Where-Object { ($_.Name -eq 'Capricorn.exe' -or $_.CommandLine -like '*-m capri*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
  timeout /t 1 /nobreak >nul
  start "" "%CD%\Capricorn.bat"
)
timeout /t 3 >nul
