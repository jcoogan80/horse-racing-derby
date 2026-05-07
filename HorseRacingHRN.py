"""
HorseRacingHRN.py — Multi-track results scraper (Horse Racing Nation)

Usage:
    python HorseRacingHRN.py [--track CODE] <date|start end|shortcut> [--dry-run]

Examples:
    python HorseRacingHRN.py 2025-05-01                          CD single day
    python HorseRacingHRN.py spring2025                          CD spring meet
    python HorseRacingHRN.py fall2025                            CD fall meet
    python HorseRacingHRN.py --track FG 2025-02-01               FG single day
    python HorseRacingHRN.py --track FG 2025-01-01 2025-03-31    FG date range
    python HorseRacingHRN.py --track OP spring2025               OP spring meet
    python HorseRacingHRN.py --track PIM spring2025              PIM spring meet
    python HorseRacingHRN.py --track BEL spring2025              BEL spring meet
    python HorseRacingHRN.py --list-tracks                       show all tracks

Flags:
    --track CODE    track code to scrape (default: CD)
    --dry-run       parse only, do not write to database
    --list-tracks   print all supported track codes and exit

Requires: pip install requests beautifulsoup4
"""

import re
import sys
import os
import time
import sqlite3

import requests
from bs4 import BeautifulSoup
from datetime import date, timedelta

# ── Track registry ────────────────────────────────────────────────────────────

TRACK_SLUGS = {
    "CD":  "churchill-downs",
    "FG":  "fair-grounds",
    "OP":  "oaklawn-park",
    "SA":  "santa-anita-park",
    "GP":  "gulfstream-park",
    "KEE": "keeneland",
    "AQU": "aqueduct",
    "PIM": "pimlico",
    "BEL": "belmont-park",
    "TAM": "tampa-bay-downs",
    "TUP": "turfway-park",
    "MVR": "mahoning-valley",
}

DEFAULT_TRACK = "CD"

# ── Shortcut date ranges (per track) ─────────────────────────────────────────
# Keys are shortcut keywords; values map track code → (start, end).
# Tracks not listed for a given shortcut will fall back to the "CD" entry
# if they share a season name, but will error if completely absent.

SHORTCUTS = {
    "spring2025": {
        "CD":  ("2025-04-26", "2025-06-29"),
        "FG":  ("2025-01-01", "2025-03-31"),
        "OP":  ("2025-01-15", "2025-05-05"),
        "PIM": ("2025-04-01", "2025-05-31"),
        "BEL": ("2025-05-01", "2025-07-06"),
        "KEE": ("2025-04-04", "2025-04-27"),
        "SA":  ("2025-01-01", "2025-06-22"),
        "GP":  ("2025-01-01", "2025-04-06"),
        "TAM": ("2025-01-01", "2025-05-04"),
    },
    "fall2025": {
        "CD":  ("2025-10-31", "2025-11-29"),
        "KEE": ("2025-10-03", "2025-10-26"),
    },
}

# ── Config ────────────────────────────────────────────────────────────────────

HRN_URL = "https://entries.horseracingnation.com/entries-results/{slug}/{date}"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "horse_racing.db")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Exotic pool name → internal wager type code
WAGER_MAP = {
    "EXACTA":       "EX",
    "TRIFECTA":     "TRI",
    "SUPERFECTA":   "SF",
    "DAILY DOUBLE": "DD",
    "PICK 3":       "P3",
    "PICK 4":       "P4",
    "PICK 5":       "P5",
    "PICK 6":       "P6",   # covers "Pick 6 Jackpot", "Derby City-6", etc.
}

# Pool names containing any of these substrings are ignored
SKIP_POOL = ("CONSOLATION", "SUPER HIGH FIVE", "Z-5", "HI-5")

# Number of legs per wager type (used to compute race_span)
WAGER_LEGS = {
    "EX": 1, "TRI": 1, "SF": 1,
    "DD": 2, "P3": 3, "P4": 4, "P5": 5, "P6": 6,
}

