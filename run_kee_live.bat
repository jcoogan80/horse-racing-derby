@echo off
:: Breeders' Cup race day: live tote odds, MTP and scratches for the KEE BC tab.
:: Reads TwinSpires every 60 s and writes Firebase (archive/kee-live); the app refreshes every minute.
:: Leave this window open during the card. It stops by itself when the last race is official.
setlocal
set PROJECT=C:\Users\jason\Desktop\HorseRacing Project
set PYTHON=C:\Users\jason\AppData\Local\Python\pythoncore-3.14-64\python.exe
"%PYTHON%" -m pip install --quiet --disable-pip-version-check requests curl_cffi
:run
"%PYTHON%" "%PROJECT%\kee_live_watcher.py"
if errorlevel 3 goto done
echo Watcher stopped. Restarting in 30 seconds (close this window to quit).
timeout /t 30 /nobreak >nul
goto run
:done
echo Card is over. You can close this window.
pause
