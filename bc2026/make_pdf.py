import json, html
M = json.load(open('page_data.json'))
DAYS = ('sat',)   # Saturday edition
races = [r for r in M['races'] if r['day'] in DAYS]; T = [t for t in M['tickets'] if t['day'] in DAYS]
P = {f"{r['day']}-{r['num']}": r['plays'] for r in races}
SC = {1:('#d0202e','#fff'),2:('#fff','#111'),3:('#1f4fbf','#fff'),4:('#f6d32d','#111'),5:('#1e7b3a','#fff'),6:('#111','#f6d32d'),7:('#f28c1b','#111'),8:('#f6a1c0','#111'),9:('#2bc3c8','#111'),10:('#6c2c91','#fff'),11:('#9aa0a6','#b4141d'),12:('#a6d84a','#111'),13:('#6b4423','#fff'),14:('#7b1e2b','#f6d32d'),15:('#c3b091','#111'),16:('#7fb8e6','#b4141d'),17:('#1c2b5a','#fff'),18:('#2f6b3a','#f6d32d')}
e = html.escape
def chip(p):
    bg, fg = SC.get(int(''.join(c for c in p if c.isdigit())), ('#777', '#fff'))
    return f'<span class="sc" style="background:{bg};color:{fg}">{e(p)}</span>'
def nm(h): return h['name'].split(' (')[0]
def odds(f): return '—' if f is None else (f'{f:.1f}-1' if f < 10 else f'{round(f)}-1')
def sel(p):
    s = p['sel']
    if p['type'].startswith('Win'): return chip(s[0])
    if p['type'] == 'Exacta box': return ''.join(chip(x) for x in s) + ' box'
    return ' / '.join(''.join(chip(x) for x in leg) for leg in s)
def runners(r): return sorted([h for h in r['horses'] if h['status'] == 'run'], key=lambda h: -h['p'])
DAYN = {'fri': 'Friday, Oct 30 · Future Stars', 'sat': 'Saturday, Oct 31 · Championship Day'}

# --- top plays summary
rows = []
for r in races:
    hs = {h['pgm']: h for h in r['horses']}
    for p in P[f"{r['day']}-{r['num']}"]['plays']:
        if p['type'].startswith('Win'):
            h = hs[p['sel'][0]]
            rows.append((r, p, h))
summary = ''.join(f"""<tr><td>{'Fri' if r['day']=='fri' else 'Sat'} R{r['num']}</td><td>{e(r['short'])}</td><td>{e(r['post'])}</td>
  <td>{chip(h['pgm'])} {e(nm(h))}</td><td class="n">{e(h['ml'])}</td><td class="n">{h['p']*100:.0f}%</td><td class="n">{odds(h['fair'])}</td>
  <td>{e(p['type'])}</td><td class="n"><b>{p['units']*p['combos']:g}u</b></td></tr>""" for r, p, h in rows)
fades = []
for r in races:
    for h in runners(r):
        if 'FADE' in h['tags']:
            fades.append(f"{'Fri' if r['day']=='fri' else 'Sat'} R{r['num']} {chip(h['pgm'])} {e(nm(h))} ({e(h['ml'])}, model {h['p']*100:.0f}%)")
keys = []
for r in races:
    t = runners(r)[0]
    if 'KEY' in t['tags']:
        keys.append(f"{'Fri' if r['day']=='fri' else 'Sat'} R{r['num']} {chip(t['pgm'])} {e(nm(t))} ({e(t['ml'])}, {t['p']*100:.0f}%)")

def race_block(r):
    hs = runners(r)[:5]
    pl = P[f"{r['day']}-{r['num']}"]
    scr = [h for h in r['horses'] if h['status'].startswith('Scratched')]
    trs = ''.join(f"<tr><td>{chip(h['pgm'])}</td><td>{e(nm(h))}</td><td class='n'>{e(h['ml'])}</td><td class='n'><b>{h['p']*100:.0f}%</b></td><td class='n'>{odds(h['fair'])}</td><td class='tg'>{' '.join(h['tags'])}</td></tr>" for h in hs)
    plays = ''.join(f"<div class='pl'><span class='pt'>{e(p['type'])}</span><span>{sel(p)} <span class='u'>{p['units']:g}u × {p['combos']} = {p['units']*p['combos']:g}u</span></span></div>" for p in pl['plays'])
    notes = ''.join(f"<div class='nt'>• {e(n)}</div>" for n in pl['notes'] if not n.startswith('No straight'))
    nostr = '' if any(p['type'].startswith('Win') for p in pl['plays']) else "<div class='nt'>• No straight bet. Exotics / multi-race only.</div>"
    scrl = f"<div class='scr'>Scratched: {', '.join(e(h['pgm']+' '+nm(h)) for h in scr)}</div>" if scr else ''
    hc = f"<div class='hc'>{e(r['note'])}</div>" if r['covered'] else ''
    return f"""<div class="race"><div class="rh"><span class="rn">R{r['num']}</span> <b>{e(r['name'])}</b>
      <span class="rf">{e(r['dist'])} {'turf' if r['turf'] else 'dirt'} · Post {e(r['post'])} ET · {r['field']} run</span></div>{scrl}
      <table class="mini"><tr><th></th><th>Top 5 (model)</th><th class='n'>ML</th><th class='n'>Win</th><th class='n'>Fair</th><th>Tags</th></tr>{trs}</table>
      {'<div class="nt">• Race run: plays at post were scored under that time\'s rules (see result).</div>' if r.get('result') else f'<div class="plays">{plays}</div>{notes}{nostr}'}{hc}
      {res_line(r)}</div>"""

