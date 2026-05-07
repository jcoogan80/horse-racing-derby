"""
scrape_entries.py — Scrape morning line entries + detect also-eligible (AE) horses
from entries.horseracingnation.com

The same HRN URL used by HorseRacingHRN.py serves entries before races run
and results after. This script reads entries (pre-race) data to extract morning
line odds and flag AE horses that drew in via scratch.

Usage:
    python scrape_entries.py                    # today, all configured tracks
    python scrape_entries.py CD                 # today, CD only
    python scrape_entries.py CD 2026-05-03      # specific date + track

Flags:
    --dry-run   print parsed data without writing to DB
    --force     overwrite existing entries for this track+date

Requires: pip install requests beautifulsoup4
"""

import re
import sys
import os
import time
import sqlite3
from datetime import date as _date, datetime

import requests
from bs4 import BeautifulSoup

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "horse_racing.db")

HRN_URL = "https://entries.horseracingnation.com/entries-results/{slug}/{date}"

TRACK_SLUGS = {
    "CD":  "churchill-downs",
    "GP":  "gulfstream-park",
    "FG":  "fair-grounds",
    "OP":  "oaklawn-park",
    "SA":  "santa-anita-park",
    "AQU": "aqueduct",
    "KEE": "keeneland",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def odds_to_decimal(s):
    """
    Convert ML odds string to decimal odds.
    Examples: '5/2' -> 2.5,  '10-1' -> 10.0,  'even' -> 1.0,  '8/5' -> 1.6
    Returns None if unparseable.
    """
    if not s:
        return None
    s = s.strip().lower().replace('\xa0', '').replace(',', '')
    if s in ('even', 'e', '1/1', '1-1', 'evens'):
        return 1.0
    m = re.match(r'^(\d+(?:\.\d+)?)[/\-](\d+(?:\.\d+)?)$', s)
    if m:
        num, den = float(m.group(1)), float(m.group(2))
        return round(num / den, 4) if den else None
    m = re.match(r'^(\d+(?:\.\d+)?)$', s)
    if m:
        return float(m.group(1))
    return None


def _parse_purse(text):
    m = re.search(r'\$([\d,]+)', text)
    if m:
        try:
            return float(m.group(1).replace(',', ''))
        except ValueError:
            pass
    return None


def _detect_surface(distance_text):
    dl = distance_text.lower()
    if 'turf' in dl:
        return 'Turf'
    if 'synthetic' in dl or 'all weather' in dl or 'polytrack' in dl:
        return 'Synthetic'
    return 'Dirt'


def _strip_speed_figure(text):
    # HRN entries cells contain "HorseName(SpeedFig)SireName" — strip from first (digits) onward
    return re.sub(r'\s*\(\d+\).*$', '', text).strip()


# ── DB Setup ─────────────────────────────────────────────────────────────────

def init_entries_tables(conn):
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            track            TEXT NOT NULL,
            race_date        TEXT NOT NULL,
            race_num         INTEGER NOT NULL,
            race_type        TEXT,
            distance         TEXT,
            surface          TEXT,
            purse            REAL,
            listed_field_size INTEGER,
            scraped_at       TEXT,
            UNIQUE(track, race_date, race_num)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS entry_horses (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id         INTEGER REFERENCES entries(id),
            track            TEXT NOT NULL,
            race_date        TEXT NOT NULL,
            race_num         INTEGER NOT NULL,
            program_num      TEXT,
            horse_name       TEXT,
            morning_line_odds REAL,
            jockey           TEXT,
            trainer          TEXT,
            is_ae            INTEGER DEFAULT 0,
            scratched        INTEGER DEFAULT 0
        )
    """)
    try:
        c.execute("ALTER TABLE entry_horses ADD COLUMN scratched INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Column already exists
    conn.commit()


# ── Scraper ───────────────────────────────────────────────────────────────────

def scrape_entries_day(date_str, track):
    """
    Fetch and parse one entries card from HRN for the given track and date.
    Returns a list of race dicts, each with keys:
        race_num, race_type, distance, surface, purse,
        listed_field_size, horses (list of horse dicts)
    Returns [] if the page has no entries or an error occurs.
    """
    slug = TRACK_SLUGS[track]
    url  = HRN_URL.format(slug=slug, date=date_str)
    print(f"Fetching {url}")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
    except requests.RequestException as e:
        print(f"  Request error: {e}")
        return []

    if resp.status_code != 200:
        print(f"  HTTP {resp.status_code} — skipping")
        return []

    if len(resp.content) < 5_000:
        print(f"  Page too small ({len(resp.content):,} bytes) — likely no card today")
        return []

    soup      = BeautifulSoup(resp.text, 'html.parser')
    race_divs = soup.find_all('div', class_='my-5')
    print(f"  {len(race_divs)} race block(s) found")

    races = []

    for div in race_divs:
        # ── Race number ──────────────────────────────────────────────────────
        anchor = div.find('a', class_='race-header')
        if not anchor:
            continue
        id_attr = anchor.get('id', '')
        m = re.search(r'race-(\d+)', id_attr)
        if not m:
            m = re.search(r'Race\s+(\d+)', anchor.get_text(), re.I)
        if not m:
            continue
        race_num = int(m.group(1))

        # ── Race metadata ────────────────────────────────────────────────────
        purse = distance = surface = race_type = ''

        purse_div = div.find('div', class_='race-purse')
        if purse_div:
            purse = _parse_purse(purse_div.get_text(strip=True))

        dist_div = div.find('div', class_='race-distance')
        if dist_div:
            distance = dist_div.get_text(' ', strip=True)
            surface  = _detect_surface(distance)

        restrict_div = div.find('div', class_='race-restrictions')
        if restrict_div:
            race_type = restrict_div.get_text(' ', strip=True)[:100]

        # ── Entries table ────────────────────────────────────────────────────
        entries_tbl = div.find('table', class_='table-entries')
        if not entries_tbl:
            continue

        horses_raw = []
        for row in entries_tbl.find_all('tr'):
            if row.find('th'):
                continue
            cols = row.find_all('td')
            if len(cols) < 2:
                continue

            # Program number — image alt in first column
            pgm_img = cols[0].find('img')
            pgm     = pgm_img['alt'].strip() if pgm_img and pgm_img.get('alt') else ''
            if not pgm:
                continue

            # Scratch detection — column with "scratch" in its class list
            scratch_col = next(
                (c for c in cols if 'scratch' in ' '.join(c.get('class', []))),
                None,
            )
            is_scratch = bool(scratch_col and scratch_col.get_text(strip=True))

            # HRN entries table column layout:
            #   col[0] = program img,  col[1] = program number text (duplicate),
            #   col[2] = horse name,   col[3] = jockey,  col[4] = trainer,
            #   col[-1] = ML odds
            # If col[1] looks like another program number, shift right by 1.
            col1_text = cols[1].get_text(strip=True) if len(cols) > 1 else ''
            offset = 1 if (col1_text == pgm or re.match(r'^\d+[A-Za-z]?$', col1_text)) else 0

            name_col    = 1 + offset
            jockey_col  = 2 + offset
            trainer_col = 3 + offset

            horse_name = ''
            if len(cols) > name_col:
                name_cell = cols[name_col]
                # Prefer the horse-link anchor — avoids sire name in sibling <p>
                horse_link = name_cell.find('a', class_='horse-link')
                if horse_link:
                    horse_name = horse_link.get_text(strip=True)
                else:
                    # Some horses (e.g. foreign-bred) have no <a> — name is bare
                    # text in <h4>. Use <h4> text only to avoid the sire <p>.
                    h4 = name_cell.find('h4')
                    if h4:
                        horse_name = _strip_speed_figure(h4.get_text(strip=True))
                    else:
                        candidate = _strip_speed_figure(name_cell.get_text(strip=True))
                        if candidate and candidate not in ('-', '', pgm):
                            horse_name = candidate
            if not horse_name:
                col0_text = re.sub(r'^\d+[A-Za-z]?\s*', '',
                                   cols[0].get_text(strip=True)).strip()
                horse_name = _strip_speed_figure(col0_text)

            jockey  = cols[jockey_col].get_text(strip=True)  if len(cols) > jockey_col  else ''
            trainer = cols[trainer_col].get_text(strip=True) if len(cols) > trainer_col else ''

            # ML odds in last column
            ml_str     = cols[-1].get_text(strip=True)
            ml_decimal = None
            if ml_str and ml_str not in ('-', '', 'SCR', 'Scr', 'N/A', 'n/a'):
                ml_decimal = odds_to_decimal(ml_str)

            horses_raw.append({
                'program_num':       pgm,
                'horse_name':        horse_name,
                'morning_line_odds': ml_decimal,
                'jockey':            jockey,
                'trainer':           trainer,
                'scratched':         is_scratch,
            })

        if not horses_raw:
            continue

        # ── AE detection ─────────────────────────────────────────────────────
        # Find the largest consecutive program number sequence starting at 1.
        # Any horse with a numeric pgm beyond that sequence is an AE.
        # Coupled entries (1A, 1B) count with their base number.
        numeric_pgms = sorted(set(
            int(m.group(1))
            for h in horses_raw
            for m in [re.match(r'^(\d+)', h['program_num'])]
            if m
        ))
        listed_field_size = 0
        for i, n in enumerate(numeric_pgms):
            if n == i + 1:
                listed_field_size = n
            else:
                break
        if listed_field_size == 0 and numeric_pgms:
            listed_field_size = numeric_pgms[0]

        horses = []
        for h in horses_raw:
            pgm    = h['program_num']
            is_ae  = pgm.upper().startswith('AE')
            if not is_ae:
                base_m = re.match(r'^(\d+)', pgm)
                if base_m and int(base_m.group(1)) > listed_field_size:
                    is_ae = True
            horses.append({**h, 'is_ae': is_ae})

        races.append({
            'race_num':         race_num,
            'race_type':        race_type,
            'distance':         distance,
            'surface':          surface,
            'purse':            purse,
            'listed_field_size': listed_field_size,
            'horses':           horses,
        })

    ae_total = sum(1 for r in races for h in r['horses'] if h['is_ae'])
    print(f"  Parsed: {len(races)} race(s), "
          f"{sum(len(r['horses']) for r in races)} horse(s), "
          f"{ae_total} AE horse(s)")
    return races


# ── Database Writer ───────────────────────────────────────────────────────────

def save_entries(conn, track, date_str, races, force=False):
    """
    Insert races into entries + entry_horses tables.
    Skips existing track+date+race_num combos unless force=True.
    Returns (races_inserted, horses_inserted, ae_list).
    """
    c          = conn.cursor()
    scraped_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    races_inserted  = 0
    horses_inserted = 0
    ae_list         = []

    for race in races:
        race_num = race['race_num']

        c.execute(
            'SELECT id FROM entries WHERE track=? AND race_date=? AND race_num=?',
            (track, date_str, race_num)
        )
        existing = c.fetchone()

        if existing and not force:
            continue

        if existing and force:
            entry_id = existing[0]
            c.execute('DELETE FROM entry_horses WHERE entry_id=?', (entry_id,))
            c.execute(
                'UPDATE entries SET race_type=?, distance=?, surface=?, purse=?, '
                'listed_field_size=?, scraped_at=? WHERE id=?',
                (race['race_type'], race['distance'], race['surface'],
                 race['purse'], race['listed_field_size'], scraped_at, entry_id)
            )
        else:
            c.execute(
                'INSERT INTO entries '
                '(track, race_date, race_num, race_type, distance, surface, purse, '
                ' listed_field_size, scraped_at) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (track, date_str, race_num, race['race_type'], race['distance'],
                 race['surface'], race['purse'], race['listed_field_size'], scraped_at)
            )
            entry_id = c.lastrowid
            races_inserted += 1

        for h in race['horses']:
            c.execute(
                'INSERT INTO entry_horses '
                '(entry_id, track, race_date, race_num, program_num, horse_name, '
                ' morning_line_odds, jockey, trainer, is_ae, scratched) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (entry_id, track, date_str, race_num,
                 h['program_num'], h['horse_name'], h['morning_line_odds'],
                 h['jockey'], h['trainer'], 1 if h['is_ae'] else 0,
                 1 if h.get('scratched') else 0)
            )
            horses_inserted += 1
            if h['is_ae']:
                ae_list.append({
                    'track':        track,
                    'race_num':     race_num,
                    'program_num':  h['program_num'],
                    'horse_name':   h['horse_name'],
                    'morning_line': h['morning_line_odds'],
                })

    conn.commit()
    return races_inserted, horses_inserted, ae_list


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    pos_args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags    = {a for a in sys.argv[1:] if a.startswith('--')}
    dry_run  = '--dry-run' in flags
    force    = '--force'   in flags

    today = _date.today().isoformat()

    if len(pos_args) == 0:
        tracks   = list(TRACK_SLUGS.keys())
        date_str = today
    elif len(pos_args) == 1:
        tracks   = [pos_args[0].upper()]
        date_str = today
    else:
        tracks   = [pos_args[0].upper()]
        date_str = pos_args[1]

    for t in tracks:
        if t not in TRACK_SLUGS:
            print(f"Unknown track '{t}'. Supported: {', '.join(TRACK_SLUGS)}")
            sys.exit(1)

    conn = None
    if not dry_run:
        conn = sqlite3.connect(DB_PATH)
        init_entries_tables(conn)

    total_races  = 0
    total_horses = 0
    all_ae       = []
    all_races_by_track = {}

    for i, track in enumerate(tracks):
        if i > 0:
            time.sleep(1.5)

        races = scrape_entries_day(date_str, track)
        all_races_by_track[track] = races

        if dry_run:
            for r in races:
                ae_tag = f"  ({sum(1 for h in r['horses'] if h['is_ae'])} AE)" if any(h['is_ae'] for h in r['horses']) else ''
                print(f"  [DRY RUN] {track} Race {r['race_num']}: "
                      f"{r['listed_field_size']} starters, {r['surface']}{ae_tag}")
                for h in r['horses']:
                    ae_mark = '  *** AE ***' if h['is_ae'] else ''
                    ml      = f"  ML={h['morning_line_odds']}" if h['morning_line_odds'] is not None else ''
                    print(f"    {h['program_num']:>3}  {(h['horse_name'] or '?'):<30}{ml}{ae_mark}")
        else:
            if races:
                ins_r, ins_h, ae_list = save_entries(conn, track, date_str, races, force=force)
                total_races  += ins_r
                total_horses += ins_h
                all_ae.extend(ae_list)

    if conn:
        conn.close()

    print()
    print('=' * 46)
    print(f'ENTRIES SUMMARY  {track if len(tracks) == 1 else "ALL TRACKS"}  {date_str}')
    print('=' * 46)
    if dry_run:
        r_count = sum(len(r) for r in all_races_by_track.values())
        h_count = sum(len(r['horses']) for races in all_races_by_track.values() for r in races)
        print(f'DRY RUN — no data written')
        print(f'Would insert: {r_count} race(s), {h_count} horse(s)')
    else:
        print(f'Races inserted:  {total_races}')
        print(f'Horses inserted: {total_horses}')

    if all_ae:
        print(f'AE horses detected ({len(all_ae)}):')
        for ae in all_ae:
            ml_str = f"  ML {ae['morning_line']}" if ae['morning_line'] is not None else ''
            print(f"  {ae['track']} Race {ae['race_num']:>2}: "
                  f"#{ae['program_num']}  {ae['horse_name']}{ml_str}")
    elif not dry_run:
        print('No AE horses detected.')
