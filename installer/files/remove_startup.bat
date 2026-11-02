@echo off
rem Stops Capricorn from starting with Windows.
del "%AppData%\Microsoft\Windows\Start Menu\Programs\Startup\Capricorn.lnk" >nul 2>&1
del "%AppData%\Microsoft\Windows\Start Menu\Programs\Startup\Capricon.lnk" >nul 2>&1
echo Capricorn removed from startup.
pause
