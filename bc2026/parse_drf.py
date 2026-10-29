"""Parse DRF raw-text past performances (pdftotext -raw) into JSON for the BC races."""
import re, json, sys, datetime as dt

BC_NAMES = {'BCJvTfSp-G1':'Juvenile Turf Sprint','BCJuvFil-G1':'Juvenile Fillies','BCJvFlTf-G1':'Juvenile Fillies Turf','BCJuvnle-G1':'Juvenile','BCJuvTrf-G1':'Juvenile Turf','BCFMSprt-G1':'Filly & Mare Sprint','BCTrfSpt-G1':'Turf Sprint','BCDirtMi-G1':'Dirt Mile','BCFMTrf-G1':'Filly & Mare Turf','BCSprint-G1':'Sprint','BCMile-G1':'Mile','BCDistaf-G1':'Distaff','BCTurf-G1':'Turf','BCClasic-G1':'Classic'}
OTHER_NAMES = {'OC 80k/N2X':'Allowance Optional Claiming (N2X)','Md Sp Wt 150k':'Maiden Special Weight','TBAftrcAlL250k':'Thoroughbred Aftercare Alliance S.','Alw 165000N1X':'Allowance (N1X)','OC 100k/N1X':'Allowance Optional Claiming (N1X)','OC 100k/N3X':'Allowance Optional Claiming (N3X)'}
MONTH = {'â':1,'á':2,'à':3,'ß':4,'Ü':5,'Þ':6,'Û':7,'Ý':8,'æ':9,'å':10,'ä':11,'ã':12}
DATE_RE = re.compile(r'^(ò)?(\d{1,2})([âáàßÜÞÛÝæåäã])(\d\d)')
RACE_HDR = re.compile(r'^(\d{1,2}) Keeneland (.+)$')
JOCKEY_RE = re.compile(r"^([A-Z][A-Z .'\-]+?) \((?:>|\d+)?\)(?: \(> ?\))?(?: 2026: \((\d+) (\d+) (\.\d+|1\.00)\))?\s*$|^([A-Z][A-Z .'\-]+?) 2026: \((\d+) (\d+) (\.\d+|1\.00)\)")
TRAINER_RE = re.compile(r"^Tr: (.+?)\(.*?\)(?: 2026:\((\d+) (\d+) (\.\d+|1\.00)\)| \(>\))?\s*$")
PACE_RE = re.compile(r'TimeformUS Pace: Early (\d+|-)\s+Late (\d+|-)')
REC_RE = re.compile(r'^(Life|2026|2025|Kee \S|D\.Fst|Wet\(\S*\)|Synth\(\S*\)|Turf\(\S*\)|Dst\S*\(\S*\)|Dst\S*) (\d+) (\d+|M) (\d+) (\d+) \$([\d,]+) (\d+|-)')
ODDS_RE = re.compile(r'^\d+-\d+$')
BEYER_RE = re.compile(r' (\d{2,3}|-) (\d{1,2}) /(\d{1,2}) ')
TF_RE = re.compile(r'^Timeform Rating: (\d+)')
FINAL_ODDS_RE = re.compile(r' (\*?\d+\.\d\d) ')


def parse_date(m):
    d, mon, yy = int(m.group(2)), MONTH[m.group(3)], int(m.group(4))
    return dt.date(2000 + yy, mon, d)


def split_races(lines):
    races, cur = [], None
    for i, ln in enumerate(lines):
        m = RACE_HDR.match(ln.strip())
        if m:
            num = int(m.group(1))
            nxt = lines[i + 1] if i + 1 < len(lines) else ''
            if cur is None or cur['num'] != num:
                cur = {'num': num, 'code': m.group(2), 'cond': nxt.strip(), 'lines': []}
                races.append(cur)
            continue
        if cur is not None:
            cur['lines'].append(ln.rstrip('\n'))
    return races