def res_line(r):
    x = r.get('result')
    if not x: return '<div class="write">Result: ______ ______ ______ &nbsp; Bet: $______ &nbsp; Return: $______</div>'
    pays = x.get('pays', {})
    return (f"<div class='res'><b>Result:</b> {' – '.join(chip(p) for p in x['order'][:4])} &nbsp; exacta ${pays.get('exacta_1', 0):g} ($1) · "
            f"tri ${pays.get('trifecta_0.50', 0):g} (50¢) &nbsp; <b class='{'pos' if (x.get('net_units') or 0) > 0 else 'neg'}'>{(x.get('net_units') or 0):+g}u</b></div>")

def tix_table(day):
    groups = {}
    for t in T:
        if t['day'] != day: continue
        groups.setdefault((t['bet'], tuple(t['races'])), {})[t['kind']] = t
    out = ''
    for (bet, rs), v in groups.items():
        def line(t): return ' / '.join(','.join(l['pgms']) for l in t['legs'])
        m, w, a = v.get('main'), v.get('wide') or v.get('tight'), v.get('against')
        WIN = {r['num']: r['result']['order'][0] for r in races if r.get('result')}
        def stat(t):
            done = [l for l in t['legs'] if l['race'] in WIN]
            if not done: return ''
            if all(WIN[l['race']] in l['pgms'] for l in done):
                return " <b class='pos'>HIT</b>" if len(done) == len(t['legs']) else f" <b class='pos'>ALIVE {len(done)}/{len(t['legs'])}</b>"
            return " <b class='neg'>DEAD</b>"
        out += f"""<tr><td><b>{e(bet)}</b><br><span class='u'>R{rs[0]}–R{rs[-1]}</span></td>
          <td class='tk'>{e(line(m))}{stat(m)}<br><span class='u'>{m['combos']} combos · ${m['combos']*0.5:.2f} @ 50¢ · hit {m['hit']*100:.1f}%</span></td>
          <td class='tk'>{e(line(w))}{stat(w)}<br><span class='u'>{w['combos']} combos · ${w['combos']*0.5:.2f} @ 50¢ · hit {w['hit']*100:.1f}%</span>
          {f"<br><b>Against:</b> {e(line(a))} <span class='u'>({a['combos']} combos, hit {a['hit']*100:.1f}%)</span>" if a else ''}</td></tr>"""
    return f"<table class='tix'><tr><th>Bet</th><th>Main ticket (saver rules)</th><th>Tight backup</th></tr>{out}</table>"

rules_html = ''.join(f'<li>{e(x)}</li>' for x in M['lessons']['sat'][1:])
body = f"""
<div class="cover">
 <div class="eb">Keeneland · Breeders' Cup · October 30–31, 2026</div>
 <h1>Saturday Betting Sheet</h1>
 <div class="sub">Model: DRF figures + OptixEQ + Racing Dudes (Aaron Halterman, Magic, Jon White) + morning line. Updated Sat 10/31 1:25 PM CT after R5: results R1–R5 filled in, ticket status marked, model #1 back on top in non-KEY races, tote scratches applied. Odds are morning line: re-check the board, and skip a win bet if the price drops below fair odds.</div>
 <div class="box"><b>Scratches applied (tote, Sat 8 AM CT):</b> R1 Candor · R3 Jimmy Rules, Lips Say Bliss, Extra Anejo · R4 Praying, Nooni · R7 Eccentric · R10 Splendora · R12 Magnitude · Sat R7 Evershed · Sat R9 Zulu Kingdom · Sat R10 Scottish Lassie · Sat R11 Test Score. Also-eligibles not drawn in are left out.</div>
 <h2>Saturday rules (from Friday's results)</h2>
 <ul class="rules">{rules_html}</ul>
 <h2>Straight bets</h2>
 <table class="sum"><tr><th>Race</th><th></th><th>Post ET</th><th>Horse</th><th class="n">ML</th><th class="n">Model</th><th class="n">Fair</th><th>Bet</th><th class="n">Stake</th></tr>{summary or '<tr><td colspan=9>None at morning-line odds. Win bets only on a KEY whose board price is at least a third above fair.</td></tr>'}</table>
 <div class="two"><div><h3>KEY horses (35%+; single in multis at 40%+)</h3>{'<br>'.join(keys)}</div><div><h3>Fades (short price, model lower)</h3>{'<br>'.join(fades)}</div></div>
 <div class="legend"><b>How to read.</b> 1 unit (u) = your base bet. Win % = model chance. Fair = odds that match the model; bet a win only when the board is at least a third above fair. Tags: KEY 35%+ · VALUE beats ML by 25%+ · FADE short price, model lower · BOMB 15-1+ with a case · AGAINST a handicapper is against it · OPTIX top Optix velocity. Exacta key = A over B; Trifecta = A / B / C.</div>
</div>
"""
for day in DAYS:
    body += f"<h2 class='day'>{DAYN[day]}</h2><div class='grid'>" + ''.join(race_block(r) for r in races if r['day'] == day) + "</div>"
    body += f"<h2 class='day tk2'>{DAYN[day].split(' · ')[0]} · Multi-race tickets</h2>" + tix_table(day)

