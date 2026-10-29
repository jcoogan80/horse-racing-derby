@echo off
:: Breeders' Cup race day: poll Equibase late changes for Keeneland every 5 minutes.
:: Each run writes web/data/scratches.json and pushes it, which re-prices the KEE BC tab.
:: Usage: run_kee_bc_scratches.bat            (today)
::        run_kee_bc_scratches.bat 2026-10-31 (specific date)
setlocal
set PROJECT=C:\Users\jason\Desktop\HorseRacing Project
set PYTHON=C:\Users\jason\AppData\Local\Python\pythoncore-3.14-64\python.exe
set DAY=%1
if "%DAY%"=="" for /f "tokens=*" %%d in ('python -c "from datetime import date; print(date.today())"') do set DAY=%%d
:loop
echo [%time%] KEE %DAY% late changes
"%PYTHON%" "%PROJECT%\ScratchWatcher.py" KEE %DAY%
timeout /t 300 /nobreak >nul
goto loop
