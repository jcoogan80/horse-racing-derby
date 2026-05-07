"""
Phase 2: Value Detection Engine
Reads from horse_racing.db and identifies high-value exotic wager sequences.

Usage:
    python derby_value.py              # full report for all tracks
    python derby_value.py AQU          # full report for one track
    python derby_value.py profile KEE  # consolidated profile for one track
"""

import sqlite3
import sys
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "horse_racing.db")


def _load_exotics(track=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if track:
        c.execute(
            "SELECT * FROM exotic_payouts WHERE track=? ORDER BY race_date, race_num",
            (track,)
        )
    else:
        c.execute("SELECT * FROM exotic_payouts ORDER BY track, race_date, race_num")
    rows = c.fetchall()
    conn.close()
    return rows


def _consistency(value_score):
    """Classify a value_score into a human-readable consistency rating."""
    if value_score is None:
        return "N/A"
    if value_score < 3.0:
        return "HIGH"
    if value_score <= 10.0:
        return "MODERATE"
    return "LOTTERY"


def score_sequences(track, wager_type, min_hits=5):
    """
    For a given track and wager type (DD, P3, P4, P5, P6), return a list of
    dicts representing every race_span ranked by avg_payout descending.

    Each dict contains:
        race_span      – e.g. "3-5" or "1-3"
        times_hit      – how many times this span paid out in the data
        avg_payout     – mean payout across all hits
        median_payout  – median payout
        max_payout     – single highest payout seen
        value_score    – avg_payout / median_payout
                         ~1 = consistent payouts, >1 = outlier-driven average
        thin_sample    – True if times_hit < min_hits
    """
    rows = [r for r in _load_exotics(track) if r["wager_type"] == wager_type]
    if not rows:
        return []

    # Deduplicate by (race_date, race_span): keep MAX payout_per_2 per day.
    # Multiple rows for the same span on the same day represent dead heats or
    # coupled entries — taking the max gives the most favorable single outcome.
    seen: dict = {}
    for r in rows:
        p = r["payout_per_2"] if r["payout_per_2"] is not None else r["payout"]
        key = (r["race_date"], r["race_span"])
        if key not in seen or p > seen[key]:
            seen[key] = p
    spans: dict = {}
    for (_, race_span), p in seen.items():
        spans.setdefault(race_span, []).append(p)

    results = []
    for span, payouts in spans.items():
        payouts_sorted = sorted(payouts)
        n = len(payouts_sorted)
        avg = sum(payouts_sorted) / n
        mid = n // 2
        median = (
            payouts_sorted[mid]
            if n % 2 == 1
            else (payouts_sorted[mid - 1] + payouts_sorted[mid]) / 2
        )
        vs = round(avg / median, 3) if median else None
        results.append({
            "race_span":     span,
            "times_hit":     n,
            "avg_payout":    round(avg, 2),
            "median_payout": round(median, 2),
            "max_payout":    round(max(payouts_sorted), 2),
            "value_score":   vs,
            "thin_sample":   n < min_hits,
        })

    results.sort(key=lambda x: x["avg_payout"], reverse=True)
    return results


def find_overlays(track, wager_type, min_hits=5):
    """
    Return sequences where avg_payout > 1.5x the overall average for that
    wager type at that track, restricted to spans with >= min_hits observations.
    Thin-sample spans are returned separately for transparency.

    Returns (overlays, thin_samples) — both lists of dicts.
    """
    sequences = score_sequences(track, wager_type, min_hits=min_hits)
    if not sequences:
        return [], []

    qualified = [s for s in sequences if not s["thin_sample"]]
    thin      = [s for s in sequences if s["thin_sample"]]

    if not qualified:
        return [], thin

    overall_avg = sum(s["avg_payout"] for s in qualified) / len(qualified)
    threshold   = overall_avg * 1.5

    overlays = []
    for s in qualified:
        if s["avg_payout"] > threshold:
            overlays.append({**s, "overlay_ratio": round(s["avg_payout"] / overall_avg, 2)})

    return overlays, thin


def profile_track(track, min_hits=5):
    """
    Consolidated single-page profile for a track across all wager types.
    Shows the top 3 overlay sequences per wager type with sample size,
    value_score, and consistency rating.
    """
    width = 68
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    print()
    print("=" * width)
    print(f"  TRACK PROFILE  |  {track}  |  generated {generated}")
    print("=" * width)
    print(f"  Min hits threshold: {min_hits}  (sequences below this flagged as thin sample)")

    any_data = False
    # SF (Superfecta) is a single-race wager, not a multi-race sequence —
    # excluded from overlay and parlay analyses throughout this file.
    for wager_type in ("DD", "P3", "P4", "P5", "P6"):
        overlays, thin = find_overlays(track, wager_type, min_hits=min_hits)
        sequences      = score_sequences(track, wager_type, min_hits=min_hits)
        if not sequences:
            continue
        any_data = True

        qualified = [s for s in sequences if not s["thin_sample"]]
        overall_avg = (
            sum(s["avg_payout"] for s in qualified) / len(qualified)
            if qualified else 0
        )

        print()
        print(f"  {'-' * (width - 2)}")
        print(
            f"  {wager_type}  |  {len(sequences)} span(s) total  |  "
            f"{len(qualified)} qualified (>={min_hits} hits)  |  "
            f"overall avg: ${overall_avg:.2f}"
        )
        print(f"  {'-' * (width - 2)}")

        if not overlays:
            print("  No overlay sequences above threshold.")
        else:
            top3 = overlays[:3]
            print(
                f"  {'Races':<10} {'Hits':>5} {'Avg $':>9} {'Median $':>10} "
                f"{'Ratio':>7} {'V.Score':>9} {'Consistency':<14}"
            )
            print(f"  {'-' * (width - 2)}")
            for o in top3:
                consistency = _consistency(o["value_score"])
                vs = f"{o['value_score']:.2f}" if o["value_score"] is not None else " N/A"
                print(
                    f"  {o['race_span']:<10} {o['times_hit']:>5} "
                    f"{o['avg_payout']:>9.2f} {o['median_payout']:>10.2f} "
                    f"{o['overlay_ratio']:>6.2f}x {vs:>9} {consistency:<14}"
                )

        if thin:
            spans_str = ", ".join(
                f"{s['race_span']} ({s['times_hit']} hits)" for s in thin[:6]
            )
            suffix = f" +{len(thin)-6} more" if len(thin) > 6 else ""
            print(f"  [thin sample: {spans_str}{suffix}]")

    if not any_data:
        print(f"\n  No exotic payout data found for {track}.")
    print()


# ── Full report helpers ───────────────────────────────────────────────────────

def _print_sequences(sequences):
    if not sequences:
        print("    (no data)")
        return
    header = (
        f"  {'Races':<8} {'Hits':>5} {'Avg $':>8} {'Median $':>9} "
        f"{'Max $':>9} {'V.Score':>9} {'Sample':<10}"
    )
    print(header)
    print("  " + "-" * (len(header) - 2))
    for s in sequences:
        vs     = f"{s['value_score']:.3f}" if s["value_score"] is not None else "  N/A"
        sample = "thin" if s["thin_sample"] else "ok"
        print(
            f"  {s['race_span']:<8} {s['times_hit']:>5} "
            f"{s['avg_payout']:>8.2f} {s['median_payout']:>9.2f} "
            f"{s['max_payout']:>9.2f} {vs:>9} {sample:<10}"
        )


def _print_overlays(overlays, thin, overall_avg):
    if not overlays:
        print("    (none -- no qualified sequence exceeds 1.5x the average)")
    else:
        print(
            f"  Overall avg (qualified): ${overall_avg:.2f}  |  "
            f"Threshold: ${overall_avg * 1.5:.2f}"
        )
        print()
        for o in overlays:
            vs = f"{o['value_score']:.3f}" if o["value_score"] is not None else "N/A"
            consistency = _consistency(o["value_score"])
            print(
                f"  *** Races {o['race_span']:<6}  avg ${o['avg_payout']:.2f}  "
                f"({o['overlay_ratio']:.2f}x)  hits={o['times_hit']}  "
                f"median=${o['median_payout']:.2f}  "
                f"vscore={vs}  [{consistency}]"
            )
    if thin:
        spans_str = ", ".join(
            f"{s['race_span']}({s['times_hit']})" for s in thin[:8]
        )
        suffix = f" +{len(thin)-8} more" if len(thin) > 8 else ""
        print(f"  [thin sample excluded: {spans_str}{suffix}]")


def print_report(track, min_hits=5):
    width = 65
    print()
    print("=" * width)
    print(f"  VALUE DETECTION REPORT  |  Track: {track}")
    print("=" * width)

    for wager_type in ("P3", "P4", "P5", "P6"):
        sequences = score_sequences(track, wager_type, min_hits=min_hits)
        if not sequences:
            continue

        qualified   = [s for s in sequences if not s["thin_sample"]]
        overall_avg = (
            sum(s["avg_payout"] for s in qualified) / len(qualified)
            if qualified else 0
        )
        overlays, thin = find_overlays(track, wager_type, min_hits=min_hits)

        print()
        print(
            f"  {wager_type}  --  {len(sequences)} span(s)  |  "
            f"{len(qualified)} qualified  |  overall avg: ${overall_avg:.2f}"
        )
        print()
        print("  Ranked sequences (by avg payout):")
        _print_sequences(sequences)
        print()
        print("  Overlay targets (avg > 1.5x overall, min hits applied):")
        _print_overlays(overlays, thin, overall_avg)
        print()


# ── Will-Pay Multipliers ──────────────────────────────────────────────────────

def _parse_span_end(race_span):
    """Return the ending race number from a span string like '7-9', or None."""
    parts = race_span.split('-')
    if len(parts) >= 2:
        try:
            return int(parts[-1])
        except ValueError:
            return None
    return None


def willpay_multipliers(track):
    """
    Compute P3->P4, P3->P5, P4->P5 payout multipliers for overlapping spans
    that share the same ending race on the same race_date.

    Returns a dict with keys 'p3_to_p4', 'p3_to_p5', 'p4_to_p5', each being
    a stats dict (mean, median, min, max, sample, confidence) or None if no data.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT race_date, wager_type, race_span, "
        "COALESCE(payout_per_2, payout) AS payout FROM exotic_payouts "
        "WHERE track=? AND wager_type IN ('P3','P4','P5') ORDER BY race_date",
        (track,)
    )
    rows = c.fetchall()
    conn.close()

    # Deduplicate by (race_date, wager_type, race_span), keep MAX payout.
    deduped: dict = {}
    for r in rows:
        key = (r['race_date'], r['wager_type'], r['race_span'])
        if key not in deduped or r['payout'] > deduped[key]:
            deduped[key] = r['payout']

    # Group by (race_date, wager_type, ending_race_num)
    grouped: dict = {}
    for (race_date, wager_type, span), payout in deduped.items():
        end = _parse_span_end(span)
        if end is not None:
            grouped.setdefault((race_date, wager_type, end), []).append(payout)

    p3_to_p4_ratios, p3_to_p5_ratios, p4_to_p5_ratios = [], [], []

    date_ends = set((d, e) for (d, w, e) in grouped)
    for (date, end) in date_ends:
        p3s = grouped.get((date, 'P3', end), [])
        p4s = grouped.get((date, 'P4', end), [])
        p5s = grouped.get((date, 'P5', end), [])
        for a in p3s:
            for b in p4s:
                if a > 0:
                    p3_to_p4_ratios.append(b / a)
        for a in p3s:
            for b in p5s:
                if a > 0:
                    p3_to_p5_ratios.append(b / a)
        for a in p4s:
            for b in p5s:
                if a > 0:
                    p4_to_p5_ratios.append(b / a)

    def _stats(ratios):
        if not ratios:
            return None
        n = len(ratios)
        s = sorted(ratios)
        mean = sum(s) / n
        mid = n // 2
        median = s[mid] if n % 2 == 1 else (s[mid - 1] + s[mid]) / 2
        return {
            "mean":       round(mean, 3),
            "median":     round(median, 3),
            "min":        round(min(s), 3),
            "max":        round(max(s), 3),
            "sample":     n,
            "confidence": "HIGH" if n >= 5 else "LOW",
        }

    return {
        "p3_to_p4": _stats(p3_to_p4_ratios),
        "p3_to_p5": _stats(p3_to_p5_ratios),
        "p4_to_p5": _stats(p4_to_p5_ratios),
    }


def _print_willpay(track):
    result = willpay_multipliers(track)
    width  = 65
    print()
    print("=" * width)
    print(f"  WILL-PAY MULTIPLIERS  |  Track: {track}")
    print("=" * width)
    labels = [
        ("p3_to_p4", "P3 -> P4  (P4 payout / P3 payout, same ending race)"),
        ("p3_to_p5", "P3 -> P5  (P5 payout / P3 payout, same ending race)"),
        ("p4_to_p5", "P4 -> P5  (P5 payout / P4 payout, same ending race)"),
    ]
    any_data = False
    for key, label in labels:
        stats = result[key]
        print()
        print(f"  {label}")
        if stats is None:
            print("    No overlapping span data found.")
            continue
        any_data = True
        print(f"    Sample:     {stats['sample']}  [{stats['confidence']} confidence]")
        print(f"    Mean:       {stats['mean']:.3f}x")
        print(f"    Median:     {stats['median']:.3f}x")
        print(f"    Min:        {stats['min']:.3f}x")
        print(f"    Max:        {stats['max']:.3f}x")
    if not any_data:
        print(f"\n  No P3/P4/P5 overlap data found for {track}.")
    print()


# ── Parlay vs Exotic ──────────────────────────────────────────────────────────

def parlay_vs_exotic(track):
    """
    For each race day at track, compute a $2 parlay over the last 4, 5, and 6
    races using actual win payouts, then compare to the matching Pick 4/5/6
    exotic payout.  Both are on a $2 base.

    Parlay formula: $2 × ∏(win_payout_i / 2) for each leg i.

    Returns a dict keyed by wager type ('P4', 'P5', 'P6'), each containing
    summary stats and a 'days' list of per-day comparison records.
    Only days where all win payouts exist AND a matching exotic payout exists
    are included.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute(
        "SELECT race_date, race_num, win_payout, field_size FROM race_results "
        "WHERE track=? AND win_payout IS NOT NULL AND win_payout > 0 "
        "ORDER BY race_date, race_num",
        (track,)
    )
    race_rows = c.fetchall()

    # SF excluded: single-race wager, not comparable to multi-race Pick sequences.
    c.execute(
        "SELECT race_date, wager_type, race_span, payout, "
        "COALESCE(payout_per_2, payout) AS payout_p2, "
        "COALESCE(wager_base, 2.0) AS wager_base "
        "FROM exotic_payouts "
        "WHERE track=? AND wager_type IN ('P4','P5','P6')",
        (track,)
    )
    exotic_rows = c.fetchall()
    conn.close()

    by_date = {}
    for r in race_rows:
        by_date.setdefault(r['race_date'], []).append(r)

    # Deduplicate by (race_date, wager_type, race_span): keep MAX payout_p2.
    exotic_idx = {}
    for r in exotic_rows:
        key = (r['race_date'], r['wager_type'], r['race_span'])
        p2 = float(r['payout_p2'])
        if key not in exotic_idx or p2 > exotic_idx[key]['p2']:
            exotic_idx[key] = {'raw': r['payout'], 'p2': p2, 'base': r['wager_base']}

    wager_map = {4: 'P4', 5: 'P5', 6: 'P6'}
    matched = {'P4': [], 'P5': [], 'P6': []}

    for race_date, races in sorted(by_date.items()):
        for N, wager_type in wager_map.items():
            if len(races) < N:
                continue
            last_n     = races[-N:]
            span       = '-'.join(str(r['race_num']) for r in last_n)
            einfo      = exotic_idx.get((race_date, wager_type, span))
            if einfo is None:
                continue
            exotic_raw  = float(einfo['raw'])
            exotic_p2   = float(einfo['p2'])
            wager_base  = einfo['base']
            leg_payouts = [float(r['win_payout']) for r in last_n]
            leg_fields  = [r['field_size'] for r in last_n if r['field_size']]
            parlay = 2.0
            for p in leg_payouts:
                parlay *= p / 2.0
            parlay = round(parlay, 2)
            ratio  = round(exotic_p2 / parlay, 3) if parlay > 0 else None
            matched[wager_type].append({
                'date':        race_date,
                'span':        span,
                'parlay':      parlay,
                'exotic':      round(exotic_raw, 2),
                'exotic_p2':   round(exotic_p2, 2),
                'wager_base':  wager_base,
                'edge':        round(exotic_p2 - parlay, 2),
                'ratio':       ratio,
                'leg_payouts': [round(p, 2) for p in leg_payouts],
                'max_leg':     round(max(leg_payouts), 2),
                'avg_field':   round(sum(leg_fields) / len(leg_fields), 1) if leg_fields else None,
            })

    _THRESH = [6, 8, 10, 12, 15, 20, 25, 30, 40, 50]

    summary = {}
    for wager_type, days in matched.items():
        if not days:
            continue
        ratios = [d['ratio'] for d in days if d['ratio'] is not None]
        if not ratios:
            continue
        n = len(ratios)
        rs = sorted(ratios)
        mid = n // 2
        median_r = rs[mid] if n % 2 == 1 else (rs[mid - 1] + rs[mid]) / 2
        edges = [d['edge'] for d in days]
        exotic_won = sum(1 for r in ratios if r > 1.0)
        parlay_won = sum(1 for r in ratios if r < 1.0)

        thresh_analysis = []
        for t in _THRESH:
            sub = [d for d in days if d.get('max_leg', 0) >= t]
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

        summary[wager_type] = {
            'sample':                 n,
            'mean_ratio':             round(sum(ratios) / n, 3),
            'median_ratio':           round(median_r, 3),
            'exotic_beat_parlay_pct': round(exotic_won / n * 100, 1),
            'parlay_beat_exotic_pct': round(parlay_won / n * 100, 1),
            'avg_edge':               round(sum(edges) / n, 2),
            'threshold_analysis':     thresh_analysis,
            'days':                   sorted(days, key=lambda d: -(d['ratio'] or 0)),
        }
    return summary


def _print_parlay(track):
    summary = parlay_vs_exotic(track)
    width   = 70
    print()
    print("=" * width)
    print(f"  PARLAY vs EXOTIC  |  Track: {track}  |  $2 base")
    print("=" * width)

    if not summary:
        print(f"\n  No matched parlay/exotic pairs found for {track}.")
        print()
        return

    for wager_type in ('P4', 'P5', 'P6'):
        s = summary.get(wager_type)
        if not s:
            continue
        verdict = (
            "EXOTIC WINS" if s['mean_ratio'] > 1.1 else
            "ROUGHLY EVEN" if s['mean_ratio'] >= 0.9 else
            "PARLAY WINS"
        )
        print()
        print(f"  {wager_type}  --  {s['sample']} matched day(s)  [{verdict}]")
        print(f"  {'-' * (width - 2)}")
        print(f"  Mean ratio (exotic / parlay):    {s['mean_ratio']:.3f}x")
        print(f"  Median ratio:                    {s['median_ratio']:.3f}x")
        print(f"  Exotic beat parlay:              {s['exotic_beat_parlay_pct']:.1f}% of days")
        print(f"  Parlay beat exotic:              {s['parlay_beat_exotic_pct']:.1f}% of days")
        print(f"  Avg dollar edge (exotic-parlay): ${s['avg_edge']:+.2f}")
        print()
        hdr = (
            f"  {'Date':<12} {'Span':<14} {'MaxLeg':>8} "
            f"{'Parlay $':>11} {'Posted':>12} {'$2 Equiv':>12} {'Ratio':>8}  Winner"
        )
        print(hdr)
        print(f"  {'-' * (width - 2)}")
        for d in s['days']:
            winner  = "EXOTIC" if d['ratio'] and d['ratio'] > 1.0 else "PARLAY"
            r_str   = f"{d['ratio']:.3f}x" if d['ratio'] is not None else "N/A"
            ml_str  = f"${d['max_leg']:.2f}" if d.get('max_leg') is not None else "N/A"
            base    = d.get('wager_base', 2.0)
            base_lbl = f"@${base:.2f}"
            print(
                f"  {d['date']:<12} {d['span']:<14} {ml_str:>8} "
                f"${d['parlay']:>10,.2f} "
                f"${d['exotic']:>8,.2f}{base_lbl:<5} "
                f"${d['exotic_p2']:>10,.2f} "
                f"{r_str:>8}  {winner}"
            )

        thresh = s.get('threshold_analysis', [])
        if thresh:
            print()
            print(f"  Breakeven threshold — exotic win rate when any leg paid >= $X:")
            print(f"  {'Min Leg $':>10} {'Days':>6} {'Exotic Win%':>12} {'Avg Ratio':>10}")
            print(f"  {'-' * 44}")
            for row in thresh:
                mark = "  <-- crossover" if row['exotic_win_pct'] >= 50 else ""
                print(
                    f"  ${row['min_leg']:>9} {row['sample']:>6} "
                    f"{row['exotic_win_pct']:>11.1f}% {row['avg_ratio']:>10.3f}x{mark}"
                )
    print()


# ── Longshot Threshold ───────────────────────────────────────────────────────

def longshot_threshold(track):
    """
    For each wager type (P4, P5, P6) at a track, find the minimum max-leg
    win-payout at which exotics (payout_per_2) beat parlays >= 50% of days.

    Returns a dict keyed by wager type, each with:
        crossover_leg   – min leg $ at which exotic wins >= 50% of qualifying days
        exotic_win_pct  – exotic win pct at that threshold
        avg_ratio       – mean exotic_p2 / parlay ratio at that threshold
        sample          – number of qualifying days at that threshold
        no_crossover    – True if exotic never reaches 50% across all thresholds
        best_pct        – highest exotic win pct seen (if no crossover)
        full_sample     – total matched days (all thresholds)
    """
    summary = parlay_vs_exotic(track)
    result = {}
    for wager_type, s in summary.items():
        thresh = s.get('threshold_analysis', [])
        full_sample = s.get('sample', 0)
        crossover = next((r for r in thresh if r['exotic_win_pct'] >= 50.0), None)
        if crossover:
            result[wager_type] = {
                'crossover_leg':  crossover['min_leg'],
                'exotic_win_pct': crossover['exotic_win_pct'],
                'avg_ratio':      crossover['avg_ratio'],
                'sample':         crossover['sample'],
                'no_crossover':   False,
                'best_pct':       crossover['exotic_win_pct'],
                'full_sample':    full_sample,
            }
        else:
            best = max(thresh, key=lambda r: r['exotic_win_pct']) if thresh else None
            result[wager_type] = {
                'crossover_leg':  None,
                'exotic_win_pct': None,
                'avg_ratio':      None,
                'sample':         None,
                'no_crossover':   True,
                'best_pct':       best['exotic_win_pct'] if best else None,
                'full_sample':    full_sample,
            }
    return result


def _print_longshot_threshold(track):
    result = longshot_threshold(track)
    width  = 70
    print()
    print("=" * width)
    print(f"  LONGSHOT THRESHOLD  |  Track: {track}  |  payout_per_2 basis")
    print("=" * width)
    print(f"  Min leg $ at which exotic (payout_per_2) wins >= 50% of qualifying days")
    print()

    if not result:
        print(f"  No parlay/exotic data found for {track}.")
        print()
        return

    hdr = f"  {'Wager':>6}  {'Days':>5}  {'Crossover $':>12}  {'Win%@Cross':>11}  {'Ratio@Cross':>12}  {'Status'}"
    print(hdr)
    print(f"  {'-' * (width - 2)}")

    for wager_type in ('P4', 'P5', 'P6'):
        r = result.get(wager_type)
        if not r:
            continue
        n = r['full_sample'] or 0
        if r['no_crossover']:
            best_pct = f"{r['best_pct']:.1f}%" if r['best_pct'] is not None else "N/A"
            print(
                f"  {wager_type:>6}  {n:>5}  {'—':>12}  {best_pct:>11}  {'—':>12}  "
                f"NO CROSSOVER (best {best_pct})"
            )
        else:
            cross_str = f"${r['crossover_leg']}"
            win_str   = f"{r['exotic_win_pct']:.1f}%"
            ratio_str = f"{r['avg_ratio']:.3f}x"
            sub_n     = f"({r['sample']} days)"
            print(
                f"  {wager_type:>6}  {n:>5}  {cross_str:>12}  {win_str:>11}  {ratio_str:>12}  "
                f"CROSSOVER {sub_n}"
            )

    # Also print full threshold ladder for each wager type
    print()
    summary = parlay_vs_exotic(track)
    for wager_type in ('P4', 'P5', 'P6'):
        s = summary.get(wager_type)
        if not s or not s.get('threshold_analysis'):
            continue
        print(f"  {wager_type} threshold ladder  "
              f"(overall: exotic won {s['exotic_beat_parlay_pct']:.1f}% of {s['sample']} days, "
              f"mean ratio {s['mean_ratio']:.3f}x):")
        print(f"  {'Min Leg $':>10} {'Days':>6} {'Exotic Win%':>12} {'Avg Ratio':>10}")
        print(f"  {'-' * 44}")
        for row in s['threshold_analysis']:
            mark = "  <-- crossover" if row['exotic_win_pct'] >= 50 else ""
            print(
                f"  ${row['min_leg']:>9} {row['sample']:>6} "
                f"{row['exotic_win_pct']:>11.1f}% {row['avg_ratio']:>10.3f}x{mark}"
            )
        print()


# ── Payout Base Validation ───────────────────────────────────────────────────

def validate_payout_bases():
    """
    Check that all exotic_payouts records use the expected wager_base values.

    Per-track expected bases:
        DD / EX : 2.0 for CD, FG, OP, SA  |  1.0 for AQU, GP, KEE
                  AQU and GP also accept 2.0 (mixed-base history in scraped data)
        P3/P4/P5: 0.5 for AQU, FG, GP, KEE, OP, SA  |  2.0 for CD
        P6      : 0.2 for AQU, FG, KEE, OP, SA  |  2.0 for CD, GP
        TRI     : 0.5 for AQU, FG, GP, KEE, OP, SA  |  2.0 for CD
        SF      : 0.1 all tracks except CD (posts SF at $2)

    Known anomalies (warn but do not fail):
        SA DD/EX at 1.0 on 2026-04-17 – 2026-04-19 (origin unresolved)

    Prints a warning for each violation group (track + wager_type + actual base)
    with count and date range.  Returns True if clean, False if hard violations.
    Run via:  python derby_value.py validate
    """
    _EXPECTED_BASES = {
        # AQU/GP DD/EX: 1.0 primary, 2.0 legacy scraped records
        # KEE: spring meets use fractional bases; fall 2025 meet ran on $2 bases throughout
        'DD':  {'CD': [2.0], 'FG': [2.0], 'OP': [2.0], 'SA': [2.0],
                'AQU': [1.0, 2.0], 'GP': [1.0, 2.0], 'KEE': [1.0, 2.0]},
        'EX':  {'CD': [2.0], 'FG': [2.0], 'OP': [2.0], 'SA': [2.0],
                'AQU': [1.0, 2.0], 'GP': [1.0, 2.0], 'KEE': [1.0, 2.0]},
        'P3':  {'AQU': [0.5], 'FG': [0.5], 'GP': [0.5], 'KEE': [0.5, 2.0], 'OP': [0.5], 'SA': [0.5],
                'CD': [2.0]},
        'P4':  {'AQU': [0.5], 'FG': [0.5], 'GP': [0.5], 'KEE': [0.5, 2.0], 'OP': [0.5], 'SA': [0.5],
                'CD': [2.0]},
        'P5':  {'AQU': [0.5], 'FG': [0.5], 'GP': [0.5], 'KEE': [0.5, 2.0], 'OP': [0.5], 'SA': [0.5],
                'CD': [2.0]},
        'P6':  {'AQU': [0.2], 'FG': [0.2], 'KEE': [0.2, 2.0], 'OP': [0.2], 'SA': [0.2],
                'CD': [2.0], 'GP': [2.0]},
        'TRI': {'AQU': [0.5], 'FG': [0.5], 'GP': [0.5], 'KEE': [0.5, 2.0], 'OP': [0.5], 'SA': [0.5],
                'CD': [2.0]},
        # SF: 0.1 standard; CD posts Superfecta at $2; KEE fall 2025 ran at $2
        'SF':  {'AQU': [0.1], 'FG': [0.1], 'GP': [0.1], 'KEE': [0.1, 2.0], 'OP': [0.1], 'SA': [0.1],
                'CD': [2.0]},
    }
    # Known anomalies: warn in output but do not count as hard violations
    _KNOWN_ANOMALIES = {
        ('SA', 'DD', 1.0): "known anomaly 2026-04-17–19, origin unresolved",
        ('SA', 'EX', 1.0): "known anomaly 2026-04-17–19, origin unresolved",
    }

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT track, wager_type, wager_base,
               COUNT(*) AS cnt,
               MIN(race_date) AS first_date,
               MAX(race_date) AS last_date
        FROM exotic_payouts
        GROUP BY track, wager_type, wager_base
        ORDER BY track, wager_type, wager_base
    """)
    rows = c.fetchall()
    conn.close()

    violations = []
    warnings   = []
    for track, wager_type, actual_base, cnt, first_date, last_date in rows:
        allowed = None
        if wager_type in _EXPECTED_BASES:
            allowed = _EXPECTED_BASES[wager_type].get(track)
            if allowed is None:
                violations.append((track, wager_type, actual_base, cnt, first_date, last_date,
                                   f"no expected base defined for {track} {wager_type}"))
                continue
        else:
            continue  # unrecognised wager type — skip

        if actual_base not in allowed:
            key = (track, wager_type, actual_base)
            if key in _KNOWN_ANOMALIES:
                warnings.append((track, wager_type, actual_base, cnt, first_date, last_date,
                                  _KNOWN_ANOMALIES[key]))
            else:
                violations.append((track, wager_type, actual_base, cnt, first_date, last_date,
                                   f"expected {allowed[0] if len(allowed) == 1 else allowed}"))

    if warnings:
        print(f"validate_payout_bases: {len(warnings)} known anomaly/anomalies (non-failing):")
        print(f"  {'Track':<6} {'Type':<5} {'ActualBase':>10} {'Count':>7}  {'Date Range':<24} Note")
        print(f"  {'-' * 74}")
        for track, wager_type, actual_base, cnt, first_date, last_date, note in warnings:
            date_range = f"{first_date} – {last_date}"
            print(f"  {track:<6} {wager_type:<5} {actual_base:>10.2f} {cnt:>7}  {date_range:<24} {note}")

    if not violations:
        print("validate_payout_bases: OK — all records match expected bases.")
        return True

    print(f"validate_payout_bases: {len(violations)} violation group(s) found:")
    print(f"  {'Track':<6} {'Type':<5} {'ActualBase':>10} {'Count':>7}  {'Date Range':<24} Note")
    print(f"  {'-' * 74}")
    for track, wager_type, actual_base, cnt, first_date, last_date, note in violations:
        date_range = f"{first_date} – {last_date}"
        print(f"  {track:<6} {wager_type:<5} {actual_base:>10.2f} {cnt:>7}  {date_range:<24} {note}")
    return False


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT DISTINCT track FROM exotic_payouts ORDER BY track")
    all_tracks = [r[0] for r in c.fetchall()]
    conn.close()

    if not all_tracks:
        print("No exotic payout data found. Run HorseRacing.py first.")
        sys.exit(1)

    args = sys.argv[1:]

    # validate mode: python derby_value.py validate
    if args and args[0].lower() == "validate":
        ok = validate_payout_bases()
        sys.exit(0 if ok else 1)

    # longshot mode: python derby_value.py longshot KEE GP ...
    if args and args[0].lower() == "longshot":
        targets = [a.upper() for a in args[1:]] if len(args) > 1 else all_tracks
        for track in targets:
            if track not in all_tracks:
                print(f"Track '{track}' not found. Available: {', '.join(all_tracks)}")
            else:
                _print_longshot_threshold(track)
    # parlay mode: python derby_value.py parlay KEE GP ...
    elif args and args[0].lower() == "parlay":
        targets = [a.upper() for a in args[1:]] if len(args) > 1 else all_tracks
        for track in targets:
            if track not in all_tracks:
                print(f"Track '{track}' not found. Available: {', '.join(all_tracks)}")
            else:
                _print_parlay(track)
    # willpay mode: python derby_value.py willpay KEE GP ...
    elif args and args[0].lower() == "willpay":
        targets = [a.upper() for a in args[1:]] if len(args) > 1 else all_tracks
        for track in targets:
            if track not in all_tracks:
                print(f"Track '{track}' not found. Available: {', '.join(all_tracks)}")
            else:
                _print_willpay(track)
    # profile mode: python derby_value.py profile KEE GP ...
    elif args and args[0].lower() == "profile":
        targets = [a.upper() for a in args[1:]] if len(args) > 1 else all_tracks
        for track in targets:
            if track not in all_tracks:
                print(f"Track '{track}' not found. Available: {', '.join(all_tracks)}")
            else:
                profile_track(track)
    else:
        # full report mode
        targets = [args[0].upper()] if args else all_tracks
        for track in targets:
            if track not in all_tracks:
                print(f"Track '{track}' not found. Available: {', '.join(all_tracks)}")
            else:
                print_report(track)
