"""
ScratchWatcher.py — Equibase Late Changes scraper
Monitors scratches and field changes for a given track/date.

Data source: https://www.equibase.com/static/latechanges/html/latechanges{TRACK}-USA.html
HTML confirmed via live inspection on 2026-04-29.
"""

import sqlite3
import re
import sys
import os
import json
import subprocess
from datetime import datetime
import time
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from HorseRacing import create_driver

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "horse_racing.db")

_WARMUP_URL     = "https://www.equibase.com/static/latechanges/html/latechanges.html"
_WARMUP_SECONDS = 12
_PAGE_SECONDS   = 8

def _latechanges_url(track_code):
    return f"https://www.equibase.com/static/latechanges/html/latechanges{track_code}-USA.html"


# ── Driver Health Check ───────────────────────────────────────────────────────

def check_driver_health(driver):
    """Return True if the WebDriver is responsive, False if it has crashed/closed."""
    if driver is None:
        return False
    try:
        _ = driver.title   # lightweight property; raises if session is dead
        return True
    except Exception:
        return False


# ── Time Parsing ──────────────────────────────────────────────────────────────

def parse_time_posted(raw):
    """
    Convert a raw time string to a sortable 24-hour HH:MM string.
    "9:31 AM ET" -> "09:31"
    Returns None if the string cannot be parsed.
    """
    if not raw:
        return None
    # Strip trailing timezone (e.g. " ET", " CT", " PT")
    cleaned = re.sub(r"\s+[A-Z]{2,3}$", "", raw.strip())
    for fmt in ("%I:%M %p", "%H:%M"):
        try:
            return datetime.strptime(cleaned, fmt).strftime("%H:%M")
        except ValueError:
            continue
    return None


# ── DB Setup ─────────────────────────────────────────────────────────────────

