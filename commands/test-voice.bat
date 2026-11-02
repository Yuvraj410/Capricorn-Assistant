@echo off
setlocal EnableExtensions
rem ============================================================================
rem  Test Capri's voice
rem  Type a line and hear Capri say it (without starting the app). Good for checking a new reference recording.
rem ============================================================================
cd /d "%~dp0.."
if exist "%CD%\capricon-data\" powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\migrate_name.ps1"
set "PY=%CD%\capricorn-data\python\Scripts\python.exe"
if not exist "%PY%" (
  echo Capricorn isn't installed yet - run Setup.exe first.
  pause
  exit /b 1
)
set "VPY=%CD%\capricorn-data\voice-env\Scripts\python.exe"
if not exist "%VPY%" (
  echo Capri's voice isn't installed - run commands\install-capri-voice.bat first.
  pause
  exit /b 1
)
for /f "delims=" %%r in ('"%PY%" -m capricorn --get voice.reference') do set "REF=%%r"
if not exist "%REF%" set "REF=%CD%\capricorn-data\voices\%REF%"
:again
set "LINE="
set /p "LINE=Line for Capri (empty = quit): "
if "%LINE%"=="" exit /b 0
"%VPY%" -m capricorn.tts.worker --reference "%REF%" --selftest "%CD%\capricorn-data\voice_cache\tts\_test.wav" --text "%LINE%" 2>>"%CD%\capricorn-data\logs\voice-test.log"
if errorlevel 1 (echo That failed - see capricorn-data\logs\voice-test.log & goto again)
powershell -NoProfile -Command "(New-Object Media.SoundPlayer '%CD%\capricorn-data\voice_cache\tts\_test.wav').PlaySync()"
goto again
