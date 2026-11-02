@echo off
rem Makes Capricorn start automatically (hidden, in the tray) when you log in to Windows.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\make_shortcut.ps1" -Where Startup
if /i not "%~1"=="/quiet" pause