def init_scratch_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scratch_alerts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            track           TEXT NOT NULL,
            date            TEXT NOT NULL,
            race_num        INTEGER NOT NULL,
            pgm             TEXT NOT NULL,
            horse_name      TEXT NOT NULL,
            change_type     TEXT,
            reason          TEXT,
            time_posted     TEXT,
            time_posted_dt  TEXT,
            detected_at     TEXT,
            UNIQUE(track, date, race_num, pgm, horse_name, change_type)
        )
    """)
    # Migrate existing databases that predate time_posted_dt
    try:
        conn.execute("ALTER TABLE scratch_alerts ADD COLUMN time_posted_dt TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists
    conn.commit()


# ── Scraper ───────────────────────────────────────────────────────────────────

def scrape_late_changes(driver, track_code, date_str, warmup=True):
    """
    Fetch the track's late changes page and parse all change entries.

    Args:
        driver:     active Selenium WebDriver (from create_driver())
        track_code: e.g. "CD"
        date_str:   YYYY-MM-DD — used only for storage; the page always shows today
        warmup:     if True, load the latechanges index page first to establish the
                    Incapsula session cookie (required on a fresh driver)

    Returns:
        list of dicts: {race_num, pgm, horse_name, change_type, reason,
                        time_posted, time_posted_dt}
    """
    if warmup:
        print(f"  Warming up session...")
        try:
            driver.get(_WARMUP_URL)
        except Exception as e:
            print(f"  Warm-up error: {e}")
        time.sleep(_WARMUP_SECONDS)

    url = _latechanges_url(track_code)
    print(f"  Fetching: {url}")
    try:
        driver.get(url)
    except Exception as e:
        print(f"  Browser error loading URL: {e}")
        return []

    time.sleep(_PAGE_SECONDS)

    try:
        html = driver.page_source
    except Exception as e:
        print(f"  Error reading page source: {e}")
        return []

    if len(html) < 5000:
        print(f"  Page too short ({len(html)} chars) — blocked or no data.")
        return []

    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="fullChanges")
    if not table:
        print("  No #fullChanges table found — no changes posted yet.")
        return []

    results = []
    current_race = None

    for row in table.find_all("tr"):
        # Race group header: <tr class="group-header"><th class="race">Race: 4</th>...
        race_th = row.find("th", class_="race")
        if race_th:
            m = re.search(r"Race:\s*(\d+)", race_th.get_text())
            if m:
                current_race = int(m.group(1))
            continue

        if current_race is None:
            continue

        pgm_td    = row.find("td", {"data-label": "PGM"})
        horse_td  = row.find("td", {"data-label": "Horse"})
        change_td = row.find("td", {"data-label": "Changes"})
        time_td   = row.find("td", {"data-label": "Time Posted"})

        # Skip non-horse rows (rail distance, weather notes, etc.)
        if not pgm_td or not horse_td:
            continue

        def clean(td):
            return td.get_text(strip=True).replace("\xa0", "").strip() if td else ""

        pgm         = clean(pgm_td).lstrip("#")
        horse_name  = clean(horse_td)
        time_posted = clean(time_td)

        # Parse "<i>Scratched</i> - PrivVet-Illness" -> change_type="Scratched", reason="PrivVet-Illness"
        change_type = reason = ""
        if change_td:
            italic = change_td.find("i")
            raw = clean(change_td)
            if italic:
                change_type = italic.get_text(strip=True)
                after = raw[len(change_type):]
                reason = after.lstrip(" -").strip()
            else:
                change_type = raw  # non-italic free-text change

        if not horse_name:
            continue

        results.append({
            "race_num":      current_race,
            "pgm":           pgm,
            "horse_name":    horse_name,
            "change_type":   change_type,
            "reason":        reason,
            "time_posted":   time_posted,
            "time_posted_dt": parse_time_posted(time_posted),
        })

    print(f"  Parsed {len(results)} change entry(ies).")
    return results


# ── Deduplication & Storage ───────────────────────────────────────────────────

def detect_new_scratches(track_code, date_str, db_path=DB_PATH, driver=None, warmup=None):
    """
    Scrape the late changes page, compare against scratch_alerts, and save new entries.

    Args:
        track_code: e.g. "CD"
        date_str:   YYYY-MM-DD
        driver:     optional persistent WebDriver; if None, one is created and closed
                    automatically (suitable for one-off CLI use)
        warmup:     override warm-up behaviour; defaults to True when driver is None
                    (fresh session needs it), False when a persistent driver is supplied

    Returns:
        list of new change dicts (empty if nothing new)
    """
    # ── Date guard ────────────────────────────────────────────────────────────
    today = datetime.now().strftime("%Y-%m-%d")
    if date_str != today:
        print(f"  WARNING: date_str={date_str} is not today ({today}).")
        print(f"  The late changes page only shows today's data.")
        print(f"  Skipping save to avoid storing today's changes under the wrong date.")
        return []

    # ── Driver management ─────────────────────────────────────────────────────
    owns_driver = driver is None
    if warmup is None:
        warmup = owns_driver  # fresh driver needs warm-up; persistent one does not
    if owns_driver:
        driver = create_driver()

    try:
        entries = scrape_late_changes(driver, track_code, date_str, warmup=warmup)
    finally:
        if owns_driver:
            driver.quit()

    if not entries:
        return []

    # ── Dedup & save ──────────────────────────────────────────────────────────
    conn = sqlite3.connect(db_path)
    init_scratch_db(conn)
    new_entries = []
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for e in entries:
        c.execute(
            """SELECT id FROM scratch_alerts
               WHERE track=? AND date=? AND race_num=? AND pgm=?
                 AND horse_name=? AND change_type=?""",
            (track_code, date_str, e["race_num"], e["pgm"],
             e["horse_name"], e["change_type"])
        )
        if c.fetchone():
            continue  # Already in DB

        c.execute(
            """INSERT OR IGNORE INTO scratch_alerts
               (track, date, race_num, pgm, horse_name, change_type, reason,
                time_posted, time_posted_dt, detected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (track_code, date_str, e["race_num"], e["pgm"], e["horse_name"],
             e["change_type"], e["reason"], e["time_posted"], e["time_posted_dt"], now)
        )
        if c.lastrowid:
            new_entries.append(e)

    # Mark newly scratched horses in entry_horses table so the next
    # export_dashboard_data run picks them up without re-scraping
    for e in new_entries:
        if e.get("change_type", "").lower() == "scratched":
            try:
                conn.execute(
                    "UPDATE entry_horses SET scratched=1 "
                    "WHERE track=? AND race_date=? AND race_num=? AND program_num=?",
                    (track_code, date_str, e["race_num"], e["pgm"])
                )
            except Exception:
                pass
    conn.commit()
    conn.close()

    if new_entries:
        export_scratches_to_json(track_code, date_str, db_path)
        push_scratches_to_github()
        _patch_dashboard_scratches(track_code, new_entries)

    return new_entries


