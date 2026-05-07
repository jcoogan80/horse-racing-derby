"""
generate_guide_pdf.py — Regenerate Derby_Value_Complete_Guide.pdf
Run: python generate_guide_pdf.py
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import os

OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Derby_Value_Complete_Guide.pdf")

# ── Styles ────────────────────────────────────────────────────────────────────

def build_styles():
    base = getSampleStyleSheet()
    s = {}

    s['title'] = ParagraphStyle('title',
        fontSize=28, fontName='Helvetica-Bold',
        alignment=TA_CENTER, spaceAfter=12,
        textColor=colors.HexColor('#1a1a2e'))

    s['subtitle'] = ParagraphStyle('subtitle',
        fontSize=14, fontName='Helvetica',
        alignment=TA_CENTER, spaceAfter=6,
        textColor=colors.HexColor('#333333'))

    s['meta'] = ParagraphStyle('meta',
        fontSize=10, fontName='Helvetica',
        alignment=TA_CENTER, spaceAfter=4,
        textColor=colors.HexColor('#555555'))

    s['h1'] = ParagraphStyle('h1',
        fontSize=16, fontName='Helvetica-Bold',
        spaceBefore=14, spaceAfter=6,
        textColor=colors.HexColor('#1a1a2e'),
        borderPad=2)

    s['h2'] = ParagraphStyle('h2',
        fontSize=12, fontName='Helvetica-Bold',
        spaceBefore=10, spaceAfter=4,
        textColor=colors.HexColor('#2c3e6b'))

    s['body'] = ParagraphStyle('body',
        fontSize=9.5, fontName='Helvetica',
        spaceAfter=5, leading=14)

    s['bullet'] = ParagraphStyle('bullet',
        fontSize=9.5, fontName='Helvetica',
        leftIndent=16, spaceAfter=3, leading=13,
        bulletIndent=6)

    s['note'] = ParagraphStyle('note',
        fontSize=8.5, fontName='Helvetica-Oblique',
        spaceAfter=4, leading=12,
        textColor=colors.HexColor('#555555'))

    s['footer'] = ParagraphStyle('footer',
        fontSize=8, fontName='Helvetica',
        alignment=TA_CENTER,
        textColor=colors.HexColor('#888888'))

    s['toc_section'] = ParagraphStyle('toc_section',
        fontSize=10, fontName='Helvetica',
        spaceAfter=3, leading=14)

    s['rule'] = ParagraphStyle('rule',
        fontSize=10.5, fontName='Helvetica-Bold',
        spaceAfter=2, spaceBefore=6,
        textColor=colors.HexColor('#1a1a2e'))

    s['callout'] = ParagraphStyle('callout',
        fontSize=9, fontName='Helvetica-Oblique',
        leftIndent=12, spaceAfter=4, leading=13,
        textColor=colors.HexColor('#333333'))

    return s


# ── Table helpers ─────────────────────────────────────────────────────────────

HEADER_BG  = colors.HexColor('#1a1a2e')
HEADER_FG  = colors.white
ROW_ALT    = colors.HexColor('#f0f2f8')
GRID_COLOR = colors.HexColor('#cccccc')

def styled_table(data, col_widths, header_rows=1):
    t = Table(data, colWidths=col_widths)
    style = [
        ('FONTNAME',    (0, 0), (-1, header_rows - 1), 'Helvetica-Bold'),
        ('FONTSIZE',    (0, 0), (-1, -1), 8.5),
        ('BACKGROUND',  (0, 0), (-1, header_rows - 1), HEADER_BG),
        ('TEXTCOLOR',   (0, 0), (-1, header_rows - 1), HEADER_FG),
        ('ALIGN',       (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN',      (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID',        (0, 0), (-1, -1), 0.4, GRID_COLOR),
        ('ROWBACKGROUNDS', (0, header_rows), (-1, -1), [colors.white, ROW_ALT]),
        ('TOPPADDING',  (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 3),
    ]
    t.setStyle(TableStyle(style))
    return t


# ── Content builder ───────────────────────────────────────────────────────────

def build_story(s):
    story = []
    W = 6.5 * inch  # usable width

    def h(text, style='h1'):
        story.append(Paragraph(text, s[style]))

    def p(text):
        story.append(Paragraph(text, s['body']))

    def note(text):
        story.append(Paragraph(text, s['note']))

    def bullets(items):
        for item in items:
            story.append(Paragraph(f'• {item}', s['bullet']))

    def sp(n=6):
        story.append(Spacer(1, n))

    def rule():
        story.append(HRFlowable(width='100%', thickness=0.5,
                                color=colors.HexColor('#cccccc'), spaceAfter=6))

    # ── PAGE 1 — Title ────────────────────────────────────────────────────────
    story.append(Spacer(1, 1.2 * inch))
    story.append(Paragraph('DERBY VALUE', s['title']))
    story.append(Paragraph('Horse Racing Analytics Platform', s['subtitle']))
    story.append(Spacer(1, 0.15 * inch))
    story.append(Paragraph('Complete Project Guide | April 2026', s['meta']))
    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph('Live Site: horse-racing-derby.netlify.app', s['meta']))
    story.append(Paragraph('GitHub: github.com/jcoogan80/horse-racing-derby', s['meta']))
    story.append(Spacer(1, 0.4 * inch))
    story.append(HRFlowable(width='80%', thickness=1,
                             color=colors.HexColor('#1a1a2e'),
                             hAlign='CENTER', spaceAfter=16))
    story.append(Paragraph(
        'Derby Value is a horse racing analytics platform built from scratch using Claude Code. '
        'It scrapes race results and exotic wager payouts from multiple sources, stores them in a '
        'local SQLite database, runs statistical analysis to find mispriced wager sequences, and '
        'provides a suite of live tools for Derby day decision-making — all accessible from a '
        'mobile-optimized web app at horse-racing-derby.netlify.app.',
        s['body']))
    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph(
        'This document covers everything: what was built, how to use each tool, the complete '
        'analytical findings from 18,446 exotic payouts across 7 tracks, and the Derby day '
        'playbook derived from the data.',
        s['body']))
    story.append(Spacer(1, 0.5 * inch))
    story.append(Paragraph(
        'Built with Claude Code | April 2026 | The Kentucky Derby is May 3, 2026',
        s['footer']))
    story.append(PageBreak())

    # ── PAGE 2 — Table of Contents ────────────────────────────────────────────
    h('Table of Contents')
    rule()
    toc_data = [
        ['1.', 'The Database', 'What data we have, where it came from, how it is structured'],
        ['2.', 'The Web App', 'Six tabs, what each does, how to navigate on Derby day'],
        ['3.', 'Python Tools Reference', 'Command-line tools and what they produce'],
        ['4.', 'The Data Pipeline', 'How to scrape, export, and push updates'],
        ['5.', 'Overlay Detection Engine', 'How it works and what it found'],
        ['6.', 'Parlay vs Exotic Analysis', 'The corrected findings across all 7 tracks'],
        ['7.', 'Longshot Threshold Analysis', 'At what odds does the exotic start winning'],
        ['8.', 'Will-Pay Estimator', 'Live payout estimation during a sequence'],
        ['9.', 'Morning Line Overlay Detector', 'Pre-race go/no-go signal'],
        ['10.', 'Key Analytical Findings', 'The rules that emerged from 18,446 data points'],
        ['11.', 'Derby Day Playbook', 'Minute-by-minute guide for May 3'],
        ['12.', 'Track-by-Track Reference', 'Complete summary for all 7 tracks'],
    ]
    for row in toc_data:
        story.append(Paragraph(
            f'<b>{row[0]}</b>  <b>{row[1]}</b> — {row[2]}',
            s['toc_section']))
    story.append(PageBreak())

    # ── PAGE 3 — The Database ─────────────────────────────────────────────────
    h('1. The Database')
    p('The foundation of Derby Value is a SQLite database — horse_racing.db — stored locally at '
      'C:\\Users\\jason\\Desktop\\HorseRacing Project\\horse_racing.db. It contains two primary '
      'tables: race_results and exotic_payouts.')
    sp()
    h('What Is In the Database', 'h2')
    db_data = [
        ['Track', 'Full Name', 'Races', 'Exotics', 'Date Range'],
        ['CD', 'Churchill Downs', '417', '2,200', 'Apr 2025–Apr 2026'],
        ['GP', 'Gulfstream Park', '~894', '~4,841', 'Dec 2025–Apr 2026'],
        ['FG', 'Fair Grounds', '473', '2,504', 'Jan–Mar 2025'],
        ['OP', 'Oaklawn Park', '490', '2,541', 'Jan–May 2025'],
        ['AQU', 'Aqueduct', '~562', '~3,088', 'Jan–Apr 2025'],
        ['SA', 'Santa Anita', '~459', '~2,516', 'Jan–Apr 2025'],
        ['KEE', 'Keeneland', '115', '633', 'Apr 2025–Apr 2026'],
        ['TOTAL', '', '3,476', '18,446', 'Jan 2025–Apr 2026'],
    ]
    story.append(styled_table(db_data,
        [0.6*inch, 1.5*inch, 0.7*inch, 0.7*inch, 1.5*inch]))
    sp(8)
    h('race_results Table — Key Columns', 'h2')
    p('Each row is one race. Columns include: track, race_date, race_num, winner, win_payout (per $2), '
      'place_payout, show_payout, race_type, distance, surface, track_condition, purse, field_size, '
      'winning_time, winner_morning_line, implied_prob.')
    sp()
    h('exotic_payouts Table — Key Columns', 'h2')
    p('Each row is one exotic payout. Columns include: track, race_date, race_num, wager_type '
      '(DD/P3/P4/P5/P6/EX/TRI/SF), race_span (e.g. \'5-8\'), winning_combination, payout (as posted), '
      'wager_base (minimum wager amount), payout_per_2 (normalized to $2 basis).')
    note('The wager_base and payout_per_2 columns were added after discovering that exotic payouts are '
         'quoted on varying minimum wager amounts — $0.50 for Pick 3/4/5, $0.20 for Pick 6, $2.00 for '
         'Daily Double. All analysis uses payout_per_2 to ensure fair comparisons.')
    sp()
    h('Where the Data Came From', 'h2')
    bullets([
        'Equibase (via Selenium scraper) — original data for AQU, GP, KEE, SA through April 2026. '
        'Bot protection limits Equibase to the last 4-6 weeks of history.',
        'Horse Racing Nation (via requests/BeautifulSoup scraper) — HorseRacingHRN.py pulls historical '
        'results from entries.horseracingnation.com for any track going back years. Used to load '
        'CD 2025 spring/fall meet, FG, OP, and extended GP/AQU/SA history.',
    ])
    story.append(PageBreak())

    # ── PAGE 4 — The Web App ──────────────────────────────────────────────────
    h('2. The Web App')
    p('The web app lives at horse-racing-derby.netlify.app and is the primary tool for Derby day. '
      'It is a pure HTML/CSS/JavaScript single-page application with no external dependencies. '
      'A service worker caches the app after first load so it works fully offline — critical at '
      'Churchill Downs on Derby day where cell service with 150,000 people is unreliable.')
    sp()
    p('The app has six tabs. Here is what each one does and when to use it:')
    sp(4)
    tab_data = [
        ['Tab', 'Use When', 'What It Shows'],
        ['Dashboard', 'After each scrape',
         'Shows DB stats, overlay sequences by track color-coded HIGH/MODERATE/LOTTERY. '
         'Quick scan of what sequences are worth targeting.'],
        ['Ticket Builder', 'Night before',
         'Select track, exotic type, starting race. Shows historical avg payout, median, '
         'hit count, overlay rating. Also contains the Will-Pay Estimator section.'],
        ['Today\'s Card', 'Race morning',
         'Enter morning line odds for your horses in each leg. Generates LONGSHOT SETUP / '
         'NEUTRAL / CHALK ALERT signal by comparing theoretical parlay to historical average.'],
        ['Hedge Calc', 'During the race',
         'Enter ticket cost, estimated payout, field size, horse odds. Calculates optimal '
         'hedge amounts. Budget mode allocates a fixed dollar amount proportionally.'],
        ['Parlay Edge', 'Reference',
         'Shows parlay vs exotic ratio by track and wager type. Includes longshot threshold '
         'table. Day-by-day detail collapsible.'],
        ['Profiles', 'Reference',
         'Static baseline overlay data for all tracks. Useful for quick cross-reference '
         'without needing the Python output.'],
    ]
    story.append(styled_table(tab_data,
        [1.0*inch, 1.1*inch, 4.4*inch]))
    sp(10)
    h('Will-Pay Estimator — Inside the Ticket Builder Tab', 'h2')
    p('Below the ticket structure output in the Ticket Builder tab is the Will-Pay Estimator. '
      'When you are alive in a multi-race sequence and the track posts a will-pay, enter:')
    bullets([
        'Which mode — P3 to P4, P3 to P5, or P4 to P5',
        'The current will-pay amount showing on the board',
        'The odds of your horses in the remaining legs',
    ])
    p('The tool uses track-specific historical multipliers derived from actual payout data to '
      'estimate the final payout. Outputs a low estimate (median multiplier), mean estimate, '
      'and high estimate, plus a confidence rating.')
    story.append(PageBreak())

    # ── PAGE 5 — Python Tools ─────────────────────────────────────────────────
    h('3. Python Tools Reference')
    p('All Python tools run from the project folder: C:\\Users\\jason\\Desktop\\HorseRacing Project')
    sp()

    for title, desc, cmds in [
        ('HorseRacingGUI.py — Equibase Scraper',
         'Visual GUI scraper that opens Chrome and navigates Equibase chart pages. '
         'Use this for scraping current meet data as results post (within the last 4-6 weeks).',
         ['python HorseRacingGUI.py']),
        ('HorseRacingHRN.py — Historical Scraper',
         'Scrapes historical results from Horse Racing Nation. No login required. '
         'Supports any track with a 1-2 second delay between requests. '
         'Skip-if-exists logic prevents duplicates.',
         [
             'python HorseRacingHRN.py 2025-05-01          # single day, defaults to CD',
             'python HorseRacingHRN.py spring2025           # CD spring meet Apr-Jun 2025',
             'python HorseRacingHRN.py fall2025             # CD fall meet Oct-Nov 2025',
             'python HorseRacingHRN.py --track GP 2025-12-01 2026-03-31',
             'python HorseRacingHRN.py --track FG spring2025',
             'python HorseRacingHRN.py --list-tracks',
             'python HorseRacingHRN.py 2025-05-01 --dry-run',
             'Supported: CD, GP, FG, OP, SA, AQU, KEE, PIM, BEL, TAM, TUP, MVR',
         ]),
        ('derby_value.py — Analytics Engine',
         'The core analysis engine. Reads from horse_racing.db and produces overlay detection, '
         'parlay comparison, will-pay multipliers, and longshot threshold reports.',
         [
             'python derby_value.py                  # full overlay report all tracks',
             'python derby_value.py CD               # overlay report for one track',
             'python derby_value.py profile CD       # consolidated profile with top overlays',
             'python derby_value.py parlay CD        # parlay vs exotic comparison',
             'python derby_value.py willpay CD       # P3/P4/P5 multiplier analysis',
             'python derby_value.py threshold CD     # longshot threshold analysis',
         ]),
        ('export_dashboard_data.py — JSON Export',
         'Exports the full database analysis to web/dashboard_data.json which the web app reads. '
         'Run this after every scrape session before pushing to GitHub.',
         [
             'python export_dashboard_data.py        # export all tracks',
             'python export_dashboard_data.py CD     # export only CD',
         ]),
        ('scrape_entries.py — Morning Entries Scraper',
         'Scrapes morning line entries from entries.horseracingnation.com. Detects also-eligible '
         '(AE) horses that drew in via scratch. Run each morning before first post.',
         [
             'python scrape_entries.py               # today, all configured tracks',
             'python scrape_entries.py CD            # today, CD only',
             'python scrape_entries.py CD 2026-05-03 # specific date + track',
             'run_morning_entries.bat                # scheduled task: scrapes today, all tracks',
         ]),
        ('hedge_calculator.py — Command Line Hedge Tool',
         'Python version of the hedge calculator. The web app version is more convenient on '
         'Derby day.',
         ['python hedge_calculator.py               # interactive prompt']),
    ]:
        h(title, 'h2')
        p(desc)
        for cmd in cmds:
            story.append(Paragraph(cmd, s['bullet']))
        sp(4)

    sp(6)
    h('The Data Pipeline — After Each Race Day', 'h2')
    for cmd in [
        'python HorseRacingGUI.py      # or HorseRacingHRN.py for historical',
        'python export_dashboard_data.py',
        'cd web',
        'git add dashboard_data.json',
        'git commit -m "update data"',
        'git push',
    ]:
        story.append(Paragraph(cmd, s['bullet']))
    note('Netlify auto-deploys within 60 seconds of the push. The live site updates automatically.')
    story.append(PageBreak())

    # ── PAGE 6 — Overlay Detection ────────────────────────────────────────────
    h('4. Overlay Detection Engine')
    p('The overlay engine is the core analytical function in derby_value.py. It identifies race '
      'sequences where exotic wagers historically overpay relative to the track average — called '
      'overlays. These are the sequences worth targeting because the public is systematically '
      'underpricing them.')
    sp()
    h('How It Works', 'h2')
    bullets([
        'score_sequences(track, wager_type) — ranks all race spans by average payout descending, '
        'computing avg, median, max, and value_score (avg/median ratio) for each span.',
        'find_overlays(track, wager_type) — flags sequences where avg payout exceeds 1.5x the '
        'overall track average for that wager type, with a minimum of 5 hits to qualify.',
        'profile_track(track) — consolidated report across all wager types showing top overlays '
        'with consistency ratings.',
    ])
    sp()
    h('Consistency Ratings', 'h2')
    rating_data = [
        ['Rating', 'Value Score', 'What It Means'],
        ['HIGH', 'Below 3.0',
         'Reliable, consistent overlay. Payouts cluster near the average. Best sequences to target.'],
        ['MODERATE', '3.0 to 10.0',
         'Solid overlay with some variance. Real signal but occasional outliers.'],
        ['LOTTERY', 'Above 10.0',
         'A few massive outliers drive the average. Median is much lower. High variance play.'],
    ]
    story.append(styled_table(rating_data,
        [0.9*inch, 0.9*inch, 4.7*inch]))
    sp(10)
    h('Churchill Downs Overlay Profile — 2025–2026 Season (417 races, 2,200 exotics)', 'h2')
    p('The CD profile is the most important output for Derby day planning. Based on 417 races and '
      '2,200 exotic payouts from the 2025 spring/fall meets and early 2026 spring meet:')
    sp(4)
    cd_overlay = [
        ['Wager', 'Sequence', 'Avg Payout', 'Median', 'Hits', 'Rating', 'Signal'],
        ['P6', 'Races 3–8', '$531,536*', '$200,609*', '7*', 'HIGH*', 'Jackpot-driven — see note'],
        ['P5', 'Races 4–8', '$64,526', '$15,479', '17', 'MODERATE', 'Best risk/reward — primary'],
        ['P3', 'Races 5–7', '$1,387', '$261', '43', 'MODERATE', 'Most reliable sample'],
        ['P4', 'Races 4–7', '$30,532', '$898', '11', 'LOTTERY', 'Selective only'],
        ['DD', 'Races 8–9', '$138', '$45', '35', 'MODERATE', 'Low cost anchor'],
    ]
    story.append(styled_table(cd_overlay,
        [0.55*inch, 0.9*inch, 0.9*inch, 0.75*inch, 0.5*inch, 0.85*inch, 2.05*inch]))
    sp(8)
    note('* P6 data quality warning: The mean ($531K) and median ($200,609) for races 3–8 are '
         'heavily distorted by two carryover jackpot hits — May 15 ($2.57M) and June 8 ($1.07M). '
         '5 of 7 hits (71%) paid between $5K and $241K, making the realistic typical payout far '
         'lower than the headline numbers suggest. This sequence is better characterized as LOTTERY '
         '(high variance, jackpot-driven) than HIGH. The P5 races 4–8 with 17 hits and a $15,479 '
         'median is the more reliable primary target for Derby day.')
    note('Sequences with fewer than 10 hits should be treated with caution regardless of overlay '
         'rating. The P6 (7 hits) and P4 (11 hits) figures above reflect a thin sample; more data '
         'from the 2026 spring meet will improve reliability.')
    story.append(PageBreak())

    # ── PAGE 7 — Parlay vs Exotic ─────────────────────────────────────────────
    h('5. Parlay vs Exotic Analysis')
    p('For every race day in the database, the analysis computes a $2 compounded win parlay through '
      'the last 4, 5, and 6 races using the actual posted win prices of each winner. It then '
      'compares this to the actual exotic payout normalized to $2 equivalent (payout_per_2). '
      'The ratio (exotic / parlay) tells you whether the pool returned more or less than fair '
      'value on that day.')
    sp()
    h('The Critical Wager Base Correction', 'h2')
    p('Exotic payouts on Equibase and HRN are quoted on varying minimum wager bases. Pick 5 payouts '
      'are per $0.50. Pick 6 payouts are per $0.20. Comparing these directly to a $2 parlay produces '
      'completely wrong results. The database stores wager_base and payout_per_2 '
      '(= payout × 2.0 / wager_base) for every exotic record.')
    sp(4)
    base_data = [
        ['Wager', 'Min Wager', 'Multiplier to $2'],
        ['Pick 3/4/5', '$0.50', '4x  (posted $1,000 = $4,000 on $2 basis)'],
        ['Pick 6', '$0.20', '10x  (posted $100,000 = $1,000,000 on $2 basis)'],
        ['Daily Double', '$1.00', '2x'],
        ['Exacta', '$2.00', '1x  (no adjustment)'],
        ['Trifecta', '$0.50', '4x'],
        ['Superfecta', '$0.10', '20x'],
    ]
    story.append(styled_table(base_data,
        [1.2*inch, 1.0*inch, 4.3*inch]))
    sp(10)
    h('Complete Cross-Track Results — Corrected (218 race days, all payout_per_2)', 'h2')
    p('Based on 218 race days across 7 tracks, all using payout_per_2:')
    sp(4)
    parlay_data = [
        ['Track', 'P4 Win%', 'P4 Ratio', 'P5 Win%', 'P5 Ratio', 'P6 Win%', 'P6 Ratio'],
        ['GP',  '98.7%', '1.97x', '97.4%', '2.43x', '90.9%', '3.01x'],
        ['CD',  '93.0%', '1.90x', '97.7%', '2.47x', '88.9%', '3.82x'],
        ['FG',  '94.3%', '1.86x', '100%',  '2.42x', '1.9%',  '0.09x'],
        ['OP',  '93.8%', '2.00x', '93.6%', '2.31x', 'n/a',   'n/a'],
        ['AQU', '75.8%', '1.51x', '98.4%', '2.57x', '11.5%', '0.48x'],
        ['SA',  '86.0%', '1.72x', '90.0%', '3.42x', '18.4%', '0.52x'],
        ['KEE', '83.3%', '1.58x', '33.3%', '0.68x', '50.0%', '5.65x'],
    ]
    story.append(styled_table(parlay_data,
        [0.55*inch, 0.75*inch, 0.75*inch, 0.75*inch, 0.75*inch, 0.75*inch, 0.75*inch]))
    sp(8)
    note('Win% = percentage of race days where the exotic beat the $2 parlay. '
         'Ratio = mean ratio of (exotic payout / parlay payout).')
    note('Three results stand out immediately: FG P6 at 1.9% win rate (avoid completely), '
         'KEE P5 at 33% win rate (the parlay wins — never buy KEE P5 expecting pool value), '
         'and SA P6 at 18.4% win rate (avoid). Everything else is exotic-favorable.')
    note('CD update note: CD P6 win rate moved from 91.4% to 88.9% (-2.5pp) as of Apr 25, 2026 '
         'after adding the 2026 spring meet opener. No metric shifted more than 5 percentage points '
         'from the original baseline. All structural conclusions remain unchanged.')
    story.append(PageBreak())

    # ── PAGE 8 — Key Analytical Findings ─────────────────────────────────────
    h('6. Key Analytical Findings')
    p('After analyzing 18,446 exotic payouts across 7 tracks and 218 race days, the following '
      'findings emerged. These are the rules that the data supports.')
    sp()

    findings = [
        ('Finding 1 — Pool Size Determines Exotic Value',
         'The single most important variable in whether an exotic pool generates value over the '
         'parlay is not the presence of longshots — it is the absolute size of the pool. GP and CD, '
         'the two highest-volume tracks in the dataset, show exotic-favorable results across P4, P5, '
         'and P6. FG and SA, lower-volume tracks, show the exotic destroying value on six-leg bets '
         'despite having similar longshot frequencies.',
         [
             'GP P6: 90.9% exotic win rate, 3.01x mean ratio',
             'CD P6: 88.9% exotic win rate, 3.82x mean ratio',
             'FG P6: 1.9% exotic win rate, 0.09x mean ratio',
             'SA P6: 18.4% exotic win rate, 0.52x mean ratio',
         ]),
        ('Finding 2 — The KEE P5 Anomaly',
         'Keeneland Pick 5 is the most striking outlier in the entire dataset. Even after normalizing '
         'to the $0.50 base (4x multiplier), the parlay beats the exotic 67% of the time with a mean '
         'ratio of 0.68x. The database contains multiple KEE P5 sequences where compounded win parlays '
         'exceeded $200,000 and $393,000 — amounts the pool simply could not match. Adding a fifth leg '
         'at Keeneland compounds the theoretical fair value faster than the pool grows.',
         ['Strategic implication: At Keeneland, play Pick 4 not Pick 5. The KEE P4 is exotic-favorable '
          'at 83% win rate and 1.58x mean ratio. If you want five legs at KEE, buy the P4 and parlay '
          'the fifth leg as a separate win bet.']),
        ('Finding 3 — The Longshot Threshold Correction',
         'Before the wager base correction, analysis showed the exotic never beating the parlay at any '
         'longshot threshold across any track. After correction, GP, FG, OP, AQU, and CD all show '
         'crossover at the very first threshold tested ($6 win payout = roughly even money). The '
         'finding that was previously invisible: at high-volume tracks, the exotic beats the parlay '
         'even when no longshots appear. The pool is large enough to generate structural value '
         'regardless of leg prices.',
         ['The one original finding that survives: KEE P5 still never crosses 50% at any threshold '
          'even after the 4x normalization. This is the most robust finding in the study.']),
        ('Finding 4 — FG P5 Is Remarkably Consistent',
         'Fair Grounds Pick 5 beat the parlay on 100% of 53 matched race days with a mean ratio of '
         '2.42x. Not a single day where the parlay won. This is the highest win rate of any wager '
         'type at any track in the database. The FG P5 pool appears well-calibrated relative to '
         'handle — large enough to concentrate but not so large that it attracts enough money to '
         'dilute the overlay edge. FG P6, by contrast, is essentially worthless.',
         []),
        ('Finding 5 — CD Will-Pay Multipliers Dwarf Other Tracks',
         'Churchill Downs P3-to-P5 multiplier (mean 61.7x, median 23.4x) is more than double '
         'Gulfstream\'s 27.7x and nearly five times Keeneland\'s 13.2x. This reflects the enormous '
         'size of CD\'s Pick 5 pool relative to its Pick 3 pool. On Derby day with 150,000 bettors, '
         'these multipliers could be even higher. A Pick 3 will-pay of $100 at median implies a '
         'Pick 5 worth $2,340.',
         []),
    ]

    for title, text, sub_bullets in findings:
        h(title, 'h2')
        p(text)
        if sub_bullets:
            bullets(sub_bullets)
        sp(4)

    story.append(PageBreak())

    # ── PAGE 9 — Will-Pay Estimator ───────────────────────────────────────────
    h('7. Will-Pay Estimator')
    p('When you are alive in a multi-race sequence and the track posts a will-pay on the tote board, '
      'the Will-Pay Estimator uses track-specific historical multipliers to estimate the final payout '
      'before the remaining legs run.')
    sp()
    h('The Formula', 'h2')
    p('Estimated Payout = Will-Pay × (Leg odds + 1 for each remaining leg) × track multiplier')
    p('Each estimate shows three versions: low (median multiplier), mean, and high (max/2). '
      'The track multiplier is calibrated from actual historical payout data — not a generic '
      'industry estimate.')
    sp()
    h('Historical Multipliers by Track', 'h2')
    wp_data = [
        ['Track', 'P3 to P4', 'P3 to P5', 'P4 to P5', 'Confidence'],
        ['CD (Churchill Downs)',  '8.62x', '61.7x', '7.87x', 'HIGH (100+ pairs)'],
        ['GP (Gulfstream Park)',  '4.25x', '27.7x', '6.95x', 'HIGH'],
        ['AQU (Aqueduct)',        '5.14x', '22.1x', '5.0x',  'HIGH'],
        ['SA (Santa Anita)',      '1.64x', '15.2x', '6.59x', 'HIGH'],
        ['KEE (Keeneland)',       '4.52x', '13.2x', '1.77x', 'HIGH'],
    ]
    story.append(styled_table(wp_data,
        [1.8*inch, 0.85*inch, 0.85*inch, 0.85*inch, 1.65*inch]))
    sp(8)
    note('CD\'s P3-to-P5 median multiplier of 23.4x means a $100 will-pay implies a P5 worth roughly '
         '$2,340 if your remaining horses hit. The $0.50 P5 minimum base means the posted will-pay '
         'needs to be multiplied by 4 first to get the $2 equivalent before applying the multiplier.')
    story.append(PageBreak())

    # ── PAGE 10 — Morning Line Overlay Detector ───────────────────────────────
    h('8. Morning Line Overlay Detector')
    p('The Today\'s Card tab answers the question no other tool can: given today\'s morning line odds, '
      'is this sequence set up to behave like a historical overlay — or will heavy favorites dilute '
      'the pool?')
    sp()
    h('How to Use It on Derby Morning', 'h2')
    bullets([
        'Open horse-racing-derby.netlify.app on your phone',
        'Tap the Today\'s Card tab',
        'Select CD, your exotic type, and starting race number',
        'For each leg, enter program numbers and morning line odds (format: 5/2, 10-1, 2.5, even)',
        'Tap Analyze',
    ])
    sp()
    h('What the Output Shows', 'h2')
    bullets([
        'Theoretical Parlay Value — best, average, and worst combo parlay across your selections',
        'Sequence History — historical avg, median, hit count, overlay rating from the database',
        'Gap Analysis — the key signal: LONGSHOT SETUP, NEUTRAL, or CHALK ALERT',
        'Combination Table — every one-horse-per-leg combination sorted highest to lowest parlay, '
        'combinations above historical average highlighted in gold',
    ])
    sp()
    signal_data = [
        ['Signal', 'Condition', 'Action'],
        ['LONGSHOT SETUP', 'Avg combo parlay > 1.5x historical avg',
         'Two signals aligned. Strong overlay candidate. Play.'],
        ['NEUTRAL', 'Avg combo parlay 0.8x – 1.5x historical avg',
         'Play based on overlay rating and pool structure alone.'],
        ['CHALK ALERT', 'Avg combo parlay < 0.8x historical avg',
         'Skip even if historical overlay. Favorites will dilute the pool today.'],
    ]
    story.append(styled_table(signal_data,
        [1.2*inch, 2.0*inch, 3.3*inch]))
    sp(8)
    note('The tool works fully offline after first load. All calculations run client-side in the '
         'browser using the cached dashboard_data.json.')
    story.append(PageBreak())

    # ── PAGE 11 — Derby Day Playbook ──────────────────────────────────────────
    h('9. Derby Day Playbook')
    p('The Kentucky Derby is May 3, 2026. The Kentucky Oaks (dress rehearsal) is May 2. '
      'Churchill Downs spring meet opened April 26. Here is the complete plan.')
    sp()

    schedule = [
        ('This Weekend — April 26–27',
         ['After last race each day: run HorseRacingGUI.py to scrape CD live results',
          'Then: python export_dashboard_data.py',
          'Then: git add web/dashboard_data.json → git commit → git push',
          'Confirm CD spring 2026 data appears in Ticket Builder dropdown on the live site']),
        ('Monday April 28 — First Look at 2026 CD Data',
         ['Run: python derby_value.py profile CD',
          'Compare 2026 spring sequences to 2025 baseline',
          'Run: python derby_value.py parlay CD — confirm CD still follows exotic-favorable pattern']),
        ('Tuesday–Wednesday April 29–30',
         ['Scrape CD daily as cards post',
          'Run export and push after each session',
          'By Wednesday the overlay engine has 2026 CD data layered on the 2025 baseline']),
        ('Thursday May 1 — Derby Prep Races',
         ['Scrape and analyze Derby prep races at CD',
          'Test hedge calculator on real ticket scenarios from prep race results',
          'Identify which sequences from the overlay profile showed up in prep race cards']),
        ('Friday May 2 — OAKS DAY (Dress Rehearsal)',
         ['Use all tools live on the Oaks card from your phone in the grandstand',
          'Morning: run Today\'s Card tab with morning line odds for target sequences',
          'During races: test Will-Pay Estimator when alive in sequences',
          'After last race: hedge calc practice on actual tickets',
          'This is the full system test before Derby day']),
        ('Saturday May 3 — DERBY DAY',
         ['The three target sequences based on 2025–2026 CD overlay data: see table below']),
    ]

    for period, items in schedule:
        h(period, 'h2')
        bullets(items)
        sp(4)

    derby_targets = [
        ['Priority', 'Bet', 'Why', 'Expected Range'],
        ['Primary',   'P5 Races 4–8',
         '97.7% exotic win rate. 17 hits. $64K avg, $15K median. Most reliable target.',
         '$15K–$370K'],
        ['Secondary', 'P6 Races 3–8',
         'High variance jackpot play. 88.9% exotic win rate but 7 hits, 2 carryover '
         'jackpots distort avg.',
         '$5K–$2.5M+'],
        ['Tactical',  'P3 Races 5–7',
         '43 hits, most reliable sample. Use to generate live will-pay data for the P5.',
         '$261–$5K'],
    ]
    story.append(styled_table(derby_targets,
        [0.8*inch, 1.0*inch, 3.1*inch, 1.1*inch]))
    sp(10)
    h('Minute-by-Minute Derby Day Decision Tree', 'h2')
    dt_data = [
        ['When', 'Action'],
        ['Derby Morning',
         'Open Today\'s Card tab. Enter morning lines for races 3–8. If LONGSHOT SETUP on P6 '
         'AND P5: maximum conviction. If CHALK ALERT: reduce size or skip.'],
        ['At the Windows',
         'Buy P6 races 3–8 ticket. Buy P5 races 4–8 ticket. Buy P3 races 5–7 as live data '
         'generator. Structure P6 and P5 to cover your strongest horses in each leg.'],
        ['After Race 5',
         'Check P3 will-pay if alive. Open Ticket Builder, enter will-pay and odds of your '
         'Race 6 and 7 horses. If P5 est. > $2,000: consider pressing. If P6 alive: do not '
         'hedge yet.'],
        ['After Race 7',
         'If alive in P5 through 4 legs: enter will-pay in Ticket Builder. If P5 est. > $5,000 '
         'with HIGH confidence: press rather than hedge. Open Hedge Calc if you want to model '
         'the hedge math.'],
        ['Final Leg Alive',
         'Open Hedge Calc. Enter ticket cost, estimated payout, covered horses, field odds. '
         'Use Budget mode with your available hedge cash. The math shows hedging protects '
         'against total loss — it is not about breaking even on the hedge bets.'],
    ]
    story.append(styled_table(dt_data, [1.2*inch, 5.3*inch]))
    story.append(PageBreak())

    # ── PAGE 12 — Track-by-Track Reference ───────────────────────────────────
    h('10. Track-by-Track Reference')

    tracks = [
        ('CD — Churchill Downs (Louisville, KY)',
         'Data: 417 races, 2,200 exotics | Apr 2025–Apr 2026',
         'Character: Premium exotic track. High volume. All wager types structurally exotic-favorable. '
         'P5 is the primary target.',
         'Play: P5 Races 4–8 (primary — 17 hits, 97.7% exotic win, $15K median). '
         'P3 Races 5–7 (43 hits, most reliable sample). '
         'P6 Races 3–8 (high variance jackpot play — 88.9% exotic win but only 7 hits, mean/median '
         'distorted by two carryover jackpots).',
         'Avoid: Nothing structurally — but treat P6 as a lottery ticket not a reliable overlay '
         'given thin sample and jackpot distortion.'),
        ('GP — Gulfstream Park (Hallandale Beach, FL)',
         'Data: ~894 races, ~4,841 exotics | Feb 2025–Apr 2026',
         'Character: Best consistent exotic track in the dataset. Crossover at first threshold on '
         'all wager types.',
         'Play: P4 (98.7% win, 1.97x), P5 (97.4% win, 2.43x), P6 (90.9% win, 3.01x).',
         'Avoid: Nothing — structural edge across all three wager types.'),
        ('FG — Fair Grounds (New Orleans, LA)',
         'Data: 473 races, 2,504 exotics | Jan–Mar 2025',
         'Character: P4 and P5 exotic-favorable. P6 worthless — pool too small.',
         'Play: P5 (100% exotic win rate across 53 days, 2.42x mean — most consistent P5 in '
         'dataset). P4 (94.3% win, 1.86x).',
         'Avoid: P6 completely — 98.1% parlay win rate. The pool cannot compete.'),
        ('OP — Oaklawn Park (Hot Springs, AR)',
         'Data: 490 races, 2,541 exotics | Jan–May 2025',
         'Character: Solid exotic track for P4 and P5. Strong overlay signal on early sequences.',
         'Play: P4 Races 2–5 (48 hits — largest P4 sample in dataset, 1.55x overlay). '
         'P5 (93.6% win, 2.31x). P3 Races 1–3 (47 hits, 1.70x).',
         'Avoid: P6 — not enough data to conclude.'),
        ('AQU — Aqueduct (Queens, NY)',
         'Data: ~562 races, ~3,088 exotics | Jan–Apr 2025',
         'Character: Mixed. Strong P5, moderate P4, weak P6.',
         'Play: P5 (98.4% exotic win, 2.57x — second highest P5 win rate in dataset). '
         'P4 (75.8% win, 1.51x). DD Races 8–9 (2.13x overlay, HIGH consistency).',
         'Avoid: P6 (11.5% exotic win — pool is too small at AQU).'),
        ('SA — Santa Anita (Arcadia, CA)',
         'Data: ~459 races, ~2,516 exotics | Jan–Apr 2025',
         'Character: P4 and P5 exotic-favorable. P6 pool too small.',
         'Play: P5 (90% win, 3.42x mean — high variance, some 50x days). P4 (86% win, 1.72x). '
         'P5 Races 6–10 (22 hits, 2.35x, MODERATE — best qualified sequence).',
         'Avoid: P6 (18.4% exotic win rate, 0.52x mean — deep parlay territory).'),
        ('KEE — Keeneland (Lexington, KY)',
         'Data: 115 races, 633 exotics | Apr 2025–Apr 2026',
         'Character: Most nuanced track. P4 exotic-favorable. P5 is a trap.',
         'Play: P4 (83% exotic win, 1.58x). P5 Races 6–10 if building the P4 with it. '
         'DD Races 9–10 (HIGH overlay, 1.75x, 16 hits).',
         'Avoid: P5 completely as a standalone — 33% exotic win rate, 0.68x mean. '
         'The parlay wins 67% of days. P6 is binary 50/50 with thin sample.'),
    ]

    for name, data_line, char, play, avoid in tracks:
        h(name, 'h2')
        p(data_line)
        p(f'<i>{char}</i>')
        p(f'<b>Play:</b> {play}')
        p(f'<b>Avoid:</b> {avoid}')
        sp(4)

    story.append(PageBreak())

    # ── PAGE 13 — The Three Rules ─────────────────────────────────────────────
    h('11. The Three Rules')
    p('After 18,446 exotic payouts across 7 tracks and 218 race days, three rules emerge from the '
      'data. These are not opinions — they are what the numbers say.')
    sp()
    rule()

    rules = [
        ('Rule 1', 'Never play P6 at FG or SA.',
         'Parlay wins 98% of the time at FG and 82% at SA. The pools are too small. '
         'The structural takeout advantage of the parlay cannot be overcome at these volume levels. '
         'This holds at every longshot threshold tested.'),
        ('Rule 2', 'Never play P5 at KEE expecting pool value.',
         'Even after the 4x wager base normalization, the KEE P5 parlay wins 67% of days with a '
         'mean ratio of 0.68x. The database contains sequences where the theoretical parlay exceeded '
         '$393,000 and the pool could not match it. Buy the KEE P4 instead. If you want five legs '
         'at Keeneland, parlay the fifth leg as a separate win bet.'),
        ('Rule 3', 'At CD and GP, exotic pools generate structural value.',
         'These two tracks show exotic-favorable results across P4, P5, and P6 at crossover from '
         'the very first threshold tested. The pool is large enough that even chalk days produce '
         'more than the parlay. This is a structural characteristic of high-volume tracks — not a '
         'sample size artifact. Play exotics confidently at CD and GP on overlay-rated sequences.'),
    ]

    for num, headline, detail in rules:
        story.append(Paragraph(num, s['rule']))
        story.append(Paragraph(f'<b>{headline}</b>', s['body']))
        p(detail)
        sp(6)

    story.append(PageBreak())

    # ── PAGE 14 — How to Keep Current ────────────────────────────────────────
    h('How to Keep the Platform Current')
    p('Derby Value is a living system. The more CD data loaded before Derby day, the more accurate '
      'the overlay engine becomes. Here is what to do each week:')
    sp()
    bullets([
        'After each CD race day (starting April 26): run HorseRacingGUI.py, export, push',
        'Run scrape_entries.py each morning (or let run_morning_entries.bat handle it automatically)',
        'After Derby week (May 3): scrape fall meets at CD and target tracks for Preakness/Belmont',
        'Add Pimlico data before Preakness (May 17): python HorseRacingHRN.py --track PIM spring2025',
        'Add Belmont data before Belmont (June 7): python HorseRacingHRN.py --track BEL spring2025',
    ])
    sp(12)
    p('The platform is designed to grow. Every new race day makes the overlay engine more accurate, '
      'the parlay analysis more statistically robust, and the will-pay multipliers more precisely '
      'calibrated. The goal is to arrive at Derby day with the most complete exotic payout database '
      'in private hands — and use it.')
    sp(24)
    rule()
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(
        'Derby Value | Built with Claude Code | April 2026',
        s['footer']))
    story.append(Paragraph(
        'horse-racing-derby.netlify.app | github.com/jcoogan80/horse-racing-derby',
        s['footer']))
    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph(
        'Database: 3,476 races | 18,446 exotic payouts | 7 tracks | 218 race days',
        s['footer']))

    return story


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    doc = SimpleDocTemplate(
        OUTPUT,
        pagesize=letter,
        rightMargin=1 * inch,
        leftMargin=1 * inch,
        topMargin=0.9 * inch,
        bottomMargin=0.9 * inch,
        title='Derby Value Complete Project Guide',
        author='Derby Value / Claude Code',
    )
    s = build_styles()
    story = build_story(s)
    doc.build(story)
    print(f'Generated: {OUTPUT}')


if __name__ == '__main__':
    main()
