"""
Horse Racing Analysis
Reads from horse_racing.db and writes analysis tabs to Google Sheets.
Run this separately after scraping data with HorseRacing.py
"""

import sqlite3
import pandas as pd
import numpy as np
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import os
import time

# ── Config ───────────────────────────────────────────────────────────────────

DB_PATH          = os.path.join(os.path.dirname(os.path.abspath(__file__)), "horse_racing.db")
CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")
SHEET_NAME       = "Horse Racing"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# ── Google Sheets Helpers ────────────────────────────────────────────────────

def get_gsheet():
    creds  = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open(SHEET_NAME)

def write_tab(sheet, tab_name, df, note=None):
    """Write a dataframe to a Google Sheet tab with an optional header note."""
    try:
        ws = sheet.worksheet(tab_name)
        ws.clear()
    except gspread.exceptions.WorksheetNotFound:
        ws = sheet.add_worksheet(title=tab_name, rows=2000, cols=30)

    df = df.fillna("")
    timestamp = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    rows = []
    rows.append([f"Last Updated: {timestamp}"] + [""] * (len(df.columns) - 1))
    if note:
        rows.append([note] + [""] * (len(df.columns) - 1))
    rows.append([])  # blank spacer row
    rows.append(df.columns.tolist())
    rows += df.values.tolist()
    ws.update(rows, value_input_option="USER_ENTERED")
    print(f"  Written: '{tab_name}' ({len(df)} rows)")
    time.sleep(1)

# ── Load Data ────────────────────────────────────────────────────────────────

def load_data():
    conn = sqlite3.connect(DB_PATH)
    races   = pd.read_sql("SELECT * FROM race_results",   conn)
    exotics = pd.read_sql("SELECT * FROM exotic_payouts", conn)
    conn.close()
    print(f"Loaded {len(races)} race results and {len(exotics)} exotic payouts.")
    return races, exotics

# ── Analysis 1: Track Condition Impact ───────────────────────────────────────

def analyze_track_conditions(races, exotics):
    """
    Shows win payouts and exotic payouts broken down by track surface condition.
    Helps identify if muddy/sloppy tracks produce bigger payouts (more chaos).
    """
    print("\nAnalyzing track conditions...")

    # Extract track condition from distance field (Equibase puts condition in race details)
    # We'll join races with exotics to get condition + payout combos

    # Average win payout by track condition
    cond_wins = races.groupby("surface").agg(
        Races        = ("race_num", "count"),
        Avg_Win_Pay  = ("win_payout", "mean"),
        Avg_Place    = ("place_payout", "mean"),
        Avg_Show     = ("show_payout", "mean"),
        Max_Win_Pay  = ("win_payout", "max"),
    ).reset_index().round(2)
    cond_wins.columns = ["Surface", "# Races", "Avg Win $", "Avg Place $", "Avg Show $", "Max Win $"]

    # Merge exotics with race condition info
    race_info = races[["track","race_date","race_num","surface"]].copy()
    ex_merged = exotics.merge(race_info, on=["track","race_date","race_num"], how="left")

    # Average exotic payout by surface and wager type
    exotic_by_surface = ex_merged[ex_merged["wager_type"].isin(["DD","P3","P4","P5"])]\
        .groupby(["surface","wager_type"])["payout"].mean().reset_index()
    exotic_by_surface.columns = ["Surface", "Wager", "Avg Payout $"]
    exotic_by_surface = exotic_by_surface.round(2)
    exotic_by_surface = exotic_by_surface.sort_values(["Surface","Wager"])

    # Combine into one dataframe with a separator
    separator = pd.DataFrame([["--- EXOTIC PAYOUTS BY SURFACE ---","",""]], columns=exotic_by_surface.columns)
    combined = pd.concat([
        cond_wins.rename(columns={"Surface":"Surface","# Races":"# Races"}),
        pd.DataFrame([["","","","","",""]],  columns=cond_wins.columns),  # spacer
    ], ignore_index=True)

    return cond_wins, exotic_by_surface

# ── Analysis 2: Best Races for Pick 3/4/5 Value ──────────────────────────────

def analyze_pick_value(races, exotics):
    """
    Looks at which race numbers produce the best Pick 3/4/5 payouts.
    High average payouts = good value sequences to target.
    """
    print("Analyzing Pick 3/4/5 value by race...")

    pick_exotics = exotics[exotics["wager_type"].isin(["P3","P4","P5","P6"])].copy()

    # Average payout by wager type and starting race number
    pick_exotics["start_race"] = pick_exotics["race_span"].apply(
        lambda x: int(x.split("-")[0]) if "-" in str(x) else int(x)
    )

    summary = pick_exotics.groupby(["wager_type","race_span"]).agg(
        Times_Hit    = ("payout", "count"),
        Avg_Payout   = ("payout", "mean"),
        Min_Payout   = ("payout", "min"),
        Max_Payout   = ("payout", "max"),
        Median       = ("payout", "median"),
    ).reset_index().round(2)

    summary.columns = ["Wager", "Races", "Times Hit", "Avg Payout $", "Min $", "Max $", "Median $"]
    summary = summary.sort_values(["Wager","Races"])

    # Add a ROI indicator - flag sequences with avg payout > $50 (good value)
    summary["Value Flag"] = summary["Avg Payout $"].apply(
        lambda x: "⭐ HIGH VALUE" if x >= 50 else "✓ Moderate" if x >= 20 else "Low"
    )

    return summary

# ── Analysis 3: Exotic Payout Trends ─────────────────────────────────────────