def parse_race(r, racedate):
    L = r['lines']
    # header info
    head = '\n'.join(L[:30])
    par = re.search(r'Beyer par: (\d+|NA)', head)
    post = re.search(r'Post time: (\S+ ET)', head)
    r['beyer_par'] = int(par.group(1)) if par and par.group(1).isdigit() else None
    r['post_time'] = post.group(1) if post else None
    code = r['code'].lstrip('ç')
    r['code'] = code
    r['name'] = BC_NAMES.get(code) or OTHER_NAMES.get(code)
    r['dist_text'] = r['cond'].split(' (')[0]
    r['turf'] = '(Turf)' in r['cond']
    # horse starts: line that is program number, followed by ML odds line
    horses, idx = [], []
    for i in range(len(L) - 2):
        if re.fullmatch(r'\d{1,2}[A-Z]?', L[i].strip()) and ODDS_RE.match(L[i + 1].strip()):
            idx.append(i)
    idx.append(len(L))
    for a, b in zip(idx, idx[1:]):
        horses.append(parse_horse(L[a:b], racedate))
    r['horses'] = horses
    del r['lines']
    return r


def parse_horse(B, racedate):
    h = {'pgm': B[0].strip(), 'ml': B[1].strip(), 'name': B[2].strip()}
    num, den = h['ml'].split('-')
    h['ml_dec'] = int(num) / int(den)
    h['pps'], h['records'] = [], {}
    h['bullets'] = 0
    h['works'] = []
    last_pp = None
    for ln in B[3:]:
        s = ln.strip()
        if s.startswith('Own:'):
            h['owner'] = s[4:].strip(); continue
        m = JOCKEY_RE.match(s)
        if m and 'jockey' not in h:
            g = m.groups()
            if g[0]:
                h['jockey'] = g[0].strip(); h['jky_starts'] = int(g[1]) if g[1] else None; h['jky_win'] = float(g[3]) if g[3] else None
            else:
                h['jockey'] = g[4].strip(); h['jky_starts'] = int(g[5]); h['jky_win'] = float(g[7])
            continue
        m = TRAINER_RE.match(s)
        if m:
            h['trainer'] = m.group(1).strip(); h['trn_starts'] = int(m.group(2)) if m.group(2) else None; h['trn_win'] = float(m.group(4)) if m.group(4) else None; continue
        m = PACE_RE.search(s)
        if m:
            h['tfus_early'] = None if m.group(1) == '-' else int(m.group(1))
            h['tfus_late'] = None if m.group(2) == '-' else int(m.group(2)); continue
        if s.startswith('Sire:'):
            h['sire'] = s[5:].strip(); continue
        if s.startswith('Br:'):
            h['breeder'] = s[3:].strip(); continue
        if re.match(r'^[BDGC][a-z]*\.? [a-z]+\.? \d', s) and 'sex_age' not in h:
            h['sex_age'] = s; continue
        m = REC_RE.match(s)
        if m:
            key = m.group(1)
            key = 'Kee' if key.startswith('Kee') else ('Dst' if key.startswith('Dst') else key.split('(')[0])
            if key not in h['records']:
                st = int(m.group(2)); w = 0 if m.group(3) == 'M' else int(m.group(3))
                h['records'][key] = {'st': st, 'w': w, 'p': int(m.group(4)), 's': int(m.group(5)),
                                     'earn': int(m.group(6).replace(',', '')),
                                     'best': None if m.group(7) == '-' else int(m.group(7))}
            continue
        if s.startswith('WORKS:'):
            ws = re.findall(r'(ò)?(\d{1,2})([âáàßÜÞÛÝæåäã])(\S+?)(\d+f|\d+ ?f)\s', s + ' ')
            h['bullets'] = s.count('ò')
            h['works_raw'] = s[6:].strip()
            continue
        if s.startswith('TRAINER:'):
            h['trainer_stats'] = s[8:].strip(); continue
        tm = TF_RE.match(s)
        if tm and last_pp is not None:
            last_pp['tf'] = int(tm.group(1)); continue
        dm = DATE_RE.match(s)
        if dm and not s.startswith('WORKS'):
            try:
                d = parse_date(dm)
            except Exception:
                continue
            pp = {'date': d.isoformat(), 'raw': s}
            bm = BEYER_RE.search(s)
            bm2 = None if bm else re.search(r' (\d{3,5})/(\d{1,2}) ', s)
            if bm2:
                blob, fld = bm2.group(1), int(bm2.group(2))
                for cut in (len(blob) - 2, len(blob) - 1):
                    b_, p_ = blob[:cut], blob[cut:]
                    if b_ and 30 <= int(b_) <= 130 and 1 <= int(p_) <= fld:
                        pp['beyer'] = int(b_); pp['post'] = int(p_); pp['field'] = fld; break
            if bm or bm2:
                if bm:
                    pp['beyer'] = None if bm.group(1) == '-' else int(bm.group(1))
                    pp['post'] = int(bm.group(2)); pp['field'] = int(bm.group(3))
                rest = s[(bm or bm2).end():].split(' ')
                calls = []
                for tok in rest:
                    if re.match(r'^ñ?[A-Z][a-zA-Z\']', tok):
                        pp['jockey'] = tok.lstrip('ñ'); break
                    mm = re.match(r'^(\d{1,2})', tok)
                    if mm: calls.append(int(mm.group(1)))
                if calls: pp['fin'] = calls[-1]
                pp['us'] = True
            else:
                # foreign line: '... <field> <fin><glyphs> Jockey Name <wt> <odds> Winner...'
                fm = re.search(r' (\d{1,2}) (\d{1,2})[^\s\d]* ([A-Z][A-Za-z\'\- ]+?)(?: (\d{3}) (\*?\d+\.\d\d)|$| \d{3}\b)', s)
                if fm:
                    pp['field'] = int(fm.group(1)); pp['fin'] = int(fm.group(2))
                    pp['jockey'] = fm.group(3).strip()
                    if fm.group(5): pp['odds'] = float(fm.group(5).lstrip('*')); pp['fav'] = fm.group(5).startswith('*')
                pp['us'] = False
            om = FINAL_ODDS_RE.search(s)
            if om and 'odds' not in pp:
                pp['odds'] = float(om.group(1).lstrip('*')); pp['fav'] = om.group(1).startswith('*')
            # surface: turf glyph ê, synthetic ú, inner turf Ñ; dirt otherwise
            seg = s[:70]
            pp['surf'] = 'T' if re.search(r'[êÑ]', seg) else ('S' if 'ú' in seg else 'D')
            tr = re.match(r'^ò?\d{1,2}\S\d\d=?\d*\s?([A-Za-z]+(?:\([A-Z]+\))?)', s)
            pp['track'] = tr.group(1) if tr else None
            # race class text
            h['pps'].append(pp); last_pp = pp
    # derived
    pps = h['pps']
    if pps:
        last = dt.date.fromisoformat(pps[0]['date'])
        h['days_off'] = (racedate - last).days
    else:
        h['days_off'] = None
    bey = [p.get('beyer') for p in pps if p.get('us') and p.get('beyer') is not None]
    tfs = [p.get('tf') for p in pps if p.get('tf') is not None]
    h['beyers'] = bey[:6]
    h['timeform'] = tfs[:6]
    h['n_us'] = sum(1 for p in pps if p.get('us'))
    h['n_foreign'] = sum(1 for p in pps if not p.get('us'))
    h['foreign_based'] = bool(pps) and not pps[0].get('us')
    return h


if __name__ == '__main__':
    fn, datestr, out = sys.argv[1], sys.argv[2], sys.argv[3]
    racedate = dt.date.fromisoformat(datestr)
    lines = open(fn, encoding='utf-8', errors='replace').read().split('\n')
    races = [parse_race(r, racedate) for r in split_races(lines)]
    races = [r for r in races if r['name']]
    json.dump(races, open(out, 'w'), indent=1, default=str)
    for r in races:
        print(r['num'], r['name'], r['dist_text'], 'par', r['beyer_par'], len(r['horses']))
        for h in r['horses']:
            print('   ', h['pgm'], h['name'][:22].ljust(22), h['ml'].rjust(5), (h.get('jockey') or '?')[:14].ljust(14),
                  (h.get('trainer') or '?')[:16].ljust(16), 'B', h['beyers'][:4], 'TF', h['timeform'][:3],
                  'pace', h.get('tfus_early'), h.get('tfus_late'), 'off', h['days_off'], 'pps', len(h['pps']))
