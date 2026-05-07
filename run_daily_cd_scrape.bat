@echo off
setlocal

set PROJECT=C:\Users\jason\Desktop\HorseRacing Project
set PYTHON=C:\Users\jason\AppData\Local\Python\pythoncore-3.14-64\python.exe
set LOG=%PROJECT%\scrape_log.txt

:: Get today's date in YYYY-MM-DD format (locale-safe via Python)
for /f "tokens=*" %%d in ('python -c "from datetime import date; print(date.today())"') do set TODAY=%%d

echo. >> "%LOG%"
echo ============================================================ >> "%LOG%"
echo CD DAILY SCRAPE  %TODAY%  started %time% >> "%LOG%"
echo ============================================================ >> "%LOG%"
echo NOTE: scrape_entries.py runs separately at 9am each morning  >> "%LOG%"
echo       via the "HorseRacing CD Morning Entries" scheduled task. >> "%LOG%"
echo       By 8pm those entries are already in the DB for export.  >> "%LOG%"

:: ── Step 1: Scrape entries for today (catches any not yet scraped this morning)
echo [1/5] scrape_entries.py CD >> "%LOG%"
"%PYTHON%" "%PROJECT%\scrape_entries.py" CD >> "%LOG%" 2>&1
if %errorlevel% neq 0 (
    echo STEP 1 WARNING: scrape_entries.py exited %errorlevel% — continuing >> "%LOG%"
)

:: ── Step 2: Scrape today's CD race results ──────────────────────────────────
echo [2/5] HorseRacingHRN.py --track CD %TODAY% >> "%LOG%"
"%PYTHON%" "%PROJECT%\HorseRacingHRN.py" --track CD %TODAY% >> "%LOG%" 2>&1
if %errorlevel% neq 0 (
    echo STEP 2 FAILED ^(exit %errorlevel%^) — aborting pipeline >> "%LOG%"
    echo ---- end %time% ---- >> "%LOG%"
    exit /b 1
)

:: ── Step 3: Validate payout bases ──────────────────────────────────────────
echo [3/5] derby_value.py validate >> "%LOG%"
"%PYTHON%" "%PROJECT%\derby_value.py" validate >> "%LOG%" 2>&1
if %errorlevel% neq 0 (
    echo STEP 3 WARNING: validate found hard violations — continuing >> "%LOG%"
)

:: ── Step 4: Export dashboard JSON (now includes today_entries) ──────────────
echo [4/5] export_dashboard_data.py >> "%LOG%"
"%PYTHON%" "%PROJECT%\export_dashboard_data.py" >> "%LOG%" 2>&1
if %errorlevel% neq 0 (
    echo STEP 4 FAILED ^(exit %errorlevel%^) — aborting pipeline >> "%LOG%"
    echo ---- end %time% ---- >> "%LOG%"
    exit /b 1
)

:: ── Step 5: Git commit and push ─────────────────────────────────────────────
echo [5/5] git add / commit / push >> "%LOG%"
cd /d "%PROJECT%\web"
git add dashboard_data.json >> "%LOG%" 2>&1
git commit -m "daily CD scrape %TODAY%" >> "%LOG%" 2>&1
git push >> "%LOG%" 2>&1
if %errorlevel% neq 0 (
    echo STEP 5 WARNING: git push exited %errorlevel% >> "%LOG%"
)

echo ---- done %time% ---- >> "%LOG%"
exit /b 0