# HRN posts payouts already normalized to a $2 base (column header "$2 Payout")
HRN_WAGER_BASE = 2.0


# ── Helpers ───────────────────────────────────────────────────────────────────

def odds_to_implied_prob(odds_str):
    """Convert fractional ML odds string to implied probability (0–1)."""
    if not odds_str:
        return None
    s = odds_str.strip().lower()
    if s in ("even", "e", "1/1", "1-1"):
        return 0.5
    m = re.match(r"^(\d+(?:\.\d+)?)[/\-](\d+(?:\.\d+)?)$", s)
    if m:
        num, den = float(m.group(1)), float(m.group(2))
        if num + den == 0:
            return None
        return round(den / (num + den), 6)
    m = re.match(r"^(\d+(?:\.\d+)?)$", s)
    if m:
        num = float(m.group(1))
        return round(1.0 / (num + 1.0), 6)
    return None


def _date_range(start: str, end: str):
    """Yield ISO date strings from start to end (inclusive)."""
    d    = date.fromisoformat(start)
    stop = date.fromisoformat(end)
    while d <= stop:
        yield d.isoformat()
        d += timedelta(days=1)


def _race_span(race_num: int, wtype: str) -> str:
    """Compute the race span string for a wager type ending at race_num."""
    legs = WAGER_LEGS.get(wtype, 1)
    if legs == 1:
        return str(race_num)
    return "-".join(str(r) for r in range(race_num - legs + 1, race_num + 1))


def _strip_speed_figure(text: str) -> str:
    """Strip trailing speed figure: 'Marmo (91)' → 'Marmo'."""
    return re.sub(r"\s*\(\d+\)\s*$", "", text).strip()


def _resolve_shortcut(keyword: str, track: str):
    """
    Return list of date strings for a shortcut keyword + track combination.
    Raises SystemExit if no mapping exists for this track.
    """
    mapping = SHORTCUTS.get(keyword)
    if mapping is None:
        print(f"Unknown shortcut '{keyword}'. Available: {', '.join(SHORTCUTS)}")
        sys.exit(1)
    if track not in mapping:
        available = ", ".join(sorted(mapping))
        print(
            f"Shortcut '{keyword}' has no date range defined for track {track}.\n"
            f"Tracks with '{keyword}' defined: {available}"
        )
        sys.exit(1)
    start, end = mapping[track]
    return list(_date_range(start, end))


# ── Scraper ───────────────────────────────────────────────────────────────────

