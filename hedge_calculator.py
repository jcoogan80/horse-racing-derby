"""
Hedge Calculator for Multi-Leg Exotic Wagers (Pick 3/4/5/6)
Helps determine optimal win bets to protect a live ticket in the final leg.

Usage:
    python hedge_calculator.py              # interactive mode
    python hedge_calculator.py sample       # run built-in sample
"""

import sqlite3
import sys
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "horse_racing.db")


# ── Odds helpers ──────────────────────────────────────────────────────────────

def parse_odds(odds_str):
    """
    Parse an odds string like '5/2', '5-2', '8', '9/1', '1/2', 'even'
    and return a float multiplier (net profit per $1 — does not include stake).

        '5/2'  -> 2.5   '8/1' -> 8.0   'even' -> 1.0   '1/2' -> 0.5
    """
    s = str(odds_str).strip().lower()
    if s in ("even", "evens", "e"):
        return 1.0
    s = s.replace("-", "/")
    if "/" in s:
        parts = s.split("/")
        try:
            return float(parts[0]) / float(parts[1])
        except (ValueError, ZeroDivisionError):
            return None
    try:
        return float(s)
    except ValueError:
        return None


def win_payout_per_dollar(odds_str):
    """Total return per $1 wagered (stake + profit).  5/2 -> $3.50."""
    mult = parse_odds(odds_str)
    if mult is None:
        return None
    return mult + 1.0


def implied_prob(odds_str):
    """
    Implied win probability from bookmaker odds.
    At 5/2: wpd=3.5, prob=1/3.5=28.6%.
    Returns None if odds are unreadable.
    """
    wpd = win_payout_per_dollar(odds_str)
    if wpd is None or wpd <= 0:
        return None
    return 1.0 / wpd


# ── Core calculation ──────────────────────────────────────────────────────────

def calculate_hedge(ticket_cost, estimated_payout, my_horses, all_horses,
                    current_odds, hedge_scale=0.5):
    """
    For each horse NOT covered by your ticket in the final leg, compute
    recommended hedge amounts.

    Parameters:
        ticket_cost      -- total cost of your exotic ticket ($)
        estimated_payout -- estimated payout if your ticket hits ($)
        my_horses        -- list of program numbers you hold in the final leg
        all_horses       -- list of all program numbers in the final leg
        current_odds     -- dict of {pgm: odds_str}, e.g. {1: '5/2', 2: '8/1'}
        hedge_scale      -- 0.0 = break-even only, 1.0 = full profit-neutral,
                            0.5 = midpoint (default)

    Returns:
        list of dicts, one per uncovered horse, sorted by implied_prob desc
    """
    covered = set(str(h) for h in my_horses)
    results = []

    for horse in all_horses:
        pgm      = str(horse)
        if pgm in covered:
            continue

        odds_str = current_odds.get(horse, current_odds.get(pgm, "N/A"))
        wpd      = win_payout_per_dollar(odds_str)
        ip       = implied_prob(odds_str)

        if wpd is None or wpd <= 0:
            results.append({
                "pgm":                pgm,
                "odds":               odds_str,
                "covered":            False,
                "implied_prob":       None,
                "break_even_hedge":   None,
                "profit_neutral":     None,
                "recommended_hedge":  None,
                "net_if_ticket_hits": round(estimated_payout - ticket_cost, 2),
                "net_if_hedge_wins":  None,
                "note":               "unreadable odds",
            })
            continue

        break_even     = ticket_cost / wpd
        profit_neutral = estimated_payout / wpd
        recommended    = break_even + hedge_scale * (profit_neutral - break_even)
        recommended    = max(2.0, round(recommended / 2) * 2)

        net_ticket = round(estimated_payout - ticket_cost - recommended, 2)
        net_hedge  = round(recommended * wpd - recommended - ticket_cost, 2)

        results.append({
            "pgm":                pgm,
            "odds":               odds_str,
            "covered":            False,
            "implied_prob":       ip,
            "break_even_hedge":   round(break_even, 2),
            "profit_neutral":     round(profit_neutral, 2),
            "recommended_hedge":  recommended,
            "net_if_ticket_hits": net_ticket,
            "net_if_hedge_wins":  net_hedge,
            "note":               "",
        })

    results.sort(key=lambda x: x["implied_prob"] or 0, reverse=True)
    return results


