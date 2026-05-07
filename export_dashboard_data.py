"""
Export dashboard data from horse_racing.db to web/dashboard_data.json.

Run this after every scrape session, then push web/ to GitHub.
The web app fetches dashboard_data.json on load and renders it live.

Usage:
    python export_dashboard_data.py
    python export_dashboard_data.py CD          # include only CD
    python export_dashboard_data.py CD KEE GP   # include listed tracks
"""

import sqlite3
import json
import os
import sys
from datetime import datetime

DB_PATH  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "horse_racing.db")
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "dashboard_data.json")


# ── Helpers (mirrors derby_value.py logic) ────────────────────────────────────

def _consistency(value_score):
    if value_score is None:
        return "N/A"
    if value_score < 3.0:
        return "HIGH"
    if value_score <= 10.0:
        return "MODERATE"
    return "LOTTERY"


def _score_sequences(conn, track, wager_type, min_hits=5):
    c = conn.cursor()
    c.execute(
        "SELECT race_span, COALESCE(payout_per_2, payout) FROM exotic_payouts "
        "WHERE track=? AND wager_type=? ORDER BY race_date",
        (track, wager_type)
    )
    raw = c.fetchall()
    if not raw:
        return []

    spans = {}
    for span, payout in raw:
        spans.setdefault(span, []).append(payout)

    results = []
    for span, payouts in spans.items():
        ps = sorted(payouts)
        n  = len(ps)
        avg = sum(ps) / n
        mid = n // 2
        median = ps[mid] if n % 2 == 1 else (ps[mid - 1] + ps[mid]) / 2
        vs = round(avg / median, 3) if median else None
        results.append({
            "race_span":     span,
            "times_hit":     n,
            "avg_payout":    round(avg, 2),
            "median_payout": round(median, 2),
            "value_score":   vs,
            "thin_sample":   n < min_hits,
        })

    results.sort(key=lambda x: x["avg_payout"], reverse=True)
    return results


def _find_overlays(conn, track, wager_type, min_hits=5):
    seqs = _score_sequences(conn, track, wager_type, min_hits)
    if not seqs:
        return []

    qualified = [s for s in seqs if not s["thin_sample"]]
    if not qualified:
        return []

    overall_avg = sum(s["avg_payout"] for s in qualified) / len(qualified)
    threshold   = overall_avg * 1.5

    overlays = []
    for s in qualified:
        if s["avg_payout"] > threshold:
            overlays.append({
                "race_span":     s["race_span"],
                "times_hit":     s["times_hit"],
                "avg_payout":    s["avg_payout"],
                "median_payout": s["median_payout"],
                "value_score":   s["value_score"],
                "overlay_ratio": round(s["avg_payout"] / overall_avg, 2),
                "consistency":   _consistency(s["value_score"]),
            })

    return overlays