def scrape_hrn_day(date_str: str, track: str):
    """
    Fetch and parse one race card from HRN for the given track and date.
    Returns (race_results, exotic_payouts) as lists of dicts ready for DB insert.
    Returns ([], []) if the page has no results.
    """
    slug = TRACK_SLUGS[track]
    url  = HRN_URL.format(slug=slug, date=date_str)
    print(f"Fetching {url}")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
    except requests.RequestException as e:
        print(f"  Request error: {e}")
        return [], []

    if resp.status_code != 200:
        print(f"  HTTP {resp.status_code} -- skipping")
        return [], []

    if len(resp.content) < 10_000:
        print(f"  Page too small ({len(resp.content):,} bytes) -- skipping")
        return [], []

    soup      = BeautifulSoup(resp.text, "html.parser")
    race_divs = soup.find_all("div", class_="my-5")
    print(f"  {len(race_divs)} race block(s) found")

    race_results   = []
    exotic_payouts = []

    for div in race_divs:
        # ── Race number ──────────────────────────────────────────────────────
        anchor = div.find("a", class_="race-header")
        if not anchor:
            continue
        id_attr = anchor.get("id", "")
        m = re.search(r"race-(\d+)", id_attr)
        if not m:
            m = re.search(r"Race\s+(\d+)", anchor.get_text(), re.I)
        if not m:
            continue
        race_num = int(m.group(1))

        # ── Race metadata ────────────────────────────────────────────────────
        purse = distance = surface = race_type = ""

        purse_div = div.find("div", class_="race-purse")
        if purse_div:
            pm    = re.search(r"\$([\d,]+)", purse_div.get_text(strip=True))
            purse = "$" + pm.group(1) if pm else purse_div.get_text(strip=True)

        dist_div = div.find("div", class_="race-distance")
        if dist_div:
            distance = dist_div.get_text(" ", strip=True)
            dl = distance.lower()
            if "turf" in dl:
                surface = "Turf"
            elif "synthetic" in dl or "all weather" in dl or "polytrack" in dl:
                surface = "Synthetic"
            else:
                surface = "Dirt"

        restrict_div = div.find("div", class_="race-restrictions")
        if restrict_div:
            race_type = restrict_div.get_text(" ", strip=True)[:100]

        # ── Entries table: pgm → ML map, field size ──────────────────────────
        ml_map     = {}
        field_size = 0

        entries_tbl = div.find("table", class_="table-entries")
        if entries_tbl:
            for row in entries_tbl.find_all("tr"):
                if row.find("th"):
                    continue
                cols = row.find_all("td")
                if len(cols) < 2:
                    continue
                pgm_img = cols[0].find("img")
                pgm     = pgm_img["alt"].strip() if pgm_img and pgm_img.get("alt") else ""
                ml_val  = cols[-1].get_text(strip=True)
                scratch_col = next(
                    (c for c in cols if "scratch" in " ".join(c.get("class", []))),
                    None,
                )
                is_scratch = bool(scratch_col and scratch_col.get_text(strip=True))
                if not is_scratch:
                    field_size += 1
                if pgm and ml_val and ml_val not in ("-", "", "SCR", "Scr"):
                    ml_map[pgm] = ml_val

        # ── Payouts table: winner + win/place/show ───────────────────────────
        winner = winner_pgm = ""
        win_pay = place_pay = show_pay = None

        payouts_tbl = div.find("table", class_="table-payouts")
        if payouts_tbl:
            for row in payouts_tbl.find_all("tr"):
                if row.find("th"):
                    continue
                cols = row.find_all("td")
                if len(cols) < 3:
                    continue
                if cols[0].get_text(strip=True).startswith("*"):
                    continue   # footnote row

                # Layout: col[0]=horse+speed, col[1]=pgm img, col[2]=Win, col[3]=Place, col[4]=Show
                win_raw = cols[2].get_text(strip=True).replace(",", "").replace("$", "")
                try:
                    wp = float(win_raw)
                except ValueError:
                    continue
                if wp <= 0:
                    continue

                pgm_img    = cols[1].find("img")
                winner_pgm = pgm_img["alt"].strip() if pgm_img and pgm_img.get("alt") else ""
                winner     = _strip_speed_figure(cols[0].get_text(strip=True))
                win_pay    = wp

                if len(cols) > 3:
                    pr = cols[3].get_text(strip=True).replace(",", "").replace("$", "")
                    try:
                        place_pay = float(pr)
                    except ValueError:
                        pass
                if len(cols) > 4:
                    sr = cols[4].get_text(strip=True).replace(",", "").replace("$", "")
                    try:
                        show_pay = float(sr)
                    except ValueError:
                        pass
                break

        if not winner:
            continue

        winner_ml = ml_map.get(winner_pgm) or ml_map.get(winner_pgm.lstrip("0"))
        implied   = odds_to_implied_prob(winner_ml)

        race_results.append({
            "track":               track,
            "race_date":           date_str,
            "race_num":            race_num,
            "winner":              winner,
            "winner_pgm":          winner_pgm,
            "win_payout":          win_pay,
            "place_payout":        place_pay,
            "show_payout":         show_pay,
            "race_type":           race_type,
            "distance":            distance,
            "surface":             surface,
            "purse":               purse,
            "winning_time":        None,
            "field_size":          field_size if field_size > 0 else None,
            "track_condition":     None,
            "winner_morning_line": winner_ml,
            "implied_prob":        implied,
        })

        # ── Exotic payouts table ─────────────────────────────────────────────
        exotic_tbl = div.find("table", class_="table-exotic-payouts")
        if not exotic_tbl:
            continue

        for row in exotic_tbl.find_all("tr"):
            if row.find("th"):
                continue
            cols = row.find_all("td")
            if len(cols) < 3:
                continue

            pool_raw  = cols[0].get_text(strip=True)
            combo_raw = cols[1].get_text(strip=True)
            pay_raw   = cols[2].get_text(strip=True).replace(",", "").replace("$", "")

            pu = pool_raw.upper()
            if any(sk in pu for sk in SKIP_POOL):
                continue

            wtype = None
            for key, wt in WAGER_MAP.items():
                if key in pu:
                    wtype = wt
                    break
            if wtype is None:
                continue

            try:
                payout = float(pay_raw)
            except ValueError:
                continue
            if payout <= 0:
                continue

            race_span = _race_span(race_num, wtype)

            # HRN already posts $2-normalized payouts
            exotic_payouts.append({
                "track":         track,
                "race_date":     date_str,
                "race_num":      race_num,
                "wager_type":    wtype,
                "race_span":     race_span,
                "winning_combo": combo_raw.strip(),
                "base_amount":   "$2",
                "payout":        round(payout, 2),
                "wager_base":    HRN_WAGER_BASE,
                "payout_per_2":  round(payout, 2),
            })

    print(f"  Parsed: {len(race_results)} winners, {len(exotic_payouts)} exotic payouts")
    return race_results, exotic_payouts


