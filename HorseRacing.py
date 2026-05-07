"""
Equibase Horse Racing Results Scraper & Database Builder
Uses Selenium with a single browser session for all dates.
Exports to Google Sheets.
Requires: pip install selenium webdriver-manager beautifulsoup4 pandas gspread google-auth
"""

from bs4 import BeautifulSoup
import sqlite3
import sys
import pandas as pd
import re
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# ── Google Sheets Setup ──────────────────────────────────────────────────────

CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")
SHEET_NAME = "Horse Racing"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def get_gsheet():
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open(SHEET_NAME)


# ── Odds Helper ─────────────────────────────────────────────────────────────

def odds_to_implied_prob(odds_str):
    """
    Convert a morning-line fractional odds string to an implied probability float.

    Accepts formats:
      "5/2"  → 2/(5+2)  ≈ 0.286
      "5-2"  → same
      "8/1"  → 1/(8+1)  ≈ 0.111
      "8"    → 1/(8+1)  (treats integer as X-to-1)
      "1/2"  → 2/(1+2)  ≈ 0.667  (odds-on)
      "even" → 0.5
    Returns None if the string cannot be parsed.
    """
    if not odds_str:
        return None
    s = odds_str.strip().lower()
    if s in ("even", "e", "1/1", "1-1"):
        return 0.5
    # Try fraction  e.g. "5/2" or "5-2"
    m = re.match(r"^(\d+(?:\.\d+)?)[/\-](\d+(?:\.\d+)?)$", s)
    if m:
        num, den = float(m.group(1)), float(m.group(2))
        if num + den == 0:
            return None
        return round(den / (num + den), 6)
    # Plain integer  e.g. "8"  →  8/1
    m = re.match(r"^(\d+(?:\.\d+)?)$", s)
    if m:
        num = float(m.group(1))
        return round(1.0 / (num + 1.0), 6)
    return None


# ── Wager base defaults (minimum wager per Equibase convention) ──────────────

_DEFAULT_WAGER_BASES = {
    'P5': 0.50, 'P6': 0.20, 'P4': 0.50, 'P3': 0.50,
    'DD': 1.00, 'EX': 1.00, 'TRI': 0.50, 'SF': 0.10,
}


# ── Database Setup ───────────────────────────────────────────────────────────

