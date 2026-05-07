@echo off
setlocal

set PROJECT=C:\Users\jason\Desktop\HorseRacing Project
set PYTHON=C:\Users\jason\AppData\Local\Python\pythoncore-3.14-64\python.exe
set LOG=%PROJECT%\scrape_log.txt

:: Get today's date in YYYY-MM-DD format (locale-safe via Python)
for /f %%d in ('"%PYTHON%" -c "from datetime import date; print(date.today())"') do set TODAY=%%d

echo. >> "%LOG%"
echo ── MORNING ENTRIES  %TODAY%  %time% ──────────────────────────────── >> "%LOG%"
echo Tracks: CD GP KEE SA AQU FG OP  (tracks with no card today are skipped) >> "%LOG%"

:: Run scraper for all configured tracks (no args = all tracks, today's date).
:: The scraper sleeps 1.5s between tracks and gracefully skips any track
:: whose entries page is missing or too small ("no card today").
"%PYTHON%" "%PROJECT%\scrape_entries.py" >> "%LOG%" 2>&1
if %errorlevel% neq 0 (
    echo MORNING ENTRIES WARNING: scrape_entries.py exited %errorlevel% >> "%LOG%"
)

echo ── morning entries done %time% ── >> "%LOG%"
exit /b 0