# ── Analyze ticket ────────────────────────────────────────────────────────────

def analyze_ticket(ticket_cost, legs, current_leg, estimated_payout,
                   last_leg_horses, current_odds):
    """
    Full picture wrapper. Returns investment summary + ranked hedge table.

    Returns dict with hedges list and summary stats.
    """
    all_horses = sorted(current_odds.keys(),
                        key=lambda x: int(x) if str(x).isdigit() else 999)
    hedges = calculate_hedge(ticket_cost, estimated_payout,
                             last_leg_horses, all_horses, current_odds)

    covered_count    = len([h for h in all_horses
                            if str(h) in set(str(x) for x in last_leg_horses)])
    uncovered_count  = len(all_horses) - covered_count
    total_hedge_cost = sum(h["recommended_hedge"] for h in hedges
                           if h["recommended_hedge"] is not None)
    net_do_nothing   = round(estimated_payout - ticket_cost, 2)
    net_hedged_best  = round(
        max((h["net_if_ticket_hits"] for h in hedges if h["net_if_ticket_hits"] is not None),
            default=net_do_nothing), 2
    )

    return {
        "ticket_cost":                       ticket_cost,
        "estimated_payout":                  estimated_payout,
        "legs":                              legs,
        "current_leg":                       current_leg,
        "covered_horses":                    covered_count,
        "uncovered_horses":                  uncovered_count,
        "total_hedge_cost":                  round(total_hedge_cost, 2),
        "net_do_nothing":                    net_do_nothing,
        "net_if_ticket_hits_with_full_hedge": net_hedged_best,
        "hedges":                            hedges,
    }


# ── Scenario table ────────────────────────────────────────────────────────────

def scenario_table(ticket_cost, estimated_payout, my_horses, all_horses,
                   current_odds, partial_threshold=8.0):
    """
    One-glance table showing outcomes for every horse in the field.

    Columns returned per row:
        pgm, odds, implied_prob, covered,
        full_hedge_amount,    net_full_hedge,
        partial_hedge_amount, net_partial_hedge,
        net_no_hedge

    partial_threshold -- horses with odds <= this value (e.g. 8.0 = 8/1 or lower)
                         are included in the partial hedge; longshots are skipped.

    Rows are sorted by implied_prob descending (most dangerous threats first).
    """
    covered_set = set(str(h) for h in my_horses)
    hedges_map  = {
        h["pgm"]: h
        for h in calculate_hedge(ticket_cost, estimated_payout,
                                 my_horses, all_horses, current_odds)
    }

    # Pre-compute totals needed for net calculations
    full_hedge_total    = sum(
        h["recommended_hedge"] for h in hedges_map.values()
        if h["recommended_hedge"] is not None
    )
    partial_hedge_total = sum(
        h["recommended_hedge"] for h in hedges_map.values()
        if h["recommended_hedge"] is not None
        and parse_odds(h["odds"]) is not None
        and parse_odds(h["odds"]) <= partial_threshold
    )

    rows = []
    for horse in all_horses:
        pgm      = str(horse)
        odds_str = current_odds.get(horse, current_odds.get(pgm, "N/A"))
        wpd      = win_payout_per_dollar(odds_str)
        ip       = implied_prob(odds_str)
        mult     = parse_odds(odds_str)

        if pgm in covered_set:
            rows.append({
                "pgm":                  pgm,
                "odds":                 odds_str,
                "implied_prob":         ip,
                "covered":              True,
                "full_hedge_amount":    0,
                "net_full_hedge":       round(estimated_payout - ticket_cost - full_hedge_total, 2),
                "partial_hedge_amount": 0,
                "net_partial_hedge":    round(estimated_payout - ticket_cost - partial_hedge_total, 2),
                "net_no_hedge":         round(estimated_payout - ticket_cost, 2),
            })
        else:
            h         = hedges_map.get(pgm)
            full_amt  = h["recommended_hedge"] if h else None
            is_threat = mult is not None and mult <= partial_threshold
            part_amt  = full_amt if (h and is_threat) else 0

            # net_full_hedge: this horse wins, you collected full_amt*wpd, spent full_hedge_total+ticket
            if full_amt and wpd:
                net_full = round(full_amt * wpd - full_hedge_total - ticket_cost, 2)
            else:
                net_full = round(-full_hedge_total - ticket_cost, 2)

            # net_partial_hedge: hedged? collect part_amt*wpd; unhedged? collect 0
            if is_threat and part_amt and wpd:
                net_part = round(part_amt * wpd - partial_hedge_total - ticket_cost, 2)
            else:
                net_part = round(-partial_hedge_total - ticket_cost, 2)

            net_none = round(-ticket_cost, 2)

            rows.append({
                "pgm":                  pgm,
                "odds":                 odds_str,
                "implied_prob":         ip,
                "covered":              False,
                "full_hedge_amount":    full_amt,
                "net_full_hedge":       net_full,
                "partial_hedge_amount": part_amt if is_threat else None,
                "net_partial_hedge":    net_part,
                "net_no_hedge":         net_none,
            })

    # Sort: most dangerous (highest implied prob) first
    rows.sort(key=lambda r: r["implied_prob"] or 0, reverse=True)
    return rows, full_hedge_total, partial_hedge_total