def init_db(db_path="horse_racing.db"):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS race_results (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            track         TEXT NOT NULL,
            race_date     TEXT NOT NULL,
            race_num      INTEGER NOT NULL,
            winner        TEXT,
            winner_pgm    TEXT,
            win_payout    REAL,
            place_payout  REAL,
            show_payout   REAL,
            race_type     TEXT,
            distance      TEXT,
            surface       TEXT,
            purse         TEXT,
            winning_time         TEXT,
            field_size           INTEGER,
            winner_morning_line  TEXT,
            implied_prob         REAL,
            track_condition      TEXT,
            UNIQUE(track, race_date, race_num)
        )
    """)
    # Add columns to existing databases that predate them
    for col_def in [
        "ALTER TABLE race_results ADD COLUMN field_size INTEGER",
        "ALTER TABLE race_results ADD COLUMN winner_morning_line TEXT",
        "ALTER TABLE race_results ADD COLUMN implied_prob REAL",
        "ALTER TABLE race_results ADD COLUMN track_condition TEXT",
    ]:
        try:
            c.execute(col_def)
        except sqlite3.OperationalError:
            pass  # Column already exists
    conn.commit()
    c.execute("""
        CREATE TABLE IF NOT EXISTS exotic_payouts (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            track         TEXT NOT NULL,
            race_date     TEXT NOT NULL,
            race_num      INTEGER NOT NULL,
            wager_type    TEXT NOT NULL,
            race_span     TEXT NOT NULL,
            winning_combo TEXT,
            base_amount   TEXT,
            payout        REAL,
            wager_base    REAL DEFAULT 2.0,
            payout_per_2  REAL,
            UNIQUE(track, race_date, race_num, wager_type, race_span, winning_combo)
        )
    """)
    # Add columns to existing databases that predate them
    for col_def in [
        "ALTER TABLE exotic_payouts ADD COLUMN wager_base REAL DEFAULT 2.0",
        "ALTER TABLE exotic_payouts ADD COLUMN payout_per_2 REAL",
    ]:
        try:
            c.execute(col_def)
        except sqlite3.OperationalError:
            pass
    # Backfill wager_base for historical rows (only where payout_per_2 not yet computed)
    for wtype, base in _DEFAULT_WAGER_BASES.items():
        c.execute(
            "UPDATE exotic_payouts SET wager_base = ? "
            "WHERE wager_type = ? AND payout_per_2 IS NULL",
            (base, wtype)
        )
    # Compute payout_per_2 for all rows that are missing it
    c.execute(
        "UPDATE exotic_payouts SET payout_per_2 = ROUND(payout * (2.0 / wager_base), 2) "
        "WHERE payout_per_2 IS NULL AND wager_base IS NOT NULL AND wager_base > 0"
    )
    conn.commit()
    return conn


# ── URL Builder ──────────────────────────────────────────────────────────────

def build_equibase_url(track_code, date_str, country="USA"):
    return f"https://www.equibase.com/static/chart/summary/{track_code}{date_str}{country}-EQB.html"


# ── Selenium Driver ──────────────────────────────────────────────────────────

def create_driver():
    """Create a single reusable Chrome browser session."""
    options = Options()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--window-size=1280,800")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    return driver


def get_page_html(driver, url, first_page=False):
    """Fetch a page using an existing driver session."""
    try:
        driver.get(url)
    except Exception as e:
        print(f"  Browser error loading URL: {e}")
        return "", True

    if first_page:
        print("  Browser opened - solve any CAPTCHA now if prompted...")
        print("  Waiting 30 seconds...")
        time.sleep(30)
    else:
        time.sleep(5)

    try:
        page_src = driver.page_source
        title    = driver.title
    except Exception as e:
        print(f"  Error reading page: {e}")
        return "", True

    # Detect any kind of error page
    skip_signals = [
        "404", "nginx", "not found", "no results",
        "pardon our interruption", "error"
    ]
    title_lower = title.lower()
    page_lower  = page_src.lower()

    if any(s in title_lower for s in skip_signals):
        print(f"  Skipping - page title indicates error: '{title}'")
        return "", True

    if len(page_src) < 10000:
        print(f"  Skipping - page too short ({len(page_src)} chars), likely an error page.")
        return "", True

    return page_src, False


# ── Scraper ──────────────────────────────────────────────────────────────────

def scrape_card(driver, url, track_code, race_date, first_page=False):
    print(f"Fetching: {url}")
    html, is_404 = get_page_html(driver, url, first_page=first_page)

    if is_404:
        print("  No results for this date - skipping.")
        return [], []

    print(f"  Page length: {len(html)} characters")

    soup = BeautifulSoup(html, "html.parser")
    race_results = []
    exotic_payouts = []

    race_divs = soup.find_all("div", class_="c-results-data")
    print(f"  Race sections found: {len(race_divs)}")

    for race_div in race_divs:
        h5 = race_div.find("h5", class_="coolgraybg")
        if not h5:
            continue
        race_match = re.search(r"Race\s+(\d+)", h5.get_text(strip=True), re.I)
        if not race_match:
            continue
        race_num = int(race_match.group(1))

        # Race details
        race_type = distance = purse = win_time = track_cond = ""
        field_size = None
        winner_ml = None
        detail_div = race_div.find("div", class_="col-xs-9 pdngBtm20")
        if detail_div:
            dt = detail_div.get_text(" ", strip=True)
            m = re.search(r"Race type\s*:\s*(.+?)(?:Age|Sex|Purse|Distance|$)", dt, re.I)
            if m: race_type = m.group(1).strip()
            m = re.search(r"Purse\s*:\s*\$?([\d,]+)", dt, re.I)
            if m: purse = "$" + m.group(1)
            m = re.search(r"Distance\s*:\s*(.+?)(?:Track|Winning|$)", dt, re.I)
            if m: distance = m.group(1).strip()
            m = re.search(r"Track Condition\s*:\s*(.+?)(?:Winning|$)", dt, re.I)
            if m: track_cond = m.group(1).strip()
            m = re.search(r"Winning Time\s*:\s*([\d:.]+)", dt, re.I)
            if m: win_time = m.group(1)
            m = re.search(r"Number of Starters\s*:\s*(\d+)", dt, re.I)
            if m: field_size = int(m.group(1))
            # Morning line odds for winner — present on some chart formats;
            # Equibase HTML summary charts do not currently include this field.
            m = re.search(r"Morning\s+Line\s*:\s*([\d/\-]+|even)", dt, re.I)
            if m: winner_ml = m.group(1).strip()

        # Winner
        winner = winner_pgm = ""
        win_pay = place_pay = show_pay = None
        for tbl in race_div.find_all("table", class_="clear fullwidth text-left"):
            for row in tbl.find_all("tr"):
                if row.find("th"):
                    continue
                cols = row.find_all("td")
                if len(cols) < 4:
                    continue
                pgm_div = cols[0].find("div", class_=re.compile("paddingSaddleCloths"))
                if not pgm_div:
                    continue
                winner_pgm = pgm_div.get_text(strip=True)
                a = cols[1].find("a")
                if a:
                    winner = a.get_text(strip=True)
                w = cols[3].get_text(strip=True).replace("\xa0", "").strip()
                try: win_pay = float(w)
                except: pass
                if len(cols) > 4:
                    p = cols[4].get_text(strip=True).replace("\xa0", "").strip()
                    try: place_pay = float(p)
                    except: pass
                if len(cols) > 5:
                    s = cols[5].get_text(strip=True).replace("\xa0", "").strip()
                    try: show_pay = float(s)
                    except: pass
                break
            if winner:
                break

        if winner:
            race_results.append({
                "track": track_code, "race_date": race_date, "race_num": race_num,
                "winner": winner, "winner_pgm": winner_pgm,
                "win_payout": win_pay, "place_payout": place_pay, "show_payout": show_pay,
                "race_type": race_type, "distance": distance,
                "surface": "Dirt" if "dirt" in distance.lower() else "Turf" if "turf" in distance.lower() else "",
                "purse": purse, "winning_time": win_time, "field_size": field_size,
                "track_condition": track_cond or None,
                "winner_morning_line": winner_ml,
                "implied_prob": odds_to_implied_prob(winner_ml),
            })

        # Exotic payouts
        for wtbl in race_div.find_all("table", class_="fullwidth"):
            hdrs = [th.get_text(strip=True).lower() for th in wtbl.find_all("th")]
            if "wager type" not in " ".join(hdrs):
                continue
            for row in wtbl.find_all("tr"):
                if row.find("th"):
                    continue
                cols = row.find_all("td")
                if len(cols) < 3:
                    continue
                wager_raw = cols[0].get_text(strip=True)
                combo_raw = cols[1].get_text(strip=True)
                pay_raw   = cols[2].get_text(strip=True)
                wu = wager_raw.upper()
                if   "DAILY DOUBLE" in wu: wtype, nr = "DD",  2
                elif "PICK 3"       in wu: wtype, nr = "P3",  3
                elif "PICK 4"       in wu: wtype, nr = "P4",  4
                elif "PICK 5"       in wu: wtype, nr = "P5",  5
                elif "PICK 6"       in wu: wtype, nr = "P6",  6
                elif "EXACTA"       in wu: wtype, nr = "EX",  1
                elif "TRIFECTA"     in wu: wtype, nr = "TRI", 1
                elif "SUPERFECTA"   in wu: wtype, nr = "SF",  1
                else: continue
                amt = re.match(r"(\$[\d.]+)", wager_raw)
                base_amt = amt.group(1) if amt else "$1"
                if amt:
                    wager_base = float(amt.group(1).replace('$', ''))
                else:
                    wager_base = _DEFAULT_WAGER_BASES.get(wtype, 2.0)
                combo = re.sub(r"\(.*?\)", "", combo_raw).strip()
                try:
                    payout = float(pay_raw.replace(",", ""))
                except:
                    continue
                race_span = str(race_num) if nr == 1 else "-".join(
                    str(r) for r in range(race_num - nr + 1, race_num + 1))
                payout_per_2 = round(payout * (2.0 / wager_base), 2) if wager_base > 0 else payout
                exotic_payouts.append({
                    "track": track_code, "race_date": race_date, "race_num": race_num,
                    "wager_type": wtype, "race_span": race_span,
                    "winning_combo": combo, "base_amount": base_amt, "payout": payout,
                    "wager_base": wager_base, "payout_per_2": payout_per_2,
                })

    print(f"  Found {len(race_results)} race winners, {len(exotic_payouts)} exotic payouts")
    return race_results, exotic_payouts


# ── Database Writer ──────────────────────────────────────────────────────────

def save_to_db(conn, race_results, exotic_payouts):
    c = conn.cursor()
    for r in race_results:
        c.execute("""
            INSERT OR REPLACE INTO race_results
            (track, race_date, race_num, winner, winner_pgm, win_payout,
             place_payout, show_payout, race_type, distance, surface, purse, winning_time,
             field_size, track_condition, winner_morning_line, implied_prob)
            VALUES (:track, :race_date, :race_num, :winner, :winner_pgm, :win_payout,
                    :place_payout, :show_payout, :race_type, :distance, :surface, :purse, :winning_time,
                    :field_size, :track_condition, :winner_morning_line, :implied_prob)
        """, r)
    for e in exotic_payouts:
        c.execute("""
            INSERT OR REPLACE INTO exotic_payouts
            (track, race_date, race_num, wager_type, race_span, winning_combo,
             base_amount, payout, wager_base, payout_per_2)
            VALUES (:track, :race_date, :race_num, :wager_type, :race_span,
                    :winning_combo, :base_amount, :payout, :wager_base, :payout_per_2)
        """, e)
    conn.commit()
    print("  Saved to database.")


# ── Card Summary ─────────────────────────────────────────────────────────────

def _safe_print(text):
    """Print a line, replacing any characters the console can't encode."""
    print(text.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8", errors="replace"))


def get_card_summary(conn, track, race_date):
    c = conn.cursor()
    winners = c.execute("""
        SELECT race_num, winner, winner_pgm, win_payout, race_type, distance
        FROM race_results WHERE track=? AND race_date=? ORDER BY race_num
    """, (track, race_date)).fetchall()
    exotics = c.execute("""
        SELECT race_num, wager_type, race_span, winning_combo, base_amount, payout
        FROM exotic_payouts WHERE track=? AND race_date=? ORDER BY race_num, wager_type
    """, (track, race_date)).fetchall()

    _safe_print(f"\n{'='*65}")
    _safe_print(f"  {track}  |  {race_date}  |  {len(winners)} races")
    _safe_print(f"{'='*65}")
    for rn, winner, pgm, win_pay, rtype, dist in winners:
        pay_str = f"${win_pay:.2f}" if win_pay else "N/A"
        _safe_print(f"\nRace {rn}: #{pgm} {winner}  WIN: {pay_str}  [{rtype}]")
        for e_rn, wtype, rspan, combo, amt, pay in exotics:
            races_in_span = [int(x) for x in rspan.split("-") if x.strip().isdigit()]
            if rn in races_in_span or e_rn == rn:
                label = {
                    "DD":"Daily Double","P3":"Pick 3","P4":"Pick 4","P5":"Pick 5",
                    "P6":"Pick 6","EX":"Exacta","TRI":"Trifecta","SF":"Superfecta"
                }.get(wtype, wtype)
                span_str = f"R{rspan}" if "-" in rspan else f"R{e_rn}"
                _safe_print(f"  +- {amt} {label:<14} {span_str:<10} {combo:<16} ${pay:,.2f}")


# ── Google Sheets Export ─────────────────────────────────────────────────────

def build_summary(races_df, exotics_df):
    rows = []
    for date in races_df["race_date"].unique():
        d_races   = races_df[races_df["race_date"] == date].sort_values("race_num")
        d_exotics = exotics_df[exotics_df["race_date"] == date]
        for _, race in d_races.iterrows():
            rn = race["race_num"]
            row = {
                "Date": date, "Track": race["track"], "Race": rn,
                "Winner": race["winner"], "Pgm": race["winner_pgm"],
                "Win $": race["win_payout"], "Place $": race["place_payout"],
                "Show $": race["show_payout"], "Race Type": race["race_type"],
                "Distance": race["distance"], "Purse": race["purse"],
                "Time": race["winning_time"],
            }
            for wtype, label in [("DD","DD"),("P3","P3"),("P4","P4"),("P5","P5"),("P6","P6")]:
                m = d_exotics[(d_exotics["race_num"] == rn) & (d_exotics["wager_type"] == wtype)]
                row[f"{label} Combo"]  = m.iloc[0]["winning_combo"] if not m.empty else ""
                row[f"{label} Payout"] = m.iloc[0]["payout"]        if not m.empty else ""
                row[f"{label} Races"]  = m.iloc[0]["race_span"]     if not m.empty else ""
            rows.append(row)
    return pd.DataFrame(rows)


def write_tab(sheet, tab_name, df):
    try:
        ws = sheet.worksheet(tab_name)
        ws.clear()
    except gspread.exceptions.WorksheetNotFound:
        ws = sheet.add_worksheet(title=tab_name, rows=5000, cols=40)
    df = df.fillna("")
    data = [df.columns.tolist()] + df.values.tolist()
    ws.update(data, value_input_option="USER_ENTERED")
    print(f"  Written: '{tab_name}' ({len(df)} rows)")
    time.sleep(1)


def export_to_gsheets(conn, track):
    print("\nConnecting to Google Sheets...")
    try:
        sheet = get_gsheet()
    except Exception as e:
        print(f"  ERROR connecting to Google Sheets: {e}")
        return
    races_df   = pd.read_sql("SELECT * FROM race_results WHERE track=? ORDER BY race_date, race_num", conn, params=(track,))
    exotics_df = pd.read_sql("SELECT * FROM exotic_payouts WHERE track=? ORDER BY race_date, race_num, wager_type", conn, params=(track,))
    write_tab(sheet, track, build_summary(races_df, exotics_df))
    all_races   = pd.read_sql("SELECT * FROM race_results ORDER BY track, race_date, race_num", conn)
    all_exotics = pd.read_sql("SELECT * FROM exotic_payouts ORDER BY track, race_date, race_num, wager_type", conn)
    write_tab(sheet, "All Tracks Summary", build_summary(all_races, all_exotics))
    write_tab(sheet, "All Winners",  all_races)
    write_tab(sheet, "All Exotics",  all_exotics)
    print(f"\nDone. Google Sheets updated: '{SHEET_NAME}'")


# ── Main ─────────────────────────────────────────────────────────────────────

def already_scraped(conn, track_code, race_date):
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*) FROM race_results WHERE track=? AND race_date=?",
        (track_code, race_date)
    )
    return c.fetchone()[0] > 0


