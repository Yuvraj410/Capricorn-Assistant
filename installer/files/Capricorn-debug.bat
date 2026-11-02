@echo off
rem Runs Capricorn with a console so you can see what it hears and does (for troubleshooting).
cd /d "%~dp0"
if exist "%CD%\capricon-data\" powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\migrate_name.ps1"
title Capricorn (debug)
"capricorn-data\python\Scripts\python.exe" -m capricorn
pause