# ── Budget hedge ──────────────────────────────────────────────────────────────

def hedge_with_budget(ticket_cost, estimated_payout, my_horses, all_horses,
                      current_odds, budget):
    """
    Allocate a fixed dollar budget across uncovered horses, weighted
    proportional to their implied win probability.

    The most dangerous horses get the most hedge money.
    Allocations are rounded to $2 increments (minimum $2).

    Parameters:
        budget -- total dollars available for ALL hedge bets combined

    Returns dict:
        budget           -- requested budget
        actual_total     -- sum of rounded allocations (may differ slightly)
        net_if_covered   -- net profit if your ticket hits (est_payout - ticket - hedges)
        allocations      -- list of dicts per uncovered horse, sorted by implied_prob desc
        coverage_notes   -- list of strings flagging horses the budget can't protect
    """
    covered_set = set(str(h) for h in my_horses)

    # Collect uncovered horses with valid odds
    uncovered = []
    for horse in all_horses:
        pgm      = str(horse)
        if pgm in covered_set:
            continue
        odds_str = current_odds.get(horse, current_odds.get(pgm, "N/A"))
        wpd      = win_payout_per_dollar(odds_str)
        ip       = implied_prob(odds_str)
        if wpd is None or ip is None:
            continue
        uncovered.append({
            "pgm":          pgm,
            "odds":         odds_str,
            "implied_prob": ip,
            "wpd":          wpd,
        })

    if not uncovered:
        return {
            "budget": budget, "actual_total": 0,
            "net_if_covered": round(estimated_payout - ticket_cost, 2),
            "allocations": [], "coverage_notes": [],
        }

    total_ip = sum(h["implied_prob"] for h in uncovered)

    # Proportional allocation rounded to $2
    allocations = []
    for h in uncovered:
        weight    = h["implied_prob"] / total_ip
        raw_alloc = budget * weight
        alloc     = max(2.0, round(raw_alloc / 2) * 2)
        allocations.append({**h, "allocated": alloc})

    actual_total = sum(a["allocated"] for a in allocations)

    # Net outcomes: all hedge bets are placed before the race
    net_if_covered = round(estimated_payout - ticket_cost - actual_total, 2)

    for a in allocations:
        # If this horse wins: collect a["allocated"]*wpd, spent actual_total+ticket_cost
        a["net_if_wins"] = round(a["allocated"] * a["wpd"] - actual_total - ticket_cost, 2)
        # Minimum bet on this horse alone to break even on the FULL outlay
        # (ticket + entire hedge budget)
        a["break_even_needed"] = round((ticket_cost + actual_total) / a["wpd"], 2)
        a["implied_prob_pct"]  = round(a["implied_prob"] * 100, 1)
        del a["implied_prob"]  # keep dict clean; pct version used for display

    allocations.sort(key=lambda x: x["implied_prob_pct"], reverse=True)

    # Flag horses where the budget allocation can't make this scenario profitable
    coverage_notes = []
    for a in allocations:
        if a["net_if_wins"] < 0:
            shortfall = round(a["break_even_needed"] - a["allocated"], 2)
            coverage_notes.append(
                f"#{a['pgm']} ({a['odds']}): allocated ${a['allocated']:.0f}, "
                f"need ${a['break_even_needed']:.2f} to break even "
                f"(short ${shortfall:.2f})"
            )

    return {
        "budget":          budget,
        "actual_total":    round(actual_total, 2),
        "net_if_covered":  net_if_covered,
        "allocations":     allocations,
        "coverage_notes":  coverage_notes,
    }