css = """
@page { size: Letter; margin: 0.45in 0.45in 0.5in; }
* { box-sizing: border-box; }
body { font-family: 'DejaVu Sans', Arial, sans-serif; font-size: 8.6pt; color: #111; margin: 0; }
h1 { font-size: 22pt; margin: 2pt 0 4pt; color: #1d4a35; }
h2 { font-size: 13pt; margin: 10pt 0 5pt; color: #1d4a35; border-bottom: 1.5pt solid #1d4a35; padding-bottom: 2pt; }
h2.day { page-break-before: always; }
h3 { font-size: 9.5pt; margin: 6pt 0 3pt; }
.eb { font-size: 8pt; letter-spacing: .12em; text-transform: uppercase; color: #8a6a22; font-weight: bold; }
.sub { color: #444; font-size: 8.4pt; max-width: 7in; }
.box { border: 1pt solid #c9b27a; background: #faf6ea; padding: 5pt 7pt; margin: 7pt 0; font-size: 8.2pt; }
.sum td { padding: 1.2pt 3pt; font-size: 7.8pt; }
.sum .sc { font-size: 7pt; padding: 0 2pt; }
.cover h2 { margin-top: 6pt; }
.legend { margin-top: 6pt; font-size: 7.8pt; color: #333; border-top: .5pt solid #bbb; padding-top: 5pt; }
table { border-collapse: collapse; width: 100%; }
th { text-align: left; font-size: 7pt; text-transform: uppercase; letter-spacing: .04em; color: #555; border-bottom: .8pt solid #333; padding: 2pt 3pt; }
td { padding: 2.2pt 3pt; border-bottom: .4pt solid #ccc; vertical-align: middle; }
.n { text-align: right; white-space: nowrap; }
.sc { display: inline-block; min-width: 13pt; text-align: center; font-weight: bold; font-size: 7.6pt; padding: 1pt 2pt; border-radius: 2pt; border: .5pt solid #666; margin-right: 1pt; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 12pt; font-size: 7.8pt; line-height: 1.55; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 7pt; }
.race { border: .8pt solid #888; border-radius: 3pt; padding: 5pt 6pt; break-inside: avoid; page-break-inside: avoid; }
.rh { border-bottom: .6pt solid #aaa; padding-bottom: 2pt; margin-bottom: 3pt; }
.rn { background: #1d4a35; color: #fff; font-weight: bold; padding: 0 4pt; border-radius: 2pt; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
.rf { display: block; color: #555; font-size: 7.4pt; margin-top: 1pt; }
.mini td, .mini th { padding: 1.4pt 2pt; font-size: 7.8pt; }
.tg { font-size: 6.4pt; color: #444; }
.plays { margin-top: 3pt; display: grid; gap: 2pt; }
.pl { display: grid; grid-template-columns: 62pt 1fr; align-items: center; font-size: 8pt; }
.pt { font-weight: bold; color: #1d4a35; }
.u { color: #555; font-size: 7pt; }
.nt { font-size: 7.1pt; color: #6b4a00; margin-top: 1.5pt; }
.hc { font-size: 7pt; color: #333; margin-top: 3pt; font-style: italic; }
.scr { font-size: 7.2pt; color: #a32020; }
.res { margin-top: 4pt; font-size: 7.6pt; } .pos { color: #1d7a3a; } .neg { color: #a32020; }
.write { margin-top: 4pt; font-size: 7.2pt; color: #666; }
.tix td { font-size: 7.8pt; }
.tix .tk { font-family: 'DejaVu Sans Mono', monospace; font-size: 7.6pt; }
.tix tr { break-inside: avoid; }
.rules { margin: 2pt 0 4pt 14pt; padding: 0; font-size: 8pt; line-height: 1.45; }
"""
open('bet_sheet.html', 'w').write(f"<!doctype html><html><head><meta charset='utf-8'><style>{css}</style></head><body>{body}</body></html>")
print('ok', len(rows), 'straight bets')