# ── Database ──────────────────────────────────────────────────────────────────

def import_to_db(race_results, exotic_payouts, db_path=DB_PATH):
    """
    Insert parsed results into horse_racing.db.
    Uses INSERT OR IGNORE so re-running is safe (existing rows are skipped).
    Returns (races_new, races_skipped, exotics_new, exotics_skipped).
    """
    conn = sqlite3.connect(db_path)
    c    = conn.cursor()

    races_new = races_skipped = 0
    for r in race_results:
        c.execute("""
            INSERT OR IGNORE INTO race_results
            (track, race_date, race_num, winner, winner_pgm, win_payout,
             place_payout, show_payout, race_type, distance, surface, purse,
             winning_time, field_size, track_condition,
             winner_morning_line, implied_prob)
            VALUES
            (:track, :race_date, :race_num, :winner, :winner_pgm, :win_payout,
             :place_payout, :show_payout, :race_type, :distance, :surface, :purse,
             :winning_time, :field_size, :track_condition,
             :winner_morning_line, :implied_prob)
        """, r)
        if c.rowcount:
            races_new += 1
        else:
            races_skipped += 1

    exotics_new = exotics_skipped = 0
    for e in exotic_payouts:
        c.execute("""
            INSERT OR IGNORE INTO exotic_payouts
            (track, race_date, race_num, wager_type, race_span,
             winning_combo, base_amount, payout, wager_base, payout_per_2)
            VALUES
            (:track, :race_date, :race_num, :wager_type, :race_span,
             :winning_combo, :base_amount, :payout, :wager_base, :payout_per_2)
        """, e)
        if c.rowcount:
            exotics_new += 1
        else:
            exotics_skipped += 1

    conn.commit()
    conn.close()
    return races_new, races_skipped, exotics_new, exotics_skipped


# ── CLI ───────────────────────────────────────────────────────────────────────