def analyze_exotic_trends(races, exotics):
    """
    Tracks exotic payout trends over time.
    Shows monthly averages and identifies if payouts are growing/shrinking.
    """
    print("Analyzing exotic payout trends...")

    ex = exotics.copy()
    ex["race_date"] = pd.to_datetime(ex["race_date"])
    ex["month"]     = ex["race_date"].dt.strftime("%Y-%m")
    ex["week"]      = ex["race_date"].dt.strftime("%Y-W%U")

    # Monthly averages by wager type
    monthly = ex[ex["wager_type"].isin(["DD","P3","P4","P5"])].groupby(
        ["month","wager_type"]
    )["payout"].agg(["mean","max","count"]).reset_index()
    monthly.columns = ["Month","Wager","Avg Payout $","Max Payout $","# Payouts"]
    monthly = monthly.round(2).sort_values(["Month","Wager"])

    # Overall stats per wager type
    overall = ex[ex["wager_type"].isin(["DD","P3","P4","P5","P6"])].groupby(
        "wager_type"
    ).agg(
        Total_Payouts = ("payout","count"),
        Avg_Payout    = ("payout","mean"),
        Median_Payout = ("payout","median"),
        Max_Payout    = ("payout","max"),
        Min_Payout    = ("payout","min"),
        Pct_Over_50   = ("payout", lambda x: round((x >= 50).mean() * 100, 1)),
        Pct_Over_100  = ("payout", lambda x: round((x >= 100).mean() * 100, 1)),
        Pct_Over_500  = ("payout", lambda x: round((x >= 500).mean() * 100, 1)),
    ).reset_index().round(2)
    overall.columns = [
        "Wager","Total Hits","Avg $","Median $","Max $","Min $",
        "% Over $50","% Over $100","% Over $500"
    ]
    overall = overall.sort_values("Wager")

    return monthly, overall

# ── Build Combined Analysis Sheet ────────────────────────────────────────────

def build_analysis_sheet(sheet, races, exotics):
    print("\nBuilding analysis tabs...")

    # ── Tab 1: Track Condition ──
    cond_wins, exotic_by_surface = analyze_track_conditions(races, exotics)

    # Combine both tables into one sheet with labels
    spacer = pd.DataFrame([[""] * len(cond_wins.columns)], columns=cond_wins.columns)
    label_row = pd.DataFrame(
        [["── EXOTIC PAYOUTS BY SURFACE (DD/P3/P4/P5) ──"] + [""] * (len(cond_wins.columns)-1)],
        columns=cond_wins.columns
    )
    exotic_renamed = exotic_by_surface.reindex(columns=cond_wins.columns, fill_value="")
    combined_cond = pd.concat([cond_wins, spacer, label_row, exotic_renamed], ignore_index=True)
    write_tab(sheet, "📊 Track Conditions", combined_cond,
              note="Track Condition Impact on Win & Exotic Payouts")

    # ── Tab 2: Pick Value ──
    pick_summary = analyze_pick_value(races, exotics)
    write_tab(sheet, "📊 Pick 3-4-5 Value", pick_summary,
              note="Best Race Sequences for Pick 3/4/5 Value (sorted by wager type)")

    # ── Tab 3: Exotic Trends ──
    monthly, overall = analyze_exotic_trends(races, exotics)
    spacer2 = pd.DataFrame([[""] * len(overall.columns)], columns=overall.columns)
    label2  = pd.DataFrame(
        [["── MONTHLY BREAKDOWN ──"] + [""] * (len(overall.columns)-1)],
        columns=overall.columns
    )
    monthly_renamed = monthly.reindex(columns=overall.columns, fill_value="")
    combined_trends = pd.concat([overall, spacer2, label2, monthly_renamed], ignore_index=True)
    write_tab(sheet, "📊 Exotic Trends", combined_trends,
              note="Exotic Payout Trends - Overall Stats + Monthly Breakdown")

    print("\n✓ All analysis tabs written to Google Sheets!")


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    races, exotics = load_data()

    if len(races) == 0:
        print("No data found in database. Run HorseRacing.py first to scrape data.")
    else:
        # Show available tracks
        available = sorted(races["track"].unique().tolist())
        print("\nAvailable tracks in database:")
        for i, t in enumerate(available, 1):
            count = len(races[races["track"] == t])
            print(f"  {i}. {t}  ({count} races)")
        print(f"  {len(available)+1}. ALL TRACKS")

        # Ask user
        print("\nEnter track number or track code (e.g. AQU), or press Enter for ALL TRACKS:")
        choice = input("  Your choice: ").strip().upper()

        if choice == "" or choice == str(len(available) + 1) or choice == "ALL":
            selected_track = "ALL"
            tab_prefix = "All Tracks"
        elif choice in available:
            selected_track = choice
            tab_prefix = choice
        else:
            # Try matching by number
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(available):
                    selected_track = available[idx]
                    tab_prefix = selected_track
                else:
                    print("Invalid choice, defaulting to ALL TRACKS.")
                    selected_track = "ALL"
                    tab_prefix = "All Tracks"
            except:
                print("Invalid choice, defaulting to ALL TRACKS.")
                selected_track = "ALL"
                tab_prefix = "All Tracks"

        # Filter data
        if selected_track == "ALL":
            filtered_races   = races
            filtered_exotics = exotics
            print("\nRunning analysis for ALL TRACKS...")
        else:
            filtered_races   = races[races["track"] == selected_track]
            filtered_exotics = exotics[exotics["track"] == selected_track]
            print(f"\nRunning analysis for {selected_track} ({len(filtered_races)} races)...")

        sheet = get_gsheet()
        build_analysis_sheet(sheet, filtered_races, filtered_exotics)