def _pool_sequences(seqs_by_span, min_hits_for_pool=10):
    """
    Given the dict from _all_sequences_with_flags (keyed by race_span),
    return a pooled aggregate with original per-span data nested under by_position.

    Qualifying sequences: thin_sample=False AND times_hit >= min_hits_for_pool.
    Pooled stats use weighted averages (weighted by times_hit).
    """
    if not seqs_by_span:
        return {}

    qualifying = {
        span: data for span, data in seqs_by_span.items()
        if not data.get("thin_sample", True) and data.get("times_hit", 0) >= min_hits_for_pool
    }
    n_excluded = len(seqs_by_span) - len(qualifying)

    wager_base = next(iter(seqs_by_span.values()), {}).get("wager_base")

    if not qualifying:
        return {
            "avg_payout":              None,
            "median_payout":           None,
            "total_hits":              0,
            "overlay_ratio":           None,
            "wager_base":              wager_base,
            "sample_sequences":        0,
            "thin_sequences_excluded": n_excluded,
            "by_position":             seqs_by_span,
        }

    total_hits = sum(d["times_hit"] for d in qualifying.values())

    weighted_avg = sum(d["avg_payout"] * d["times_hit"] for d in qualifying.values()) / total_hits

    # Median of medians (simple — sorted middle value)
    medians = sorted(d["median_payout"] for d in qualifying.values())
    nm = len(medians)
    mid = nm // 2
    median_of_medians = medians[mid] if nm % 2 == 1 else (medians[mid - 1] + medians[mid]) / 2

    # Weighted overlay_ratio (skip None entries)
    overlay_pairs = [
        (d["overlay_ratio"] * d["times_hit"], d["times_hit"])
        for d in qualifying.values()
        if d.get("overlay_ratio") is not None
    ]
    if overlay_pairs:
        w_ov = sum(v for v, _ in overlay_pairs) / sum(w for _, w in overlay_pairs)
    else:
        w_ov = None

    return {
        "avg_payout":              round(weighted_avg, 2),
        "median_payout":           round(median_of_medians, 2),
        "total_hits":              total_hits,
        "overlay_ratio":           round(w_ov, 3) if w_ov is not None else None,
        "wager_base":              wager_base,
        "sample_sequences":        len(qualifying),
        "thin_sequences_excluded": n_excluded,
        "by_position":             seqs_by_span,
    }


def _all_sequences_with_flags(conn, track, wager_type, min_hits=10):
    """Return ALL race spans as a dict keyed by race_span, with overlay flags."""
    c = conn.cursor()
    c.execute(
        "SELECT race_span, COALESCE(payout_per_2, payout), COALESCE(wager_base, 2.0) "
        "FROM exotic_payouts WHERE track=? AND wager_type=? ORDER BY race_date",
        (track, wager_type)
    )
    raw = c.fetchall()
    if not raw:
        return {}

    wager_base_used = raw[0][2]
    spans = {}
    for span, payout, _ in raw:
        spans.setdefault(span, []).append(payout)

    results = []
    for span, payouts in spans.items():
        ps  = sorted(payouts)
        n   = len(ps)
        avg = sum(ps) / n
        mid = n // 2
        med = ps[mid] if n % 2 == 1 else (ps[mid - 1] + ps[mid]) / 2
        vs  = round(avg / med, 3) if med else None
        results.append({
            "race_span":     span,
            "times_hit":     n,
            "avg_payout":    round(avg, 2),
            "median_payout": round(med, 2),
            "max_payout":    round(max(ps), 2),
            "value_score":   vs,
            "thin_sample":   n < min_hits,
        })

    qualified   = [s for s in results if not s["thin_sample"]]
    overall_avg = sum(s["avg_payout"] for s in qualified) / len(qualified) if qualified else 0
    threshold   = overall_avg * 1.5

    output = {}
    for s in results:
        is_overlay = (
            not s["thin_sample"] and overall_avg > 0 and s["avg_payout"] > threshold
        )
        output[s["race_span"]] = {
            "times_hit":     s["times_hit"],
            "avg_payout":    s["avg_payout"],
            "median_payout": s["median_payout"],
            "max_payout":    s["max_payout"],
            "wager_base":    wager_base_used,
            "is_overlay":    is_overlay,
            "overlay_ratio": round(s["avg_payout"] / overall_avg, 2) if overall_avg else None,
            "consistency":   _consistency(s["value_score"]),
            "thin_sample":   s["thin_sample"],
        }
    return output


# ── Will-Pay Multipliers ──────────────────────────────────────────────────────

