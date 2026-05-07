"""
Horse Racing Date Picker GUI
Supports individual date picking AND date ranges.
Requires: pip install tkcalendar
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from tkcalendar import Calendar
from datetime import datetime, timedelta
import threading
import sqlite3
import sys
import os
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from HorseRacing import scrape_date_range
from HorseRacing import create_driver
from ScratchWatcher import detect_new_scratches, add_ae_manual, check_driver_health, push_dashboard_to_github
from scrape_entries import scrape_entries_day, save_entries, init_entries_tables, DB_PATH as _ENTRIES_DB_PATH
from export_dashboard_data import export as export_dashboard

TRACKS = [
    "AQU", "BEL", "SAR",
    "GP",  "TAM", "PBD",
    "SA",  "DMR", "GG",
    "CD",  "KEE", "TP",
    "HAW", "AP",
    "PRX", "PEN",
    "LRL", "PIM",
]

class HorseRacingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Horse Racing Scraper")
        screen_h = root.winfo_screenheight()
        screen_w = root.winfo_screenwidth()
        win_h = min(750, screen_h - 80)
        win_w = min(900, screen_w - 40)
        self.root.geometry(f"{win_w}x{win_h}+20+20")
        self.root.resizable(True, True)
        self.root.minsize(600, 500)
        self.selected_dates = set()
        self.range_start = None
        self._watch_active     = False
        self._watch_timer      = None
        self._watch_driver     = None   # persistent browser for Watch Mode
        self._watch_first_poll = False  # True on the first poll after Start
        self.build_ui()

    def build_ui(self):
        tk.Label(self.root, text="Horse Racing Results Scraper",
                 font=("Arial", 16, "bold")).pack(pady=8)

        # ── Track selector ──
        track_frame = tk.Frame(self.root)
        track_frame.pack(pady=3)
        tk.Label(track_frame, text="Track:", font=("Arial", 11)).pack(side=tk.LEFT, padx=5)
        self.track_var = tk.StringVar(value="AQU")
        ttk.Combobox(track_frame, textvariable=self.track_var,
                     values=TRACKS, width=8, font=("Arial", 11)).pack(side=tk.LEFT)

        # ── Mode toggle ──
        mode_frame = tk.Frame(self.root)
        mode_frame.pack(pady=3)
        tk.Label(mode_frame, text="Selection Mode:", font=("Arial", 11)).pack(side=tk.LEFT, padx=5)
        self.mode_var = tk.StringVar(value="individual")
        tk.Radiobutton(mode_frame, text="Individual Dates", variable=self.mode_var,
                       value="individual", font=("Arial", 10),
                       command=self.on_mode_change).pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(mode_frame, text="Date Range", variable=self.mode_var,
                       value="range", font=("Arial", 10),
                       command=self.on_mode_change).pack(side=tk.LEFT, padx=5)

        # ── Calendar ──
        self.cal_label = tk.Label(self.root, text="Click dates to select (click again to deselect):",
                                  font=("Arial", 10))
        self.cal_label.pack()
        self.cal = Calendar(self.root, selectmode="day",
                            year=datetime.now().year,
                            month=datetime.now().month,
                            day=datetime.now().day,
                            date_pattern="mm/dd/yy",
                            font=("Arial", 10),
                            showweeknumbers=False)
        self.cal.pack(pady=3)
        self.cal.bind("<<CalendarSelected>>", self.on_date_click)

        # ── Range status label ──
        self.range_label = tk.Label(self.root, text="", font=("Arial", 10), fg="#2a7a2a")
        self.range_label.pack()

        # ── Selected dates display ──
        tk.Label(self.root, text="Selected Dates:", font=("Arial", 11, "bold")).pack()
        self.dates_listbox = tk.Listbox(self.root, height=4, width=45, font=("Arial", 10))
        self.dates_listbox.pack(pady=3)

        # ── Buttons ──
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=5)
        tk.Button(btn_frame, text="Clear All", width=12,
                  command=self.clear_dates, bg="#cc4444", fg="white",
                  font=("Arial", 10)).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="📋  Scrape Entries", width=16,
                  command=self.scrape_entries, bg="#2a4a8a", fg="white",
                  font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="▶  Run Scraper", width=14,
                  command=self.run_scraper, bg="#2a7a2a", fg="white",
                  font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=5)

        # ── Watch Mode ──
        tk.Label(self.root, text="── Watch Mode ──",
                 font=("Arial", 10, "bold")).pack(pady=(8, 0))

        watch_row1 = tk.Frame(self.root)
        watch_row1.pack()
        tk.Label(watch_row1, text="Interval:", font=("Arial", 10)).pack(side=tk.LEFT, padx=4)
        self.interval_var = tk.StringVar(value="15 min")
        ttk.Combobox(watch_row1, textvariable=self.interval_var,
                     values=["15 min", "30 min", "60 min"],
                     width=8, font=("Arial", 10), state="readonly").pack(side=tk.LEFT)

        watch_row2 = tk.Frame(self.root)
        watch_row2.pack(pady=3)
        self.watch_btn = tk.Button(watch_row2, text="▶  Start Watching", width=18,
                                   command=self.toggle_watch,
                                   bg="#2a7a2a", fg="white",
                                   font=("Arial", 10, "bold"))
        self.watch_btn.pack()

        # ── Manual AE Entry ──
        tk.Label(self.root, text="── Manual AE Entry ──",
                 font=("Arial", 10, "bold")).pack(pady=(6, 0))

        ae_frame = tk.Frame(self.root)
        ae_frame.pack(pady=3)
        tk.Label(ae_frame, text="Manual AE:", font=("Arial", 10)).pack(side=tk.LEFT, padx=4)
        tk.Label(ae_frame, text="Race #", font=("Arial", 9)).pack(side=tk.LEFT)
        self.ae_race = tk.Entry(ae_frame, width=4, font=("Arial", 10))
        self.ae_race.pack(side=tk.LEFT, padx=2)
        tk.Label(ae_frame, text="Pgm #", font=("Arial", 9)).pack(side=tk.LEFT)
        self.ae_pgm = tk.Entry(ae_frame, width=4, font=("Arial", 10))
        self.ae_pgm.pack(side=tk.LEFT, padx=2)
        tk.Label(ae_frame, text="Horse Name", font=("Arial", 9)).pack(side=tk.LEFT)
        self.ae_name = tk.Entry(ae_frame, width=20, font=("Arial", 10))
        self.ae_name.pack(side=tk.LEFT, padx=2)
        tk.Button(ae_frame, text="Add AE", command=self.add_ae_entry,
                  bg="#1a5a9a", fg="white", font=("Arial", 10)).pack(side=tk.LEFT, padx=4)

        # ── Output log ──
        tk.Label(self.root, text="Output:", font=("Arial", 11, "bold")).pack()
        self.log = scrolledtext.ScrolledText(self.root, height=8, width=70, font=("Courier", 9),
                                             bg="#1e1e1e", fg="#00ff88", state=tk.DISABLED,
                                             wrap=tk.WORD)
        self.log.pack(pady=5, fill=tk.BOTH, expand=True)

    def on_mode_change(self):
        self.selected_dates = set()
        self.range_start = None
        self.range_label.config(text="")
        self.refresh_listbox()
        if self.mode_var.get() == "range":
            self.cal_label.config(text="Click START date, then END date of range:")
        else:
            self.cal_label.config(text="Click dates to select (click again to deselect):")

    def on_date_click(self, event=None):
        selected = self.cal.get_date()  # MM/DD/YY
        if self.mode_var.get() == "individual":
            if selected in self.selected_dates:
                self.selected_dates.discard(selected)
                self.log_msg(f"Removed: {selected}")
            else:
                self.selected_dates.add(selected)
                self.log_msg(f"Added: {selected}")
        else:
            # Range mode
            if self.range_start is None:
                self.range_start = selected
                self.range_label.config(text=f"Start: {selected}  →  now click END date")
                self.log_msg(f"Range start: {selected}")
            else:
                end = selected
                self.range_label.config(text=f"Range: {self.range_start}  →  {end}")
                self.log_msg(f"Range end: {end}")
                self.fill_date_range(self.range_start, end)
                self.range_start = None

        self.refresh_listbox()

    def fill_date_range(self, start_str, end_str):
        try:
            start = datetime.strptime(start_str, "%m/%d/%y")
            end   = datetime.strptime(end_str,   "%m/%d/%y")
            if end < start:
                start, end = end, start
            self.selected_dates = set()
            current = start
            while current <= end:
                self.selected_dates.add(current.strftime("%m/%d/%y"))
                current += timedelta(days=1)
            self.log_msg(f"Selected {len(self.selected_dates)} dates in range.")
        except Exception as e:
            self.log_msg(f"Error setting range: {e}")

    def refresh_listbox(self):
        self.dates_listbox.delete(0, tk.END)
        for d in sorted(self.selected_dates):
            try:
                dt = datetime.strptime(d, "%m/%d/%y")
                display = dt.strftime("%a, %b %d %Y")
            except:
                display = d
            self.dates_listbox.insert(tk.END, display)
        count = len(self.selected_dates)
        self.dates_listbox.insert(tk.END, f"── {count} date(s) selected ──")

    def clear_dates(self):
        self.selected_dates = set()
        self.range_start = None
        self.range_label.config(text="")
        self.refresh_listbox()
        self.log_msg("All dates cleared.")

    def log_msg(self, msg):
        self.log.config(state=tk.NORMAL)
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)
        self.log.config(state=tk.DISABLED)

    def _current_watch_target(self):
        """Return (track, date_str YYYY-MM-DD) from the current UI selectors."""
        track = self.track_var.get().strip().upper()
        date_str = datetime.now().strftime("%Y-%m-%d")
        # Use the most recently selected date if exactly one is chosen
        if len(self.selected_dates) == 1:
            d = next(iter(self.selected_dates))
            try:
                date_str = datetime.strptime(d, "%m/%d/%y").strftime("%Y-%m-%d")
            except ValueError:
                pass
        return track, date_str

    def toggle_watch(self):
        if not self._watch_active:
            self._watch_active     = True
            self._watch_first_poll = True
            self._watch_driver     = create_driver()
            self.watch_btn.config(text="■  Stop Watching", bg="#cc4444")
            track, date_str = self._current_watch_target()
            self.log_msg(f"\nWatch Mode started: {track} {date_str}")
            self.log_msg("INFO: AE additions are not auto-detected. "
                         "Use Manual AE panel if a horse is added to the field.")
            self._schedule_watch(track, date_str, first=True)
        else:
            self._stop_watch()

    def _stop_watch(self):
        self._watch_active = False
        if self._watch_timer is not None:
            self.root.after_cancel(self._watch_timer)
            self._watch_timer = None
        self.watch_btn.config(text="▶  Start Watching", bg="#2a7a2a")
        self.log_msg("Watch Mode stopped.")
        threading.Thread(target=self._quit_watch_driver, daemon=True).start()

    def _quit_watch_driver(self):
        """Close the persistent Watch Mode browser on a background thread."""
        drv = self._watch_driver
        self._watch_driver = None
        if drv is not None:
            try:
                drv.quit()
            except Exception:
                pass

    def _schedule_watch(self, track, date_str, first=False):
        if not self._watch_active:
            return
        if first:
            delay_ms = 0
        else:
            minutes = int(self.interval_var.get().split()[0])
            delay_ms = minutes * 60 * 1000
        self._watch_timer = self.root.after(delay_ms, self._run_watch_poll, track, date_str)

    def _run_watch_poll(self, track, date_str):
        if not self._watch_active:
            return

        # Capture warmup flag for this poll and immediately clear it so
        # subsequent polls skip the 12-second Incapsula warm-up.
        needs_warmup = self._watch_first_poll
        self._watch_first_poll = False

        # The entire poll (health check + browser fetch + ~20 s of waits) runs
        # on a background thread so the GUI stays fully responsive.
        def poll_thread():
            # ── Driver health check ───────────────────────────────────────────
            drv = self._watch_driver
            if not check_driver_health(drv):
                self.root.after(0, self.log_msg, "⚠ Browser restarted")
                try:
                    if drv is not None:
                        drv.quit()
                except Exception:
                    pass
                self._watch_driver = create_driver()
                drv = self._watch_driver
                # Restarted driver always needs a warm-up
                nonlocal needs_warmup
                needs_warmup = True

            # ── Scrape ───────────────────────────────────────────────────────
            try:
                new = detect_new_scratches(track, date_str,
                                           driver=drv, warmup=needs_warmup)
            except Exception as e:
                self.root.after(0, self.log_msg, f"Watch error: {e}")
                new = []

            if not self._watch_active:
                return

            # ── Log results ──────────────────────────────────────────────────
            has_scratch = False
            if new:
                for e in new:
                    if e["change_type"] == "AE_ADDED":
                        icon = "✚ AE ADDED"
                    else:
                        icon = "⚠ SCRATCH "
                        has_scratch = True
                    self.root.after(0, self.log_msg,
                        f"{icon} — Race {e['race_num']} #{e['pgm']} {e['horse_name']}"
                        f" — {e['reason']} [{e['time_posted']}]")
            else:
                now_str = datetime.now().strftime("%I:%M %p")
                self.root.after(0, self.log_msg,
                    f"[OK] [{now_str}] No new scratches at {track}")

            # ── Visual alert for real scratches ───────────────────────────────
            if has_scratch:
                self.root.after(0, self._flash_scratch_alert)

            # ── Schedule next poll ────────────────────────────────────────────
            if self._watch_active:
                self.root.after(0, self._schedule_watch, track, date_str)

        threading.Thread(target=poll_thread, daemon=True).start()

    def _flash_scratch_alert(self):
        """Flash the log background red and ring the bell on a real scratch."""
        self.root.bell()
        self.log.config(bg="#3a0000")
        self.root.after(3000, lambda: self.log.config(bg="#1e1e1e"))

    def add_ae_entry(self):
        track, date_str = self._current_watch_target()
        race_raw  = self.ae_race.get().strip()
        pgm_raw   = self.ae_pgm.get().strip()
        horse_raw = self.ae_name.get().strip()

        if not race_raw or not pgm_raw or not horse_raw:
            messagebox.showwarning("Missing Fields", "Race #, Pgm #, and Horse Name are all required.")
            return
        try:
            race_num = int(race_raw)
        except ValueError:
            messagebox.showwarning("Invalid Race #", "Race # must be a number.")
            return

        try:
            inserted = add_ae_manual(track, date_str, race_num, pgm_raw, horse_raw)
        except Exception as e:
            self.log_msg(f"AE entry error: {e}")
            return

        if inserted:
            self.log_msg(f"✚ AE logged — Race {race_num} #{pgm_raw} {horse_raw}")
        else:
            self.log_msg(f"Already recorded: Race {race_num} #{pgm_raw} {horse_raw}")

        self.ae_race.delete(0, tk.END)
        self.ae_pgm.delete(0, tk.END)
        self.ae_name.delete(0, tk.END)

    def scrape_entries(self):
        if not self.selected_dates:
            messagebox.showwarning("No Dates", "Please select at least one date.")
            return
        track = self.track_var.get().strip().upper()
        if not track:
            messagebox.showwarning("No Track", "Please select a track.")
            return

        date_strs = []
        for d in sorted(self.selected_dates):
            try:
                dt = datetime.strptime(d, "%m/%d/%y")
                date_strs.append(dt.strftime("%Y-%m-%d"))
            except Exception:
                self.log_msg(f"Skipping invalid date: {d}")

        if not date_strs:
            return

        self.log_msg(f"\nScraping entries: {track} | {len(date_strs)} date(s)")
        self.log_msg("-" * 40)

        def netlify_deploy():
            try:
                result = subprocess.run(
                    [
                        'netlify', 'deploy',
                        '--site', 'b4f839c0-9763-430b-aabb-d0bfe8db072c',
                        '--dir', 'web',
                        '--prod'
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    cwd='C:/Users/jason/Desktop/HorseRacing Project'
                )
                if result.returncode == 0:
                    return 'Netlify deploy successful'
                else:
                    return 'Netlify deploy failed: ' + result.stderr
            except subprocess.TimeoutExpired:
                return 'Netlify deploy timed out after 120s'
            except Exception as e:
                return 'Netlify deploy error: ' + str(e)

        def entries_thread():
            class LogRedirect:
                def __init__(self, app):
                    self.app = app
                def write(self, msg):
                    if msg.strip():
                        self.app.root.after(0, self.app.log_msg, msg.rstrip())
                def flush(self):
                    pass

            old_stdout = sys.stdout
            sys.stdout = LogRedirect(self)
            try:
                self.log_msg("Step 1/4: Scraping entries...")
                conn = sqlite3.connect(_ENTRIES_DB_PATH)
                init_entries_tables(conn)
                total_races = total_horses = 0
                for date_str in date_strs:
                    races = scrape_entries_day(date_str, track)
                    if races:
                        ins_r, ins_h, _ = save_entries(conn, track, date_str, races)
                        total_races  += ins_r
                        total_horses += ins_h
                        self.log_msg(
                            f"✓ Entries scraped for {track} {date_str}"
                            f" — {ins_r} race(s), {ins_h} horse(s)"
                        )
                    else:
                        self.log_msg(f"  No entries found for {track} {date_str}")
                conn.close()
                self.log_msg("\nStep 2/4: Exporting dashboard data...")
                export_dashboard()
                self.log_msg("Step 3/4: Pushing to GitHub...")
                push_dashboard_to_github()
                self.log_msg("Step 4/4: Deploying to Netlify...")
                deploy_msg = netlify_deploy()
                self.log_msg(deploy_msg)
                self.log_msg(
                    f"\n✓ All done — site is live."
                    f" {total_races} race(s), {total_horses} horse(s) saved."
                )
            except Exception as e:
                self.log_msg(f"\n✗ Entries error: {e}")
            finally:
                sys.stdout = old_stdout

        threading.Thread(target=entries_thread, daemon=True).start()

    def run_scraper(self):
        if not self.selected_dates:
            messagebox.showwarning("No Dates", "Please select at least one date.")
            return
        track = self.track_var.get().strip().upper()
        if not track:
            messagebox.showwarning("No Track", "Please select a track.")
            return

        date_codes = []
        for d in sorted(self.selected_dates):
            try:
                dt = datetime.strptime(d, "%m/%d/%y")
                date_codes.append(dt.strftime("%m%d%y"))
            except:
                self.log_msg(f"Skipping invalid date: {d}")

        self.log_msg(f"\nStarting: {track} | {len(date_codes)} date(s)")
        self.log_msg("-" * 40)

        def scrape_thread():
            class LogRedirect:
                def __init__(self, app):
                    self.app = app
                def write(self, msg):
                    if msg.strip():
                        self.app.root.after(0, self.app.log_msg, msg.rstrip())
                def flush(self):
                    pass

            old_stdout = sys.stdout
            sys.stdout = LogRedirect(self)
            try:
                scrape_date_range(track_code=track, dates=date_codes)
                self.log_msg("\n✓ Done! Check your Google Sheet.")
            except Exception as e:
                self.log_msg(f"\n✗ Error: {e}")
            finally:
                sys.stdout = old_stdout

        threading.Thread(target=scrape_thread, daemon=True).start()


if __name__ == "__main__":
    root = tk.Tk()
    app = HorseRacingApp(root)
    root.mainloop()