# ── DB historical lookup ──────────────────────────────────────────────────────

def historical_payouts(track, wager_type="P6", limit=20):
    """Pull recent exotic payouts from horse_racing.db for context."""
    if not os.path.exists(DB_PATH):
        return []
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            """
            SELECT race_date, race_span, payout
            FROM exotic_payouts
            WHERE track=? AND wager_type=?
            ORDER BY race_date DESC, race_span
            LIMIT ?
            """,
            (track.upper(), wager_type.upper(), limit)
        )
        rows = c.fetchall()
        conn.close()
        return rows
    except Exception:
        return []


# ── Print helpers ─────────────────────────────────────────────────────────────

def _fmt(val, prefix="$", decimals=2):
    if val is None:
        return "    N/A"
    s    = f"{abs(val):,.{decimals}f}"
    sign = "-" if val < 0 else " "
    return f"{sign}{prefix}{s}"


def print_scenario_table(rows, ticket_cost, estimated_payout,
                         full_hedge_total, partial_hedge_total,
                         partial_threshold=8.0):
    w = 90
    print()
    print("=" * w)
    print("  SCENARIO TABLE  --  What happens if each horse wins the final leg")
    print(f"  Sorted by win probability  |  Partial hedge = {partial_threshold:.0f}/1 or shorter only")
    print("=" * w)
    hdr = (
        f"  {'Pgm':>4}  {'Odds':<7} {'Win%':>5}  {'Cov':>4}  "
        f"{'Full Hedge':>10}  {'Net/Full':>12}  "
        f"{'Part Hedge':>10}  {'Net/Part':>12}  {'Net/None':>11}"
    )
    print(hdr)
    print("  " + "-" * (w - 2))

    for r in rows:
        cov      = "YES" if r["covered"] else " no"
        ip_str   = f"{r['implied_prob']*100:.1f}%" if r["implied_prob"] else "  N/A"

        if r["covered"]:
            full_str = "    ----"
            part_str = "    ----"
        else:
            full_str = (f"${r['full_hedge_amount']:>8,.0f}"
                        if r["full_hedge_amount"] else "    ----")
            if r["partial_hedge_amount"]:
                part_str = f"${r['partial_hedge_amount']:>8,.0f}"
            elif r["partial_hedge_amount"] == 0:
                part_str = "    ----"   # covered horse
            else:
                part_str = "  (skip)"   # longshot, not hedged in partial mode

        nfh  = _fmt(r["net_full_hedge"])
        nph  = _fmt(r["net_partial_hedge"])
        nnh  = _fmt(r["net_no_hedge"])

        print(
            f"  {r['pgm']:>4}  {r['odds']:<7} {ip_str:>5}  {cov:>4}  "
            f"{full_str:>10}  {nfh:>12}  "
            f"{part_str:>10}  {nph:>12}  {nnh:>11}"
        )

    print("  " + "-" * (w - 2))
    print(
        f"  Full hedge total  : ${full_hedge_total:>10,.2f}  "
        f"(covers ALL {sum(1 for r in rows if not r['covered'])} uncovered horses)"
    )
    partial_covered = sum(
        1 for r in rows
        if not r["covered"] and r["partial_hedge_amount"] is not None
        and r["partial_hedge_amount"] > 0
    )
    print(
        f"  Partial hedge total: ${partial_hedge_total:>9,.2f}  "
        f"(covers {partial_covered} realistic threats at <={partial_threshold:.0f}/1)"
    )
    print(f"\n  Ticket cost: ${ticket_cost:,.2f}   Est. payout if ticket hits: ${estimated_payout:,.2f}")
    print()