def _willpay_multipliers(conn, track):
    """Compute P3->P4, P3->P5, P4->P5 multipliers for overlapping span endings."""
    c = conn.cursor()
    c.execute(
        "SELECT race_date, wager_type, race_span, COALESCE(payout_per_2, payout) "
        "FROM exotic_payouts "
        "WHERE track=? AND wager_type IN ('P3','P4','P5') ORDER BY race_date",
        (track,)
    )
    rows = c.fetchall()
    if not rows:
        return {}

    grouped = {}
    for race_date, wager_type, race_span, payout in rows:
        parts = race_span.split('-')
        if len(parts) >= 2:
            try:
                end = int(parts[-1])
                key = (race_date, wager_type, end)
                grouped.setdefault(key, []).append(payout)
            except ValueError:
                pass

    p3_to_p4, p3_to_p5, p4_to_p5 = [], [], []
    date_ends = set((d, e) for (d, w, e) in grouped)
    for (date, end) in date_ends:
        p3s = grouped.get((date, 'P3', end), [])
        p4s = grouped.get((date, 'P4', end), [])
        p5s = grouped.get((date, 'P5', end), [])
        for a in p3s:
            for b in p4s:
                if a > 0:
                    p3_to_p4.append(b / a)
        for a in p3s:
            for b in p5s:
                if a > 0:
                    p3_to_p5.append(b / a)
        for a in p4s:
            for b in p5s:
                if a > 0:
                    p4_to_p5.append(b / a)

    def _stats(ratios):
        if not ratios:
            return None
        n = len(ratios)
        s = sorted(ratios)
        mean = sum(s) / n
        mid  = n // 2
        median = s[mid] if n % 2 == 1 else (s[mid - 1] + s[mid]) / 2
        return {
            "mean":       round(mean, 3),
            "median":     round(median, 3),
            "min":        round(min(s), 3),
            "max":        round(max(s), 3),
            "sample":     n,
            "confidence": "HIGH" if n >= 5 else "LOW",
        }

    result = {}
    for key, ratios in [("p3_to_p4", p3_to_p4), ("p3_to_p5", p3_to_p5), ("p4_to_p5", p4_to_p5)]:
        stats = _stats(ratios)
        if stats:
            result[key] = stats
    return result


# ── Parlay vs Exotic ──────────────────────────────────────────────────────────

