"""
test_scratch_pipeline.py — End-to-end scratch pipeline test (no live Equibase required).

Flow:
  1. DB injection   — insert 3 fake scratch rows directly
  2. JSON export    — call export_scratches_to_json, validate output
  3. Git push sim   — call push_scratches_to_github twice (real push + dedup)
  4. HTML rendering — local HTTP server + Selenium, dashboard + OptixEQ screenshots
  5. Date guard     — write yesterday's JSON, confirm banner is suppressed
  6. Cleanup        — remove test rows, print pass/fail table
"""

import sqlite3
import os
import sys
import json
import time
import functools
import threading
from datetime import datetime, timedelta
from http.server import HTTPServer, SimpleHTTPRequestHandler
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ScratchWatcher import (
    export_scratches_to_json, push_scratches_to_github,
    init_scratch_db, parse_time_posted, DB_PATH,
)
from HorseRacing import create_driver

TODAY     = datetime.now().strftime("%Y-%m-%d")
YESTERDAY = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
TRACK     = "CD"
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
WEB_DIR   = os.path.join(BASE_DIR, "web")
PORT      = 8765
SEP       = "=" * 62

results = {}  # key -> "PASS" | "FAIL"


def ok(key, msg=""):
    results[key] = "PASS"
    print(f"  [PASS] {msg or key}")


def fail(key, msg=""):
    results[key] = "FAIL"
    print(f"  [FAIL] {msg or key}")


def section(title):
    print(f"\n{SEP}\n  {title}\n{SEP}")


# ── Local HTTP server ─────────────────────────────────────────────────────────

class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass


def _start_server():
    handler = functools.partial(_QuietHandler, directory=WEB_DIR)
    srv = HTTPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# =============================================================================
# Step 1: DB Injection
# =============================================================================

section("Step 1: DB Injection")

TEST_HORSES = [
    (1,  "3",  "Fast Eddie",  "Scratched",  "PrivVet-Illness", "08:15 AM ET"),
    (3,  "7",  "Lucky Star",  "Scratched",  "Trainer",         "09:45 AM ET"),
    (7,  "13", "Derby Dream", "AE_ADDED",   "Manual Entry",    None),
]

conn = sqlite3.connect(DB_PATH)
init_scratch_db(conn)

# Pre-clean so the test is idempotent
conn.execute(
    "DELETE FROM scratch_alerts WHERE horse_name IN ('Fast Eddie','Lucky Star','Derby Dream')"
    " AND track=? AND date=?",
    (TRACK, TODAY),
)
conn.commit()