def print_analyze_ticket(result):
    width = 68
    print()
    print("=" * width)
    print(f"  HEDGE ANALYSIS  --  Pick {result['legs']}  |  After leg {result['current_leg']}")
    print("=" * width)
    print(f"  Ticket cost          : ${result['ticket_cost']:>10,.2f}")
    print(f"  Estimated payout     : ${result['estimated_payout']:>10,.2f}")
    print(f"  Horses covered (leg) : {result['covered_horses']}")
    print(f"  Horses uncovered     : {result['uncovered_horses']}")
    print(f"  Total hedge cost     : ${result['total_hedge_cost']:>10,.2f}")
    print()
    print(f"  Do-nothing net profit: {_fmt(result['net_do_nothing'])}")
    print()

    hedges = result["hedges"]
    if not hedges:
        print("  No uncovered horses -- no hedging needed.")
    else:
        print(
            f"  {'Pgm':>4}  {'Odds':<8} {'Win%':>5}  {'B/E Hedge':>10} {'P/N Hedge':>10} "
            f"{'Rec Hedge':>10}  {'Net/Ticket':>11}  {'Net/Hedge':>10}"
        )
        print("  " + "-" * (width - 2))
        for h in hedges:
            ip_str = f"{h['implied_prob']*100:.1f}%" if h["implied_prob"] else "  N/A"
            be     = f"${h['break_even_hedge']:>8,.2f}"  if h["break_even_hedge"]  is not None else "     N/A"
            pn     = f"${h['profit_neutral']:>8,.2f}"    if h["profit_neutral"]    is not None else "     N/A"
            rec    = f"${h['recommended_hedge']:>8,.0f}" if h["recommended_hedge"] is not None else "     N/A"
            nt     = _fmt(h["net_if_ticket_hits"])
            nh     = _fmt(h["net_if_hedge_wins"])
            print(
                f"  {h['pgm']:>4}  {h['odds']:<8} {ip_str:>5}  {be:>10} {pn:>10} "
                f"{rec:>10}  {nt:>11}  {nh:>10}"
            )
    print()
    print("  Column guide:")
    print("  B/E Hedge  = bet this much to break even if uncovered horse wins")
    print("  P/N Hedge  = bet this much to match ticket payout if uncovered horse wins")
    print("  Rec Hedge  = suggested amount (halfway between B/E and P/N, rounded to $2)")
    print("  Net/Ticket = your net if YOUR ticket hits (after ticket + all hedge costs)")
    print("  Net/Hedge  = your net if the HEDGE HORSE wins (win bet return minus costs)")
    print()


def print_budget_hedge(result, ticket_cost, estimated_payout):
    w = 72
    print()
    print("=" * w)
    print(f"  BUDGET HEDGE  --  ${result['budget']:,.2f} allocated across uncovered threats")
    print("  Strategy: proportional to implied win probability")
    print("=" * w)
    print(f"  Requested budget  : ${result['budget']:>10,.2f}")
    print(f"  Actual total      : ${result['actual_total']:>10,.2f}  (rounded to $2 increments)")
    print(f"  Ticket cost       : ${ticket_cost:>10,.2f}")
    print()
    print(f"  If your ticket hits  :  net {_fmt(result['net_if_covered'])}")
    print()

    allocs = result["allocations"]
    if not allocs:
        print("  No uncovered horses to hedge.")
    else:
        print(
            f"  {'Pgm':>4}  {'Odds':<8} {'Win%':>5}  {'Allocated':>10}  "
            f"{'Net if Wins':>13}  {'B/E Needed':>12}  {'Profitable?':>12}"
        )
        print("  " + "-" * (w - 2))
        for a in allocs:
            profitable = "YES" if a["net_if_wins"] >= 0 else f"short ${a['break_even_needed'] - a['allocated']:,.0f}"
            print(
                f"  {a['pgm']:>4}  {a['odds']:<8} {a['implied_prob_pct']:>4.1f}%  "
                f"${a['allocated']:>9,.0f}  "
                f"{_fmt(a['net_if_wins']):>13}  "
                f"${a['break_even_needed']:>10,.2f}  {profitable:>12}"
            )

    print()
    if result["coverage_notes"]:
        print(f"  This ${result['budget']:,.0f} budget cannot make any uncovered horse profitable.")
        print(f"  Break-even needed = (ticket + full budget) / odds.  Shortfalls:")
        for note in result["coverage_notes"]:
            print(f"    - {note}")
        print()
        top = result["allocations"][0]
        print(
            f"  To break even if #{top['pgm']} ({top['odds']}) wins, "
            f"you'd need a total hedge budget of ~${top['break_even_needed']:,.0f} "
            f"placed entirely on that horse."
        )
    else:
        print("  All uncovered horses are profitable even after full hedge spend.")
    print()