# ── Manual AE Override ────────────────────────────────────────────────────────

def add_ae_manual(track_code, date_str, race_num, pgm, horse_name, db_path=DB_PATH):
    """
    Manually record an AE horse added to the field.
    Handles the known gap: AE additions do not appear on the late changes page.

    Returns:
        True if inserted, False if already recorded
    """
    conn = sqlite3.connect(db_path)
    init_scratch_db(conn)
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    c.execute(
        """INSERT OR IGNORE INTO scratch_alerts
           (track, date, race_num, pgm, horse_name, change_type, reason,
            time_posted, time_posted_dt, detected_at)
           VALUES (?, ?, ?, ?, ?, 'AE_ADDED', 'Manual Entry', ?, ?, ?)""",
        (track_code, date_str, race_num, str(pgm), horse_name, now, now, now)
    )
    inserted = c.rowcount > 0
    conn.commit()
    conn.close()

    if inserted:
        print(f"AE entry saved:    {track_code} {date_str} R{race_num} #{pgm} {horse_name}")
    else:
        print(f"Already recorded:  {track_code} {date_str} R{race_num} #{pgm} {horse_name}")
    return inserted


# ── JSON Export ──────────────────────────────────────────────────────────────

def export_scratches_to_json(track_code, date_str, db_path=DB_PATH):
    web_data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "data")
    os.makedirs(web_data_dir, exist_ok=True)
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        """SELECT race_num, pgm, horse_name, change_type, reason, time_posted, time_posted_dt
           FROM scratch_alerts WHERE track=? AND date=?
           ORDER BY race_num, pgm""",
        (track_code, date_str)
    ).fetchall()
    conn.close()
    scratches = [
        {"race": r[0], "pgm": r[1], "horse": r[2], "change_type": r[3],
         "reason": r[4] or "", "time_posted": r[5] or "", "time_posted_dt": r[6]}
        for r in rows
    ]
    payload = {
        "track": track_code, "date": date_str,
        "generated_at": datetime.now().strftime("%I:%M %p ET"),
        "scratches": scratches
    }
    out_path = os.path.join(web_data_dir, "scratches.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"  Exported {len(scratches)} entries -> web/data/scratches.json")
    return out_path


def push_scratches_to_github():
    web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        subprocess.run(["git", "add", "data/scratches.json"],
                       cwd=web_dir, check=True, capture_output=True)
        result = subprocess.run(
            ["git", "commit", "-m", f"scratch update {ts}"],
            cwd=web_dir, capture_output=True, text=True
        )
        if result.returncode != 0:
            out = result.stdout.strip() or result.stderr.strip()
            if "nothing to commit" in out:
                print("  Git: nothing new to commit.")
                return
            print(f"  Git commit warning: {out}")
            return
        push = subprocess.run(["git", "push"], cwd=web_dir,
                               capture_output=True, text=True)
        if push.returncode == 0:
            print("  Pushed to GitHub.")
        else:
            print(f"  Git push failed: {push.stderr.strip()}")
    except Exception as e:
        print(f"  Git push error: {e}")


# ── Dashboard Scratch Patch ──────────────────────────────────────────────────

def _patch_dashboard_scratches(track_code, new_entries):
    """
    Update web/dashboard_data.json in-place: set scratched=true for each
    newly scratched horse, matching on race_num + program_num + horse_name.
    Calls push_dashboard_to_github() if any horses were patched.
    """
    web_dir   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
    dash_path = os.path.join(web_dir, "dashboard_data.json")
    if not os.path.exists(dash_path):
        return

    scratch_entries = [e for e in new_entries if e.get("change_type", "").lower() == "scratched"]
    if not scratch_entries:
        return

    try:
        with open(dash_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  Could not read dashboard_data.json: {e}")
        return

    track_data = data.get("today_entries", {}).get(track_code)
    if not track_data:
        return

    patched = 0
    for e in scratch_entries:
        race_num = e["race_num"]
        pgm      = e["pgm"]
        name     = e["horse_name"]
        for race in track_data.get("races", []):
            if race.get("race_num") != race_num:
                continue
            for horse in race.get("horses", []):
                if horse.get("program_num") == pgm and horse.get("horse_name") == name:
                    horse["scratched"] = True
                    patched += 1

    if patched:
        try:
            with open(dash_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print(f"  Patched {patched} horse(s) as scratched in dashboard_data.json")
            push_dashboard_to_github()
        except Exception as e:
            print(f"  Could not write dashboard_data.json: {e}")


# ── Dashboard Push ───────────────────────────────────────────────────────────

def push_dashboard_to_github():
    """
    Stage, commit, and push web/dashboard_data.json.
    Non-crashing: logs errors but does not raise.
    """
    web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        subprocess.run(["git", "add", "dashboard_data.json"],
                       cwd=web_dir, check=True, capture_output=True)
        result = subprocess.run(
            ["git", "commit", "-m", f"entries update {ts}"],
            cwd=web_dir, capture_output=True, text=True
        )
        if result.returncode != 0:
            out = result.stdout.strip() or result.stderr.strip()
            if "nothing to commit" in out:
                print("  Git: nothing new to commit.")
                return
            print(f"  Git commit warning: {out}")
            return
        push = subprocess.run(["git", "push"], cwd=web_dir,
                               capture_output=True, text=True)
        if push.returncode == 0:
            print("  Pushed dashboard_data.json to GitHub.")
        else:
            print(f"  Git push failed: {push.stderr.strip()}")
    except Exception as e:
        print(f"  Git push error: {e}")


# ── Backfill ─────────────────────────────────────────────────────────────────

def backfill_time_posted_dt(db_path=DB_PATH):
    """
    One-time (idempotent) migration: populate time_posted_dt for any rows
    where it is NULL but time_posted has a parseable value.
    Safe to call repeatedly — only touches NULL rows.
    """
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT id, time_posted FROM scratch_alerts"
        " WHERE time_posted_dt IS NULL AND time_posted IS NOT NULL AND time_posted != ''"
    ).fetchall()

    updated = 0
    for row_id, time_posted in rows:
        dt = parse_time_posted(time_posted)
        if dt:
            conn.execute(
                "UPDATE scratch_alerts SET time_posted_dt=? WHERE id=?",
                (dt, row_id)
            )
            updated += 1

    conn.commit()
    conn.close()
    print(f"Backfilled {updated} row(s)  ({len(rows) - updated} unparseable, left NULL)")
    return updated


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    track = sys.argv[1].upper() if len(sys.argv) > 1 else "CD"
    date  = sys.argv[2]        if len(sys.argv) > 2 else datetime.now().strftime("%Y-%m-%d")

    print(f"\nChecking late changes: {track}  {date}")
    print("-" * 45)

    new = detect_new_scratches(track, date)
    if new:
        print(f"\n{len(new)} new change(s):")
        for e in new:
            print(f"  R{e['race_num']} #{e['pgm']:>3}  {e['horse_name']:<28}"
                  f"  {e['change_type']} - {e['reason']}"
                  f"  @ {e['time_posted']} ({e['time_posted_dt']})")
    else:
        print("No new changes.")

    backfill_time_posted_dt()
