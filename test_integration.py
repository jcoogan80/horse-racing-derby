"""
Integration test for ScratchWatcher.
Tests detect_new_scratches deduplication, add_ae_manual, and DB state.
Does NOT launch the GUI — tests the underlying functions directly.
"""

import sqlite3
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ScratchWatcher import detect_new_scratches, add_ae_manual, DB_PATH

TRACK = "CD"
DATE  = "2026-04-29"
SEP   = "-" * 55

# Pre-clean any leftover test rows from previous interrupted runs
_conn = sqlite3.connect(DB_PATH)
_conn.execute("DELETE FROM scratch_alerts WHERE horse_name='Integration Test Horse'")
_conn.commit()
_conn.close()

def section(title):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)

# ── Step 1: Live scrape ───────────────────────────────────────────────────────

section("Step 1: detect_new_scratches — first call (live scrape)")
results = detect_new_scratches(TRACK, DATE)

if results:
    print(f"  {len(results)} new change(s) returned:")
    for e in results:
        print(f"    R{e['race_num']:>2} #{e['pgm']:>3}  {e['horse_name']:<28}"
              f"  {e['change_type']:<12}  {e['reason']:<22}  @ {e['time_posted']}")
else:
    print("  (empty — all already in DB from prior run, dedup working)")

# ── Step 2: Deduplication check ───────────────────────────────────────────────

section("Step 2: detect_new_scratches — second call (dedup check)")
results2 = detect_new_scratches(TRACK, DATE)
print(f"  Returned: {results2}")
assert results2 == [], f"FAIL: expected empty list, got {results2}"
print("  PASS: empty list confirmed — no duplicates inserted")

# ── Step 3: Manual AE insertion ───────────────────────────────────────────────

section("Step 3: add_ae_manual")
inserted = add_ae_manual(TRACK, DATE, 7, "13", "Integration Test Horse")
print(f"  Returned: {inserted}")
assert inserted is True, f"FAIL: expected True, got {inserted}"
print("  PASS: manual AE inserted")

# ── Step 4: Full DB inspection ────────────────────────────────────────────────

section("Step 4: scratch_alerts table — all rows for CD 2026-04-29")

conn = sqlite3.connect(DB_PATH)
rows = conn.execute(
    """SELECT race_num, pgm, horse_name, change_type, reason, time_posted, detected_at
       FROM scratch_alerts
       WHERE track=? AND date=?
       ORDER BY race_num, pgm""",
    (TRACK, DATE)
).fetchall()
conn.close()

failures = []

print(f"  {'R#':>3}  {'Pgm':>4}  {'Horse':<30}  {'Type':<14}  {'Reason':<22}  {'Posted':<14}  Detected")
print(f"  {'--':>3}  {'---':>4}  {'-----':<30}  {'----':<14}  {'------':<22}  {'------':<14}  --------")
for row in rows:
    race_num, pgm, horse_name, change_type, reason, time_posted, detected_at = row

    # Print row
    print(f"  R{race_num:>2}  #{pgm:>3}  {horse_name:<30}  {(change_type or ''):.<14}  "
          f"{(reason or ''):.<22}  {(time_posted or ''):.<14}  {detected_at or ''}")

    # Validate no \xa0 artifacts in text fields
    for field_name, val in [("horse_name", horse_name), ("pgm", pgm),
                             ("reason", reason), ("time_posted", time_posted)]:
        if val and "\xa0" in val:
            failures.append(f"\\xa0 artifact in {field_name}: {repr(val)}")

    # detected_at must be present
    if not detected_at:
        failures.append(f"Missing detected_at for R{race_num} #{pgm} {horse_name}")

print(f"\n  Total rows: {len(rows)}")

# Spot-check the manual AE row
ae_rows = [r for r in rows if r[2] == "Integration Test Horse"]
assert len(ae_rows) == 1, f"FAIL: expected 1 AE row, found {len(ae_rows)}"
ae = ae_rows[0]
assert ae[3] == "AE_ADDED",     f"FAIL: change_type={ae[3]!r}, expected 'AE_ADDED'"
assert ae[4] == "Manual Entry", f"FAIL: reason={ae[4]!r}, expected 'Manual Entry'"
print("  PASS: manual AE row — change_type='AE_ADDED', reason='Manual Entry'")

if failures:
    for f in failures:
        print(f"  FAIL: {f}")
    sys.exit(1)
else:
    print("  PASS: no \\xa0 artifacts, all detected_at timestamps present")

# ── Step 5: Summary ───────────────────────────────────────────────────────────

section("Step 5: Summary")

conn = sqlite3.connect(DB_PATH)
detail = conn.execute(
    "SELECT change_type, reason FROM scratch_alerts WHERE track=? AND date=?",
    (TRACK, DATE)
).fetchall()
conn.close()

n_scratched   = sum(1 for ct, _ in detail if ct == "Scratched")
n_ae_removed  = sum(1 for ct, r in detail if ct == "Scratched" and r == "Also-Eligible")
n_ae_added    = sum(1 for ct, _ in detail if ct == "AE_ADDED")
n_other_chg   = sum(1 for ct, _ in detail if ct not in ("Scratched", "AE_ADDED"))
total         = len(detail)

print(f"  Total rows in scratch_alerts (CD 2026-04-29): {total}")
print(f"    Scratched (all reasons):  {n_scratched}")
print(f"      of which Also-Eligible: {n_ae_removed}")
print(f"    AE_ADDED (manual):        {n_ae_added}")
print(f"    Other changes:            {n_other_chg}")
print()
print(f"  [PASS] Integration test passed -- "
      f"{n_scratched} scratches, {n_ae_removed} AE removals, {n_ae_added} manual AE entries")

# ── Cleanup ───────────────────────────────────────────────────────────────────

conn = sqlite3.connect(DB_PATH)
conn.execute("DELETE FROM scratch_alerts WHERE horse_name='Integration Test Horse'")
conn.commit()
conn.close()
print("  (Integration Test Horse row cleaned up)")
