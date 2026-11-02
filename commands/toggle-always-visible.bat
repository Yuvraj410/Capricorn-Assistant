@echo off
setlocal EnableExtensions
rem ============================================================================
rem  Always visible
rem  Keep Capri on screen (blinking) even when idle, or only show her when called.
rem ============================================================================
cd /d "%~dp0.."
if exist "%CD%\capricon-data\" powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\migrate_name.ps1"
set "PY=%CD%\capricorn-data\python\Scripts\python.exe"
if not exist "%PY%" (
  echo Capricorn isn't installed yet - run Setup.exe first.
  pause
  exit /b 1
)
for /f "delims=" %%m in ('"%PY%" -m capricorn --get ui.always_visible') do set "CUR=%%m"
if /i "%CUR%"=="True" (set "NEW=false") else (set "NEW=true")
"%PY%" -m capricorn --set ui.always_visible=%NEW%
echo Always visible is now: %NEW%
powershell -NoProfile -Command "if (Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' or Name='python.exe' or Name='Capricorn.exe'\" | Where-Object { ($_.Name -eq 'Capricorn.exe' -or $_.CommandLine -like '*-m capri*') }) { exit 0 } else { exit 1 }" >nul 2>&1
if not errorlevel 1 (
  echo Restarting Capricorn so the change takes effect...
  powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' or Name='python.exe' or Name='Capricorn.exe'\" | Where-Object { ($_.Name -eq 'Capricorn.exe' -or $_.CommandLine -like '*-m capri*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
  timeout /t 1 /nobreak >nul
  start "" "%CD%\Capricorn.bat"
)
timeout /t 3 >nul
