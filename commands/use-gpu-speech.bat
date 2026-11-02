@echo off
setlocal EnableExtensions
rem ============================================================================
rem  GPU speech-to-text
rem  Installs NVIDIA CUDA libraries (~1 GB) and runs Whisper on your GPU for faster replies. Falls back to CPU automatically if it fails.
rem ============================================================================
cd /d "%~dp0.."
if exist "%CD%\capricon-data\" powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\migrate_name.ps1"
set "PY=%CD%\capricorn-data\python\Scripts\python.exe"
if not exist "%PY%" (
  echo Capricorn isn't installed yet - run Setup.exe first.
  pause
  exit /b 1
)
echo This downloads ~1 GB of NVIDIA libraries into capricorn-data\python.
choice /c YN /n /m "Continue? [Y/N]: "
if errorlevel 2 exit /b 0
"%PY%" -m pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"
if errorlevel 1 (echo Install failed. & pause & exit /b 1)
"%PY%" -m capricorn --set stt.device=cuda --set stt.compute_type=float16
powershell -NoProfile -Command "if (Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' or Name='python.exe' or Name='Capricorn.exe'\" | Where-Object { ($_.Name -eq 'Capricorn.exe' -or $_.CommandLine -like '*-m capri*') }) { exit 0 } else { exit 1 }" >nul 2>&1
if not errorlevel 1 (
  echo Restarting Capricorn so the change takes effect...
  powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' or Name='python.exe' or Name='Capricorn.exe'\" | Where-Object { ($_.Name -eq 'Capricorn.exe' -or $_.CommandLine -like '*-m capri*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
  timeout /t 1 /nobreak >nul
  start "" "%CD%\Capricorn.bat"
)
echo To go back to CPU: run this again and answer N, then:  "%PY%" -m capricorn --set stt.device=cpu --set stt.compute_type=int8
pause