def scrape_date_range(track_code, dates, db_path="horse_racing.db"):
    conn = init_db(db_path)

    # Filter out dates already in the database before opening a browser
    dates_to_scrape = []
    for date_str in dates:
        dt = datetime.strptime(date_str, "%m%d%y")
        race_date = dt.strftime("%Y-%m-%d")
        if already_scraped(conn, track_code, race_date):
            print(f"Skipping {track_code} {race_date} — already in database")
        else:
            dates_to_scrape.append(date_str)

    if not dates_to_scrape:
        print("All dates already in database. Nothing to scrape.")
        conn.close()
        return

    driver = create_driver()
    any_data_saved = False
    try:
        for i, date_str in enumerate(dates_to_scrape):
            dt = datetime.strptime(date_str, "%m%d%y")
            race_date = dt.strftime("%Y-%m-%d")
            url = build_equibase_url(track_code, date_str)
            try:
                race_results, exotic_payouts = scrape_card(
                    driver, url, track_code, race_date, first_page=(i == 0)
                )
                if race_results or exotic_payouts:
                    save_to_db(conn, race_results, exotic_payouts)
                    any_data_saved = True
                    get_card_summary(conn, track_code, race_date)
            except Exception as e:
                print(f"  Skipping {race_date} due to error: {e}")
                # If browser crashed, restart it for next date
                try:
                    driver.quit()
                except:
                    pass
                driver = create_driver()
                print("  Browser restarted.")
            time.sleep(2)
    finally:
        try:
            driver.quit()
        except:
            pass
        print("  Browser closed.")
    if any_data_saved:
        export_to_gsheets(conn, track_code)
    else:
        print("  No data returned for any date — skipping Google Sheets export.")
    conn.close()


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    scrape_date_range(
        track_code="SA",
        dates=[
            "032526","032626","032726","032826","032926","033026","033126",
            "040126","040226","040326","040426","040526","040626","040726",
            "040826","040926","041026","041126","041226","041326","041426",
            "041526","041626","041726","041826","041926","042026","042126",
            "042226",
        ]
    )