def _parlay_vs_exotic(conn, track):
    """
    Mirror of derby_value.parlay_vs_exotic() using an existing connection.
    Returns summary dict keyed by wager type ('P4','P5','P6').
    """
    c = conn.cursor()
    c.execute(
        "SELECT race_date, race_num, win_payout, field_size FROM race_results "
        "WHERE track=? AND win_payout IS NOT NULL AND win_payout > 0 "
        "ORDER BY race_date, race_num",
        (track,)
    )
    race_rows = c.fetchall()

    c.execute(
        "SELECT race_date, wager_type, race_span, payout, "
        "COALESCE(payout_per_2, payout) AS payout_p2, "
        "COALESCE(wager_base, 2.0) AS wager_base "
        "FROM exotic_payouts "
        "WHERE track=? AND wager_type IN ('P4','P5','P6')",
        (track,)
    )
    exotic_rows = c.fetchall()

    by_date = {}
    for race_date, race_num, win_payout, field_size in race_rows:
        by_date.setdefault(race_date, []).append((race_num, win_payout, field_size))

    exotic_idx = {}
    for race_date, wager_type, race_span, payout, payout_p2, wager_base in exotic_rows:
        exotic_idx[(race_date, wager_type, race_span)] = {
            'raw': payout, 'p2': payout_p2, 'base': wager_base
        }

    wager_map = {4: 'P4', 5: 'P5', 6: 'P6'}
    matched = {'P4': [], 'P5': [], 'P6': []}

    for race_date, races in sorted(by_date.items()):
        for N, wager_type in wager_map.items():
            if len(races) < N:
                continue
            last_n     = races[-N:]
            span       = '-'.join(str(r[0]) for r in last_n)
            einfo      = exotic_idx.get((race_date, wager_type, span))
            if einfo is None:
                continue
            exotic_raw  = float(einfo['raw'])
            exotic_p2   = float(einfo['p2'])
            wager_base  = einfo['base']
            leg_payouts = [float(r[1]) for r in last_n]
            leg_fields  = [r[2] for r in last_n if r[2]]
            parlay = 2.0
            for p in leg_payouts:
                parlay *= p / 2.0
            parlay = round(parlay, 2)
            ratio  = round(exotic_p2 / parlay, 3) if parlay > 0 else None
            matched[wager_type].append({
                'date':       race_date,
                'span':       span,
                'parlay':     parlay,
                'exotic':     round(exotic_raw, 2),
                'exotic_p2':  round(exotic_p2, 2),
                'wager_base': wager_base,
                'ratio':      ratio,
                'max_leg':    round(max(leg_payouts), 2),
                'avg_field':  round(sum(leg_fields) / len(leg_fields), 1) if leg_fields else None,
            })

    _THRESH = [6, 8, 10, 12, 15, 20, 25, 30, 40, 50]

    summary = {}
    for wager_type, days in matched.items():
        if not days:
            continue
        ratios = [d['ratio'] for d in days if d['ratio'] is not None]
        if not ratios:
            continue
        n  = len(ratios)
        rs = sorted(ratios)
        mid = n // 2
        median_r = rs[mid] if n % 2 == 1 else (rs[mid - 1] + rs[mid]) / 2
        edges = [d['exotic_p2'] - d['parlay'] for d in days]
        exotic_won = sum(1 for r in ratios if r > 1.0)

        thresh_analysis = []
        for t in _THRESH:
            sub = [d for d in days if (d.get('max_leg') or 0) >= t]
            if len(sub) < 2:
                continue
            rs_sub = [d['ratio'] for d in sub if d['ratio'] is not None]
            if not rs_sub:
                continue
            ew = sum(1 for r in rs_sub if r > 1.0)
            thresh_analysis.append({
                'min_leg':        t,
                'sample':         len(sub),
                'exotic_win_pct': round(ew / len(sub) * 100, 1),
                'avg_ratio':      round(sum(rs_sub) / len(rs_sub), 3),
            })

        # Group days by span for by_position breakdown
        by_position = {}
        for d in days:
            by_position.setdefault(d['span'], []).append(d)
        pos_summary = {}
        for span, span_days in by_position.items():
            sp_ratios = [sd['ratio'] for sd in span_days if sd['ratio'] is not None]
            if not sp_ratios:
                continue
            sn = len(sp_ratios)
            sp_rs = sorted(sp_ratios)
            sp_mid = sn // 2
            sp_med = sp_rs[sp_mid] if sn % 2 == 1 else (sp_rs[sp_mid - 1] + sp_rs[sp_mid]) / 2
            sp_ew = sum(1 for r in sp_ratios if r > 1.0)
            pos_summary[span] = {
                'sample':                 sn,
                'mean_ratio':             round(sum(sp_ratios) / sn, 3),
                'median_ratio':           round(sp_med, 3),
                'exotic_beat_parlay_pct': round(sp_ew / sn * 100, 1),
                'days':                   sorted(span_days, key=lambda d: -(d['ratio'] or 0)),
            }

        summary[wager_type] = {
            'sample':                 n,
            'mean_ratio':             round(sum(ratios) / n, 3),
            'median_ratio':           round(median_r, 3),
            'exotic_beat_parlay_pct': round(exotic_won / n * 100, 1),
            'avg_edge':               round(sum(edges) / n, 2),
            'threshold_analysis':     thresh_analysis,
            'days':                   sorted(days, key=lambda d: -(d['ratio'] or 0)),
            'by_position':            pos_summary,
        }
    return summary


# ── Today's Entries + AE Alerts ──────────────────────────────────────────────

