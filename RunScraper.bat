@echo off
setlocal

set PROJECT=C:\Users\jason\Desktop\HorseRacing Project
set WEB=%PROJECT%\web

:: ── 1. Activate virtual environment if one exists ──────────────────────────
set ACTIVATED=0
for %%E in (venv env .venv Scripts) do (
    if exist "%PROJECT%\%%E\Scripts\activate.bat" (
        echo Activating virtual environment: %%E
        call "%PROJECT%\%%E\Scripts\activate.bat"
        set ACTIVATED=1
        goto :env_done
    )
)
:env_done
if %ACTIVATED%==0 (
    echo No virtual environment found — using system Python.
)

:: ── 2. Run the GUI scraper ─────────────────────────────────────────────────
echo.
echo Running HorseRacingGUI.py ...
python "%PROJECT%\HorseRacingGUI.py"

:: ── 3. Export dashboard data ───────────────────────────────────────────────
echo.
echo Running export_dashboard_data.py ...
python "%PROJECT%\export_dashboard_data.py"
if errorlevel 1 (
    echo ERROR: export_dashboard_data.py failed. Aborting git push.
    pause
    exit /b 1
)

:: ── 4. Git add / commit / push ─────────────────────────────────────────────
echo.
echo Committing and pushing dashboard_data.json ...
cd /d "%WEB%"
git add dashboard_data.json
git commit -m "auto update data"
git push

echo.
echo Done!
pause