def print_historical(track, wager_type, rows):
    if not rows:
        print(f"  No {wager_type} history found for {track} in database.")
        return
    print(f"  Recent {wager_type} payouts at {track}:")
    print(f"  {'Date':<12} {'Races':<14} {'Payout':>12}")
    print("  " + "-" * 40)
    for date, span, payout in rows:
        print(f"  {date:<12} {span:<14} ${payout:>10,.2f}")
    avg = sum(p for _, _, p in rows) / len(rows)
    print(f"  {'Average':<26} ${avg:>10,.2f}  ({len(rows)} payouts)")
    print()


# ── Interactive mode ──────────────────────────────────────────────────────────

def _prompt_float(label, default=None):
    hint = f" [{default}]" if default is not None else ""
    while True:
        raw = input(f"  {label}{hint}: ").strip()
        if raw == "" and default is not None:
            return float(default)
        try:
            return float(raw.replace(",", "").replace("$", ""))
        except ValueError:
            print("  Please enter a number.")


def _prompt_int(label, default=None):
    hint = f" [{default}]" if default is not None else ""
    while True:
        raw = input(f"  {label}{hint}: ").strip()
        if raw == "" and default is not None:
            return int(default)
        try:
            return int(raw)
        except ValueError:
            print("  Please enter a whole number.")


def interactive_mode():
    print()
    print("=" * 60)
    print("  HEDGE CALCULATOR  --  Interactive Mode")
    print("=" * 60)

    track_input = input("  Track code for historical data (or Enter to skip): ").strip().upper()
    wager_type  = input("  Wager type [P6]: ").strip().upper() or "P6"
    legs_map    = {"P3": 3, "P4": 4, "P5": 5, "P6": 6, "DD": 2}
    total_legs  = legs_map.get(wager_type, _prompt_int("  Total legs in wager", 6))

    if track_input:
        hist = historical_payouts(track_input, wager_type)
        print()
        print_historical(track_input, wager_type, hist[:10])

    print()
    ticket_cost      = _prompt_float("Ticket cost ($)")
    estimated_payout = _prompt_float("Estimated payout if ticket hits ($)")
    current_leg_done = _prompt_int(
        f"How many legs have you survived (out of {total_legs})", total_legs - 1
    )

    print()
    field_size = _prompt_int("  How many horses in the final leg")
    print("  Enter program numbers you hold in the final leg (comma-separated):")
    raw_my = input("  Your horses: ").strip()
    my_horses = [x.strip() for x in raw_my.split(",") if x.strip()]

    print("  Enter all program numbers in the field (comma-separated):")
    raw_all = input("  All horses: ").strip()
    all_horses = [x.strip() for x in raw_all.split(",") if x.strip()]
    if not all_horses:
        all_horses = [str(i) for i in range(1, field_size + 1)]

    print()
    print("  Enter current odds for each horse (e.g.  3  5/2  8/1  even)")
    current_odds = {}
    for pgm in all_horses:
        raw_odds = input(f"    Horse #{pgm} odds: ").strip()
        current_odds[pgm] = raw_odds if raw_odds else "N/A"

    result = analyze_ticket(
        ticket_cost, total_legs, current_leg_done,
        estimated_payout, my_horses, current_odds
    )
    print_analyze_ticket(result)

    rows, full_total, part_total = scenario_table(
        ticket_cost, estimated_payout, my_horses, all_horses, current_odds
    )
    print_scenario_table(rows, ticket_cost, estimated_payout, full_total, part_total)

    raw_budget = input("  Enter hedge budget for budget mode (or Enter to skip): ").strip()
    if raw_budget:
        try:
            budget = float(raw_budget.replace(",", "").replace("$", ""))
            bh = hedge_with_budget(
                ticket_cost, estimated_payout, my_horses, all_horses, current_odds, budget
            )
            print_budget_hedge(bh, ticket_cost, estimated_payout)
        except ValueError:
            pass