def _ae_premium_note(conn, track, listed_field_size):
    """
    Compute historical AE payout premium from race_results.
    Looks at races where winner_pgm > field_size (AE drew in and won).
    Returns a plain-English note string.
    """
    c = conn.cursor()
    fs = listed_field_size or 10
    c.execute("""
        SELECT
            AVG(CASE WHEN CAST(winner_pgm AS INT) > field_size THEN win_payout END) AS ae_avg,
            AVG(CASE WHEN CAST(winner_pgm AS INT) <= field_size THEN win_payout END) AS field_avg,
            SUM(CASE WHEN CAST(winner_pgm AS INT) > field_size THEN 1 ELSE 0 END) AS ae_wins
        FROM race_results
        WHERE track = ?
          AND field_size BETWEEN ? AND ?
          AND win_payout IS NOT NULL AND win_payout > 0
    """, (track, max(8, fs - 2), fs + 2))
    row = c.fetchone()
    if row and row[0] is not None and row[1] and row[1] > 0:
        premium  = round(row[0] / row[1], 1)
        ae_wins  = int(row[2])
        return (f"AE entry — drew in via scratch. "
                f"Historical AE payout premium at {track}: {premium}x field average "
                f"({ae_wins} AE win(s) in dataset).")
    return f"AE entry — drew in via scratch. No AE win history at {track} for this field size."


def _build_today_entries(conn):
    """
    Build the today_entries section for dashboard_data.json.
    Reads from the entries + entry_horses tables for today's date.
    Returns {} if the tables don't exist or no entries were scraped today.

    Output shape:
        {
            "CD": {
                "date": "2026-05-03",
                "races": [ { race_num, race_type, distance, surface,
                              field_size, horses, ae_horses } ],
                "ae_alerts": [ { race_num, program_num, horse_name,
                                  morning_line, note } ]
            }
        }
    """
    from datetime import timedelta
    today    = datetime.now().strftime('%Y-%m-%d')
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    c        = conn.cursor()

    # Tables may not exist on first run
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='entries'")
    if not c.fetchone():
        return {}

    # Include today's AND tomorrow's entries so pre-race-day morning lines appear
    c.execute(
        "SELECT DISTINCT track, race_date FROM entries "
        "WHERE race_date IN (?, ?) ORDER BY race_date, track",
        (today, tomorrow)
    )
    rows = c.fetchall()
    if not rows:
        return {}
    # For each track keep the earliest date (prefer today over tomorrow)
    track_date = {}
    for track, race_date in rows:
        if track not in track_date:
            track_date[track] = race_date
    tracks = list(track_date.keys())

    result = {}
    for track in tracks:
        race_date = track_date[track]
        c.execute(
            "SELECT race_num, race_type, distance, surface, listed_field_size "
            "FROM entries WHERE track=? AND race_date=? ORDER BY race_num",
            (track, race_date)
        )
        races_meta = c.fetchall()

        races      = []
        ae_alerts  = []

        # Load scratch_alerts for this track/date to catch runtime scratches
        # that arrived after the initial scrape (Equibase late changes)
        scratch_set = set()
        try:
            sa_rows = c.execute(
                "SELECT race_num, pgm FROM scratch_alerts "
                "WHERE track=? AND date=? AND change_type='Scratched'",
                (track, race_date)
            ).fetchall()
            scratch_set = {(r[0], r[1]) for r in sa_rows}
        except Exception:
            pass

        for race_num, race_type, distance, surface, listed_field_size in races_meta:
            c.execute(
                "SELECT program_num, horse_name, morning_line_odds, jockey, trainer, is_ae, "
                "COALESCE(scratched, 0) "
                "FROM entry_horses "
                "WHERE track=? AND race_date=? AND race_num=? ORDER BY rowid",
                (track, race_date, race_num)
            )
            horse_rows = c.fetchall()

            horses    = []
            ae_horses = []
            for pgm, name, ml, jockey, trainer, is_ae, scratched in horse_rows:
                is_scratched = bool(scratched) or (race_num, pgm) in scratch_set
                h = {
                    'program_num':  pgm,
                    'horse_name':   name or '',
                    'morning_line': ml,
                    'jockey':       jockey or '',
                    'trainer':      trainer or '',
                    'is_ae':        bool(is_ae),
                    'scratched':    is_scratched,
                }
                horses.append(h)
                if is_ae:
                    ae_horses.append(h)

            races.append({
                'race_num':   race_num,
                'race_type':  race_type or '',
                'distance':   distance  or '',
                'surface':    surface   or '',
                'field_size': listed_field_size or 0,
                'horses':     horses,
                'ae_horses':  [h['program_num'] for h in ae_horses],
            })

            for h in ae_horses:
                note = _ae_premium_note(conn, track, listed_field_size)
                ae_alerts.append({
                    'race_num':    race_num,
                    'program_num': h['program_num'],
                    'horse_name':  h['horse_name'],
                    'morning_line': h['morning_line'],
                    'note':        note,
                })

        result[track] = {
            'date':       race_date,
            'races':      races,
            'ae_alerts':  ae_alerts,
        }

    return result


