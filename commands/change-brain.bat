@echo off
setlocal EnableExtensions
rem ============================================================================
rem  Change Capri's brain (LLM)
rem  Downloads another free Ollama model and switches to it. Examples: qwen3:4b (default), qwen3:8b (smarter, slower), llama3.2:3b (faster).
rem ============================================================================
cd /d "%~dp0.."
if exist "%CD%\capricon-data\" powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\migrate_name.ps1"
set "PY=%CD%\capricorn-data\python\Scripts\python.exe"
if not exist "%PY%" (
  echo Capricorn isn't installed yet - run Setup.exe first.
  pause
  exit /b 1
)
for /f "delims=" %%m in ('"%PY%" -m capricorn --get brain.model') do set "CUR=%%m"
echo Current brain: %CUR%
echo.
echo   qwen3:4b     default - good balance (~2.6 GB)
echo   qwen3:8b     smarter, a bit slower (~5.2 GB)
echo   llama3.2:3b  fastest (~2.0 GB)
echo   gemma3:4b    alternative (~3.3 GB)
echo.
set "MODEL="
set /p "MODEL=Model name (Enter to cancel): "
if not defined MODEL exit /b 0
set "OLLAMA=ollama"
where ollama >nul 2>&1 || set "OLLAMA=%LocalAppData%\Programs\Ollama\ollama.exe"
"%OLLAMA%" pull %MODEL%
if errorlevel 1 (
  echo Download failed - check the name at https://ollama.com/library
  pause
  exit /b 1
)
"%PY%" -m capricorn --set brain.model=%MODEL%
powershell -NoProfile -Command "if (Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' or Name='python.exe' or Name='Capricorn.exe'\" | Where-Object { ($_.Name -eq 'Capricorn.exe' -or $_.CommandLine -like '*-m capri*') }) { exit 0 } else { exit 1 }" >nul 2>&1
if not errorlevel 1 (
  echo Restarting Capricorn so the change takes effect...
  powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' or Name='python.exe' or Name='Capricorn.exe'\" | Where-Object { ($_.Name -eq 'Capricorn.exe' -or $_.CommandLine -like '*-m capri*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
  timeout /t 1 /nobreak >nul
  start "" "%CD%\Capricorn.bat"
)
pause