# ── Sample run ────────────────────────────────────────────────────────────────

SAMPLE_ODDS = {
    1:  "5/2",
    2:  "3/1",
    3:  "8/1",
    4:  "6/1",
    5:  "9/2",
    6:  "15/1",
    7:  "4/1",
    8:  "12/1",
    9:  "20/1",
    10: "7/2",
}

def run_sample(output=None):
    """
    Sample: $120 Pick 6 ticket (partial wheel).
    Estimated payout: $180,000.
    User holds horses 2, 5, 8 in the 10-horse final leg.
    Derby-range morning line odds.
    Budget hedge: $500.
    """
    ticket_cost      = 120.00
    estimated_payout = 180_000.00
    my_horses        = [2, 5, 8]
    all_horses       = list(range(1, 11))
    current_odds     = SAMPLE_ODDS
    total_legs       = 6
    current_leg_done = 5
    track            = "CD"
    wager_type       = "P6"
    hedge_budget     = 500.00

    import io
    buf        = io.StringIO()
    old_stdout = sys.stdout
    if output:
        sys.stdout = buf

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    print()
    print("=" * 72)
    print("  HEDGE CALCULATOR  --  SAMPLE RUN")
    print(f"  Generated: {generated}")
    print("=" * 72)
    print()
    print("  Scenario:")
    print(f"    Wager type       : Pick {total_legs}")
    print(f"    Ticket cost      : ${ticket_cost:,.2f}")
    print(f"    Estimated payout : ${estimated_payout:,.2f}")
    print(f"    Legs survived    : {current_leg_done} of {total_legs}")
    print(f"    My horses (leg 6): {', '.join(str(h) for h in my_horses)}")
    print(f"    Field size       : {len(all_horses)} horses")
    print()
    print("  Final leg odds:")
    for pgm, odds in current_odds.items():
        covered = " <-- YOUR HORSE" if pgm in my_horses else ""
        print(f"    #{pgm:>2}  {odds:<8}{covered}")
    print()

    # Historical context
    hist = historical_payouts(track, wager_type, limit=10)
    if hist:
        print_historical(track, wager_type, hist)
    else:
        print(f"  (No {wager_type} history for {track} in local database yet)")
        print()

    # Full analysis table
    result = analyze_ticket(
        ticket_cost, total_legs, current_leg_done,
        estimated_payout, my_horses, current_odds
    )
    print_analyze_ticket(result)

    # Scenario table (full vs partial vs nothing, sorted by win probability)
    rows, full_total, part_total = scenario_table(
        ticket_cost, estimated_payout, my_horses, all_horses, current_odds
    )
    print_scenario_table(rows, ticket_cost, estimated_payout, full_total, part_total)

    # Budget hedge with $500
    bh = hedge_with_budget(
        ticket_cost, estimated_payout, my_horses, all_horses, current_odds, hedge_budget
    )
    print_budget_hedge(bh, ticket_cost, estimated_payout)

    if output:
        sys.stdout = old_stdout
        text = buf.getvalue()
        with open(output, "w", encoding="utf-8") as f:
            f.write(text)
        sys.stdout.write(text)
        print(f"  Sample saved to: {output}")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]

    if args and args[0].lower() == "sample":
        sample_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "hedge_calculator_sample.txt"
        )
        run_sample(output=sample_path)
    else:
        interactive_mode()