# ── Recent Results ───────────────────────────────────────────────────────────

def _recent_results(conn):
    """
    For each track return the most recent race day's win/place/show results
    and exotic payouts for that same date.
    """
    c = conn.cursor()
    c.execute(
        "SELECT track, MAX(race_date) FROM race_results GROUP BY track ORDER BY track"
    )
    track_dates = c.fetchall()

    result = []
    for track, latest_date in track_dates:
        # Win/place/show results
        c.execute(
            "SELECT race_num, winner, winner_pgm, win_payout, place_payout, show_payout "
            "FROM race_results WHERE track=? AND race_date=? ORDER BY race_num",
            (track, latest_date)
        )
        races = []
        for row in c.fetchall():
            races.append({
                "race_num":     row[0],
                "winner":       row[1] or "",
                "winner_pgm":   row[2] or "",
                "win_payout":   row[3],
                "place_payout": row[4],
                "show_payout":  row[5],
            })

        # Exotic payouts — store both payout_per_2 (may be null) and raw payout
        c.execute(
            "SELECT wager_type, race_span, winning_combo, payout_per_2, payout "
            "FROM exotic_payouts WHERE track=? AND race_date=? "
            "ORDER BY wager_type, race_span",
            (track, latest_date)
        )
        exotics = []
        for row in c.fetchall():
            exotics.append({
                "wager_type":    row[0],
                "race_span":     row[1],
                "winning_combo": row[2] or "",
                "payout_per_2":  row[3],
                "payout":        round(float(row[4]), 2) if row[4] is not None else None,
            })

        result.append({
            "track":        track,
            "date":         latest_date,
            "race_count":   len(races),
            "exotic_count": len(exotics),
            "races":        races,
            "exotics":      exotics,
        })

    return result


# ── Main export ───────────────────────────────────────────────────────────────