now_str   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
inserted  = 0
for race_num, pgm, horse, change_type, reason, time_posted in TEST_HORSES:
    tp_dt = parse_time_posted(time_posted)
    cur = conn.execute(
        """INSERT OR IGNORE INTO scratch_alerts
           (track, date, race_num, pgm, horse_name, change_type, reason,
            time_posted, time_posted_dt, detected_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (TRACK, TODAY, race_num, pgm, horse, change_type, reason,
         time_posted or "", tp_dt, now_str),
    )
    if cur.rowcount:
        inserted += 1
    print(f"  R{race_num} #{pgm:<3}  {horse:<22}  {change_type:<12}  "
          f"tp_dt={tp_dt!r}")

conn.commit()
conn.close()

if inserted == 3:
    ok("db_inject", "All 3 test rows inserted")
else:
    fail("db_inject", f"Only {inserted}/3 rows inserted")


# =============================================================================
# Step 2: JSON Export
# =============================================================================

section("Step 2: JSON Export")

out_path = export_scratches_to_json(TRACK, TODAY)
with open(out_path, encoding="utf-8") as f:
    data = json.load(f)

print(f"\n  web/data/scratches.json:\n")
print(json.dumps(data, indent=2))

errs = []
if data["track"] != TRACK:
    errs.append(f"track={data['track']!r}")
if data["date"] != TODAY:
    errs.append(f"date={data['date']!r}, expected {TODAY!r}")
if not data.get("generated_at"):
    errs.append("generated_at is empty")
if len(data["scratches"]) < 3:
    errs.append(f"expected >= 3 scratches, got {len(data['scratches'])}")
print(f"  Total scratches in JSON: {len(data['scratches'])} "
      f"(includes real CD data + 3 test rows)")

by_horse = {s["horse"]: s for s in data["scratches"]}

for horse, exp_dt in [("Fast Eddie", "08:15"), ("Lucky Star", "09:45")]:
    s = by_horse.get(horse)
    if not s:
        errs.append(f"'{horse}' missing from scratches")
    elif s.get("time_posted_dt") != exp_dt:
        errs.append(f"{horse} time_posted_dt={s.get('time_posted_dt')!r}, expected {exp_dt!r}")

derby = by_horse.get("Derby Dream")
if not derby:
    errs.append("'Derby Dream' missing from scratches")
else:
    if derby.get("time_posted_dt") is not None:
        errs.append(f"Derby Dream time_posted_dt={derby['time_posted_dt']!r}, expected None")
    if derby.get("change_type") != "AE_ADDED":
        errs.append(f"Derby Dream change_type={derby.get('change_type')!r}, expected 'AE_ADDED'")

if errs:
    fail("json_export", "Errors: " + "; ".join(errs))
else:
    ok("json_export",
       f"{len(data['scratches'])} total scratches, generated_at={data['generated_at']!r}, "
       f"3 test horses present with correct time_posted_dt")


# =============================================================================
# Step 3: Git Push Simulation
# =============================================================================

section("Step 3: Git Push Simulation")

print("  First call — should commit and push (or report already up-to-date)...")
try:
    push_scratches_to_github()
    ok("git_push_1", "push_scratches_to_github() completed without exception")
except Exception as e:
    fail("git_push_1", f"Exception: {e}")

print("\n  Second call — should report 'nothing to commit' gracefully...")
try:
    push_scratches_to_github()
    ok("git_push_2", "Second call completed gracefully (no crash)")
except Exception as e:
    fail("git_push_2", f"Exception on second call: {e}")


# =============================================================================
# Step 4: HTML Rendering Test
# =============================================================================

section("Step 4: HTML Rendering Test")

server = _start_server()
print(f"  HTTP server started: http://127.0.0.1:{PORT}/")
time.sleep(0.3)

driver = create_driver()
WAIT   = WebDriverWait(driver, 15)

try:
    # ── Dashboard ─────────────────────────────────────────────
    print("\n  [Dashboard] Loading page and waiting for loadScratches()...")
    driver.get(f"http://127.0.0.1:{PORT}/index.html")

    # Wait until scratch-banner has child content
    try:
        WAIT.until(lambda d: len(
            d.find_element(By.ID, "scratch-banner").get_attribute("innerHTML").strip()
        ) > 20)
        banner_loaded = True
    except Exception:
        banner_loaded = False

    banner_el   = driver.find_element(By.ID, "scratch-banner")
    banner_html = banner_el.get_attribute("innerHTML")

    if banner_loaded and len(banner_html.strip()) > 20:
        ok("dashboard_banner", "Scratch banner is visible and populated")
    else:
        fail("dashboard_banner",
             f"Banner empty or timed out. innerHTML[:200]={banner_html[:200]!r}")

    for horse in ["Fast Eddie", "Lucky Star", "Derby Dream"]:
        key = f"banner_{horse.replace(' ', '_').lower()}"
        if horse in banner_html:
            ok(key, f"'{horse}' present in banner")
        else:
            fail(key, f"'{horse}' NOT found in banner")

    # Screenshot
    shot1 = os.path.join(BASE_DIR, "test_dashboard.png")
    driver.save_screenshot(shot1)
    print(f"\n  Screenshot saved: test_dashboard.png")

    # ── OptixEQ ───────────────────────────────────────────────
    print("\n  [OptixEQ] Navigating to OptixEQ tab...")
    driver.execute_script("showTab('optixeq')")
    time.sleep(1)  # brief settle

    scr_badges  = driver.find_elements(By.CSS_SELECTOR, ".scr-badge")
    ae_badges   = driver.find_elements(By.CSS_SELECTOR, ".ae-badge")
    scratched   = driver.find_elements(By.CSS_SELECTOR, ".scratched-horse")

    print(f"  .scr-badge elements:     {len(scr_badges)}")
    print(f"  .ae-badge elements:      {len(ae_badges)}")
    print(f"  .scratched-horse elems:  {len(scratched)}")

    if len(scr_badges) >= 2:
        ok("scr_badges", f"{len(scr_badges)} SCR badge(s) injected across race cards")
    else:
        fail("scr_badges", f"Expected >= 2 SCR badges, found {len(scr_badges)}")

    if len(ae_badges) >= 1:
        ok("ae_badges", f"{len(ae_badges)} AE badge(s) injected")
    else:
        fail("ae_badges", f"Expected >= 1 AE badge, found {len(ae_badges)}")

    if len(scratched) >= 2:
        ok("strikethrough", f"{len(scratched)} .scratched-horse strikethrough(s) applied")
    else:
        fail("strikethrough", f"Expected >= 2 strikethroughs, found {len(scratched)}")

    shot2 = os.path.join(BASE_DIR, "test_optixeq.png")
    driver.save_screenshot(shot2)
    print(f"\n  Screenshot saved: test_optixeq.png")

    # ==========================================================================
    # Step 5: Date Guard
    # ==========================================================================

    section("Step 5: Date Guard Test")

    json_path = os.path.join(WEB_DIR, "data", "scratches.json")
    yest_payload = {
        "track": TRACK,
        "date":  YESTERDAY,
        "generated_at": "08:00 AM ET",
        "scratches": [
            {"race": 1, "pgm": "3", "horse": "Fast Eddie",
             "change_type": "Scratched", "reason": "PrivVet-Illness",
             "time_posted": "08:15 AM ET", "time_posted_dt": "08:15"}
        ],
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(yest_payload, f, indent=2)
    print(f"  Wrote scratches.json with date={YESTERDAY!r}")

    driver.get(f"http://127.0.0.1:{PORT}/index.html")
    time.sleep(4)  # full load cycle

    banner_el2   = driver.find_element(By.ID, "scratch-banner")
    banner_html2 = banner_el2.get_attribute("innerHTML").strip()
    print(f"  Banner innerHTML length: {len(banner_html2)}")

    if len(banner_html2) < 10:
        ok("date_guard", f"Date guard working — banner empty for date={YESTERDAY!r}")
    else:
        fail("date_guard",
             f"Date guard FAILED — banner shows for yesterday: {banner_html2[:200]!r}")

    # Restore today's JSON
    export_scratches_to_json(TRACK, TODAY)
    print(f"  Restored today's scratches.json (date={TODAY!r})")

finally:
    driver.quit()
    server.shutdown()


# =============================================================================
# Step 6: Cleanup
# =============================================================================

section("Step 6: Cleanup")

conn = sqlite3.connect(DB_PATH)
cur = conn.execute(
    "DELETE FROM scratch_alerts WHERE horse_name IN ('Fast Eddie','Lucky Star','Derby Dream')"
    " AND track=? AND date=?",
    (TRACK, TODAY),
)
deleted = cur.rowcount
conn.commit()
conn.close()

print(f"  Deleted {deleted} test row(s) from scratch_alerts")
if deleted == 3:
    ok("cleanup", "All 3 test rows removed from DB")
else:
    fail("cleanup", f"Expected to delete 3 rows, deleted {deleted}")


# =============================================================================
# Summary
# =============================================================================

section("SUMMARY")

col_w = max(len(k) for k in results)
print(f"\n  {'Test':<{col_w}}   Result")
print(f"  {'-' * col_w}   ------")
for k, v in results.items():
    badge = "[PASS]" if v == "PASS" else "[FAIL]"
    print(f"  {k:<{col_w}}   {badge}")

n_pass = sum(1 for v in results.values() if v == "PASS")
n_fail = sum(1 for v in results.values() if v != "PASS")
total  = len(results)
print(f"\n  {n_pass}/{total} passed", end="")
if n_fail:
    print(f"  ({n_fail} FAILED)")
    sys.exit(1)
else:
    print("  -- all green")