def _print_day(date_str, track, race_results, exotic_payouts):
    """Print a formatted summary of one day's results."""
    WLABEL = {
        "DD": "Daily Double", "P3": "Pick 3",  "P4": "Pick 4",
        "P5": "Pick 5",       "P6": "Pick 6",  "EX": "Exacta",
        "TRI": "Trifecta",    "SF": "Superfecta",
    }
    print(f"\n{'='*65}")
    print(f"  {track}  |  {date_str}  |  {len(race_results)} races")
    print(f"{'='*65}")

    ex_by_rn = {}
    for e in exotic_payouts:
        ex_by_rn.setdefault(e["race_num"], []).append(e)

    for r in sorted(race_results, key=lambda x: x["race_num"]):
        rn = r["race_num"]
        ml = f"  ML:{r['winner_morning_line']}" if r["winner_morning_line"] else ""
        print(
            f"\nRace {rn:>2}: #{r['winner_pgm']:<3} {r['winner'][:22]:<22}"
            f"  WIN: ${r['win_payout']:.2f}{ml}"
        )
        for e in sorted(ex_by_rn.get(rn, []), key=lambda x: x["wager_type"]):
            label = WLABEL.get(e["wager_type"], e["wager_type"])
            print(
                f"         {label:<14} R{e['race_span']:<10}"
                f" {e['winning_combo'][:20]:<20} ${e['payout']:>8,.2f}"
            )


def _list_tracks():
    print(f"{'Code':<6} {'Slug'}")
    print("-" * 40)
    for code, slug in sorted(TRACK_SLUGS.items()):
        print(f"{code:<6} {slug}")


def _parse_args(argv):
    """
    Parse command-line arguments.
    Returns (track, dates, dry_run).
    """
    args = list(argv)

    # --list-tracks (handled before this function returns)
    if "--list-tracks" in args:
        _list_tracks()
        sys.exit(0)

    dry_run = "--dry-run" in args
    args = [a for a in args if a != "--dry-run"]

    # --track CODE
    track = DEFAULT_TRACK
    if "--track" in args:
        idx = args.index("--track")
        if idx + 1 >= len(args):
            print("--track requires a track code argument.")
            sys.exit(1)
        track = args[idx + 1].upper()
        args  = args[:idx] + args[idx + 2:]

    if track not in TRACK_SLUGS:
        print(f"Unknown track code '{track}'.")
        _list_tracks()
        sys.exit(1)

    if not args:
        print(__doc__)
        sys.exit(1)

    # Expand positional args into a flat date list
    IS_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    dates   = []
    i       = 0
    while i < len(args):
        t = args[i]
        if IS_DATE.match(t):
            # Check if next arg is also a date → treat as start/end range
            if i + 1 < len(args) and IS_DATE.match(args[i + 1]):
                dates.extend(_date_range(t, args[i + 1]))
                i += 2
            else:
                dates.append(t)
                i += 1
        elif t in SHORTCUTS:
            dates.extend(_resolve_shortcut(t, track))
            i += 1
        else:
            print(f"Unknown argument: '{t}'  (expected YYYY-MM-DD or a shortcut keyword)")
            sys.exit(1)

    return track, dates, dry_run


def main():
    track, dates, dry_run = _parse_args(sys.argv[1:])

    label = "DRY RUN -- " if dry_run else ""
    print(f"{label}Scraping {len(dates)} date(s) for {track} ({TRACK_SLUGS[track]})")

    total_races   = 0
    total_exotics = 0

    for i, d in enumerate(dates):
        if i > 0:
            time.sleep(1.5)

        race_results, exotic_payouts = scrape_hrn_day(d, track)

        if not race_results and not exotic_payouts:
            continue

        total_races   += len(race_results)
        total_exotics += len(exotic_payouts)

        if dry_run:
            _print_day(d, track, race_results, exotic_payouts)
        else:
            rn, rs, en, es = import_to_db(race_results, exotic_payouts)
            print(f"  DB: +{rn} races ({rs} skipped), +{en} exotics ({es} skipped)")

    print(f"\nDone. Total parsed: {total_races} race winners, {total_exotics} exotic payouts.")
    if dry_run:
        print("(Dry run -- nothing written to database.)")


if __name__ == "__main__":
    main()