def export(track_filter=None):
    if not os.path.exists(DB_PATH):
        print(f"ERROR: horse_racing.db not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    # ── DB summary ──
    c.execute("SELECT COUNT(DISTINCT track) FROM race_results")
    total_tracks = c.fetchone()[0]

    c.execute("SELECT COUNT(DISTINCT race_date) FROM race_results")
    total_race_days = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM race_results")
    total_races = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM exotic_payouts")
    total_exotics = c.fetchone()[0]

    c.execute("SELECT MIN(race_date), MAX(race_date) FROM race_results")
    date_min, date_max = c.fetchone()

    c.execute(
        "SELECT track, COUNT(DISTINCT race_date), COUNT(*) "
        "FROM race_results GROUP BY track ORDER BY track"
    )
    track_rows = c.fetchall()

    c.execute(
        "SELECT track, COUNT(*) FROM exotic_payouts GROUP BY track ORDER BY track"
    )
    exotic_counts = dict(c.fetchall())

    c.execute("SELECT track, MAX(race_num) FROM race_results GROUP BY track")
    max_races = dict(c.fetchall())

    tracks_detail = [
        {
            "track":    row[0],
            "days":     row[1],
            "races":    row[2],
            "exotics":  exotic_counts.get(row[0], 0),
            "max_race": max_races.get(row[0], 9),
        }
        for row in track_rows
    ]

    db_summary = {
        "total_tracks":    total_tracks,
        "total_race_days": total_race_days,
        "total_races":     total_races,
        "total_exotics":   total_exotics,
        "date_range":      {"from": date_min or "", "to": date_max or ""},
        "tracks":          tracks_detail,
    }

    # ── Overlays per track ──
    all_tracks = [row[0] for row in track_rows]
    if track_filter:
        all_tracks = [t for t in all_tracks if t in track_filter]

    overlays  = {}
    sequences = {}
    for track in all_tracks:
        track_overlays = {}
        track_seqs     = {}
        for wager in ("DD", "P3", "P4", "P5", "P6"):
            ovl  = _find_overlays(conn, track, wager)
            if ovl:
                track_overlays[wager] = ovl
            seqs = _all_sequences_with_flags(conn, track, wager)
            if seqs:
                track_seqs[wager] = _pool_sequences(seqs)
        overlays[track]  = track_overlays
        sequences[track] = track_seqs
        hits  = sum(len(v) for v in track_overlays.values())
        spans = sum(
            len(v["by_position"]) for v in track_seqs.values() if isinstance(v, dict) and "by_position" in v
        )
        print(f"  {track}: {hits} overlay(s), {spans} total sequence span(s)")

    # ── Will-Pay Multipliers (all tracks, unfiltered) ──
    c.execute("SELECT DISTINCT track FROM exotic_payouts ORDER BY track")
    all_tracks_full = [r[0] for r in c.fetchall()]
    willpay = {}
    for track in all_tracks_full:
        wm = _willpay_multipliers(conn, track)
        if wm:
            willpay[track] = wm

    # ── Parlay vs Exotic (all tracks, unfiltered) ──
    parlay_exotic = {}
    for track in all_tracks_full:
        pe = _parlay_vs_exotic(conn, track)
        if pe:
            parlay_exotic[track] = pe
            for wt, s in pe.items():
                print(f"  {track} {wt}: {s['sample']} parlay/exotic pair(s) matched")

    # ── Today's entries + AE alerts ──
    today_entries = _build_today_entries(conn)

    # ── Recent results per track ──
    recent_results = _recent_results(conn)

    conn.close()
    ae_total = sum(len(td['ae_alerts']) for td in today_entries.values())
    if today_entries:
        print(f"  Today's entries: {sum(len(td['races']) for td in today_entries.values())} race(s) "
              f"across {len(today_entries)} track(s)  |  {ae_total} AE alert(s)")
    else:
        print("  Today's entries: none scraped yet (run scrape_entries.py first)")

    payload = {
        "last_updated":        datetime.now().strftime("%Y-%m-%d %H:%M"),
        "db_summary":          db_summary,
        "recent_results":      recent_results,
        "overlays":            overlays,
        "sequences":           sequences,
        "willpay_multipliers": willpay,
        "parlay_vs_exotic":    parlay_exotic,
        "today_entries":       today_entries,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    total_spans = sum(
        len(v["by_position"]) for t in sequences.values() for v in t.values()
        if isinstance(v, dict) and "by_position" in v
    )
    print(f"\nWrote {OUT_PATH}")
    print(f"  Tracks: {len(overlays)}  |  Races: {total_races}  |  "
          f"Exotics: {total_exotics}  |  Days: {total_race_days}  |  Sequences: {total_spans}")
    print(f"  Date range: {date_min} to {date_max}")
    print()
    print("Next steps:")
    print("  cd web")
    print('  git add dashboard_data.json')
    print('  git commit -m "update dashboard data"')
    print("  git push")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args:
        track_filter = [a.upper() for a in args]
        print(f"Exporting overlay data for: {', '.join(track_filter)}")
    else:
        track_filter = None
        print("Exporting overlay data for all tracks...")

    export(track_filter)
