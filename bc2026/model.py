"""BC 2026 EV model: figures + pace + connections (fig model), handicapper consensus, ML -> blended win%, edge, tags."""
import json, math, re, statistics as st, sys
sys.path.insert(0, 'optix')
from plots import PLOTS
_OPT = json.load(open('optix/optix.json'))
def _norm(n): return re.sub(r'\s*\([A-Z]{2,3}\)\s*$', '', n.upper()).replace("'", "").strip()
OPTIX = {(d, int(rn)): {_norm(h['name']): h for h in hs} for d, x in _OPT.items() for rn, hs in x.items()}

TF_OFFSET = 12          # Timeform rating -> Beyer-equivalent
EURO_TURF_BOOST = 1.5   # Saturday turf: multiply foreign-based runners' win% before renormalizing
T_SOFT = 4.5            # softmax temperature (points)
W_FIG, W_CONS, W_ML = 0.45, 0.25, 0.30

# --- scratches / AE status (as of Thu 10/29) ---
OUT = {
    ('fri', 3): {'13', '14', '15', '16'},                     # AEs (not drawn in)
    ('fri', 6): {'13', '14', '15', '16', '17'},               # AEs (max 12)
    ('fri', 8): {'2', '16', '17'},                            # Go for Launch out (not in Optix program) -> Silent Beauty (15) in; 16-17 AEs
    ('fri', 9): {'2', '4'},                                   # Gaudreau, Earth Song scr                                        # Gaudreau scr
    ('fri', 10): {'1'},                                       # Induction scr -> Popcorn (15) in
    ('sat', 1): {'1'},                                        # Sat-morning tote scratches (TwinSpires): Candor
    ('sat', 3): {'3', '4', '5'},                              # Jimmy Rules, Lips Say Bliss, Extra Anejo
    ('sat', 4): {'3', '13'},                                  # Praying, Nooni
    ('sat', 12): {'6'},                                       # Magnitude
    ('sat', 5): {'15', '16', '17', '18'},                     # AEs
    ('sat', 7): {'2', '9'},                                   # Evershed scr -> Vina Arana (15) in
    ('sat', 9): {'6', '15'},                                  # Zulu Kingdom scr; Vina Arana runs F&M Turf
    ('sat', 10): {'5', '8'},                                  # Scottish Lassie scr
    ('sat', 11): {'8', '16'},                                 # Test Score scr -> Map of Stars (15) in; Telescopic AE
}
SCR_NOTE = {('fri', 9, '4'): 'Scratched', ('fri', 8, '2'): 'Scratched (missing from Optix program)', ('fri', 9, '2'): 'Scratched', ('fri', 10, '1'): 'Scratched', ('sat', 7, '2'): 'Scratched',
            ('sat', 9, '6'): 'Scratched', ('sat', 10, '5'): 'Scratched', ('sat', 11, '8'): 'Scratched',
            ('sat', 9, '15'): 'Running in F&M Turf', ('sat', 1, '1'): 'Scratched', ('sat', 3, '3'): 'Scratched', ('sat', 3, '4'): 'Scratched', ('sat', 3, '5'): 'Scratched', ('sat', 4, '3'): 'Scratched', ('sat', 4, '13'): 'Scratched', ('sat', 7, '9'): 'Scratched', ('sat', 10, '8'): 'Scratched', ('sat', 12, '6'): 'Scratched'}

# --- handicapper opinions: race -> {source: {pgm: role}} ; roles: top, 2,3,4, use, single, bomb, against
CONS = {
    ('fri', 6): {'Aaron': {'4': 'top', '10': 'use', '3': 'use'},
                 'Jon': {'3': 'top', '10': 'use', '4': 'use'}},
    ('fri', 7): {'Aaron': {'10': 'top', '5': 'use'},
                 'Magic': {'8': 'top', '4': 'use', '6': 'use', '7': 'use', '10': 'against'},
                 'Jon': {'10': 'top', '2': '2', '5': 'use'}},
    ('fri', 8): {'Aaron': {'9': 'top', '12': '2'},
                 'Jon': {'10': 'top', '9': 'use'}},
    ('fri', 9): {'Aaron': {'5': 'top', '7': '2', '6': '3', '3': '4'},
                 'Magic': {'6': 'use', '7': 'use', '5': 'against'},
                 'Jon': {'5': 'top', '3': '2', '6': 'use', '7': 'use'}},
    ('fri', 10): {'Aaron': {'10': 'use', '14': 'use', '5': 'use'},
                  'Magic': {'14': 'single'},
                  'Jon': {'2': 'top', '5': 'use', '10': 'use', '14': 'use'}},
    ('sat', 4): {'Aaron': {'2': 'top', '4': 'use', '11': 'use'},
                 'Jon': {'2': 'top'}},
    ('sat', 5): {'Aaron': {'11': 'top'},
                 'Jon': {'3': 'top', '7': 'use'}},
    ('sat', 6): {'Jon': {'7': 'top', '1': 'use'}},
    ('sat', 7): {'Aaron': {'11': 'top', '12': 'use'},
                 'Jon': {'12': 'single', '5': 'use', '11': 'use', '13': 'use'}},
    ('sat', 8): {'Aaron': {'13': 'top'},
                 'Jon': {'13': 'top', '3': 'bomb', '11': 'use'}},
    ('sat', 9): {'Aaron': {'8': 'top', '1': 'use', '9': 'use'},
                 'Jon': {'8': 'single', '11': 'bomb'}},
    ('sat', 10): {'Aaron': {'2': 'top', '4': '2', '8': '3', '7': '4'},
                  'Magic': {'2': 'single'},
                  'Jon': {'4': 'top', '2': '2'}},
    ('sat', 11): {'Aaron': {'12': 'top', '1': 'use', '3': 'use', '10': 'use'},
                  'Magic': {'1': 'use', '5': 'use', '7': 'use', '9': 'use', '10': 'use', '11': 'use', '14': 'use', '15': 'use',
                            '2': 'against', '12': 'against', '13': 'against'},
                  'Jon': {'1': 'top', '12': 'use', '13': 'use', '10': 'use', '6': 'bomb'}},
    ('sat', 12): {'Aaron': {'2': 'top', '5': '2', '7': '3', '6': '4'},
                  'Magic': {'6': 'top', '5': 'use'},
                  'Jon': {'2': 'top', '5': '2', '7': '3', '4': '4'}},
}

# Racing Dudes official Friday card (Win/Place/Show/Next Best), received Fri 10/30 AM
RD_FRI = {1: ['6', '1', '2', '5'], 2: ['3', '9', '6', '7'], 3: ['6', '2', '3', '8'], 4: ['10', '7', '4', '1'], 5: ['8', '2', '1', '11'], 6: ['4', '3', '5', '9'], 7: ['10', '5', '2', '8'], 8: ['9', '10', '12', '6'], 9: ['5', '7', '6', '3'], 10: ['10', '4', '5', '2']}
for _n, _p in RD_FRI.items():
    CONS.setdefault(('fri', _n), {})['RD'] = dict(zip(_p, ['top', '2', '3', '4']))

ROLE_PTS = {'single': 4.0, 'top': 3.0, '2': 2.0, '3': 1.5, '4': 1.0, 'use': 1.0, 'bomb': 0.8, 'against': 0.0}

SHORT = {'Allowance Optional Claiming (N2X)': 'Alw OC N2X', 'Maiden Special Weight': 'Maiden', 'Thoroughbred Aftercare Alliance S.': 'TAA Stakes',
         'Allowance (N1X)': 'Alw N1X', 'Allowance Optional Claiming (N1X)': 'Alw OC N1X', 'Allowance Optional Claiming (N3X)': 'Alw OC N3X', 'Juvenile Turf Sprint': 'Juv Turf Sprint', 'Juvenile Fillies': 'Juv Fillies', 'Juvenile Fillies Turf': 'Juv Fillies Turf',
         'Juvenile': 'Juvenile', 'Juvenile Turf': 'Juv Turf', 'Filly & Mare Sprint': 'F&M Sprint', 'Turf Sprint': 'Turf Sprint',
         'Dirt Mile': 'Dirt Mile', 'Filly & Mare Turf': 'F&M Turf', 'Sprint': 'Sprint', 'Mile': 'Mile', 'Distaff': 'Distaff',
         'Turf': 'Turf', 'Classic': 'Classic'}


def pp_fig(p):
    if p.get('us') and p.get('beyer') is not None:
        return p['beyer'], 'B'
    if p.get('tf') is not None:
        return p['tf'] - TF_OFFSET, 'TF'
    return None, None


def fig_rating(h, turf, two_yo):
    figs_same, figs_all = [], []
    for p in h['pps'][:8]:
        f, kind = pp_fig(p)
        if f is None or f < 30:
            continue
        same = (p['surf'] == 'T') == turf
        figs_all.append(f)
        if same:
            figs_same.append(f)
    use = figs_same[:3] if figs_same else [f - 4 for f in figs_all[:3]]
    if not use:
        return None, [], 'no figs'
    last, mean = use[0], st.mean(use)
    top2 = st.mean(sorted(use, reverse=True)[:2])
    if two_yo:   # juveniles: weight the latest (improving) and best two
        r = 0.45 * last + 0.40 * top2 + 0.15 * mean
    else:
        r = 0.45 * top2 + 0.35 * mean + 0.20 * last
    note = '' if figs_same else 'off-surface figs'
    # single-race spike (>=8 over the next best of last 3) -> partial regression
    srt = sorted(use, reverse=True)
    if len(srt) >= 2 and srt[0] - srt[1] >= 8:
        r -= 2.0; note = (note + '; ' if note else '') + 'one-off top fig'
    return r, use, note


def run(day, races):
    out = []
    for r in races:
        key = (day, r['num'])
        out_set = OUT.get(key, set())
        turf = r['turf']
        two_yo = r['name'].startswith('Juvenile') or all(re.search(r'\b2 \(', h.get('sex_age') or '') for h in r['horses'])
        hs = []
        for h in r['horses']:
            status = 'run'
            if h['pgm'] in out_set:
                status = SCR_NOTE.get((day, r['num'], h['pgm']), 'AE (not drawn in)')
            fr, figs, note = fig_rating(h, turf, two_yo)
            hs.append({**{k: h.get(k) for k in ['pgm', 'name', 'ml', 'ml_dec', 'jockey', 'trainer', 'jky_win', 'trn_win',
                                                'tfus_early', 'tfus_late', 'days_off', 'bullets', 'records', 'foreign_based',
                                                'sex_age', 'sire', 'trainer_stats', 'works_raw']},
                       'status': status, 'fig_raw': fr, 'figs': figs, 'fig_note': note,
                       'beyers': h['beyers'][:4], 'timeform': h['timeform'][:4],
                       'last_races': [{'date': p['date'], 'track': p.get('track'), 'surf': p['surf'], 'fin': p.get('fin'),
                                       'field': p.get('field'), 'fig': pp_fig(p)[0], 'kind': pp_fig(p)[1],
                                       'odds': p.get('odds')} for p in h['pps'][:5]]})
        run_h = [x for x in hs if x['status'] == 'run']
        # fill missing fig with field 25th pct - 3
        known = sorted(x['fig_raw'] for x in run_h if x['fig_raw'] is not None)
        floor = (known[len(known) // 4] - 3) if known else 80
        for x in run_h:
            if x['fig_raw'] is None:
                x['fig_raw'] = floor; x['fig_note'] = 'no figs (imputed)'
        # --- OptixEQ: oFIG blend + plot velocity ---
        ox = OPTIX.get(key, {})
        pl = PLOTS.get(key, {'std': {}, 'sd': {}})
        for x in run_h:
            info = ox.get(_norm(x['name']))
            x['ofigs'] = [z['ofig'] for z in info['runs']][:3] if info else []
            x['ongs'] = [z['ong'] for z in info['runs']][:3] if info else []
            x['rs'] = info['rs'] if info else None
            ys = [pl[k][x['pgm']][1] for k in ('std', 'sd') if x['pgm'] in pl[k]]
            xs = [pl[k][x['pgm']][0] for k in ('std', 'sd') if x['pgm'] in pl[k]]
            x['opt_vel'] = round(sum(ys) / len(ys), 2) if ys else None
            x['opt_pos'] = round(sum(xs) / len(xs), 2) if xs else None
            x['opt_std'] = pl['std'].get(x['pgm']); x['opt_sd'] = pl['sd'].get(x['pgm'])
            of = [v for v in x['ofigs'] if v]
            if of:
                top2 = st.mean(sorted(of, reverse=True)[:2])
                x['ofig_rating'] = (0.45 * of[0] + 0.40 * top2 + 0.15 * st.mean(of)) if two_yo else (0.45 * top2 + 0.35 * st.mean(of) + 0.20 * of[0])
            else:
                x['ofig_rating'] = None
        diffs = [x['ofig_rating'] - x['fig_raw'] for x in run_h if x['ofig_rating'] is not None and 'imputed' not in x['fig_note']]
        if len(diffs) >= 3:
            off = st.median(diffs)
            for x in run_h:
                if x['ofig_rating'] is not None:
                    x['fig_beyer'] = x['fig_raw']
                    x['fig_raw'] = 0.5 * x['fig_raw'] + 0.5 * (x['ofig_rating'] - off)
                    x['fig_note'] = (x['fig_note'] + '; ' if x['fig_note'] else '') + 'blended with oFIG'
        # pace
        early = sorted([x['tfus_early'] for x in run_h if x['tfus_early']], reverse=True)
        cover = len(early) / max(1, len(run_h))
        thr = (early[0] - 12) if early else 999
        hot = len([e for e in early if e >= thr])
        contested = cover >= 0.7 and hot >= 3 and len(early) >= 2 and early[1] >= early[0] - 5
        lone = cover >= 0.7 and len(early) >= 2 and early[0] - early[1] >= 8
        if not contested: hot = 0
        if cover < 0.7:
            pace_txt = 'Unclear (%d of %d have US pace figs)' % (len(early), len(run_h))
        else:
            pace_txt = ('Contested — %d with early speed' % hot) if contested else ('Lone speed' if lone else 'Honest')
        for x in run_h:
            adj, why = 0.0, []
            e, l = x['tfus_early'], x['tfus_late']
            if e and early:
                if lone and e == early[0] and day == 'fri':   # Saturday: no lone-speed bonus (0 for 3 on Friday)
                    adj += 2.5; why.append('lone speed')
                if hot >= 3 and e >= thr:
                    adj -= 1.5; why.append('speed duel risk')
                if hot >= 3 and l and l >= 100 and e < thr - 15:
                    adj += 1.5; why.append('pace sets up late run')
            d = x['days_off'] or 0
            if d > 150:
                adj -= 3; why.append('%d days off' % d)
            elif d > 100:
                adj -= 1.5; why.append('%d days off' % d)
            jw = x['jky_win'] if x['jky_win'] is not None else 0.15
            tw = x['trn_win'] if x['trn_win'] is not None else 0.15
            adj += max(-1.0, min(1.5, (jw - 0.15) * 10)) + max(-1.0, min(1.0, (tw - 0.15) * 6))
            post = int(''.join(c for c in x['pgm'] if c.isdigit()))
            d_txt = r['dist_text']
            if (not turf and '1Â' in d_txt and post >= 10) or (turf and d_txt.startswith('1 MILE') and post >= 11) \
                    or (turf and '¶' in d_txt and post >= 12):
                adj -= 1.5; why.append('wide post, short run to turn')
            kee = (x['records'] or {}).get('Kee')
            if kee and kee['st'] >= 1 and kee['w'] >= 1:
                adj += 1.0; why.append('won at KEE')
            x['adj'] = round(adj, 1); x['adj_why'] = why
            x['rating'] = x['fig_raw'] + adj
        # softmax
        mx = max(x['rating'] for x in run_h)
        ex = [math.exp((x['rating'] - mx) / T_SOFT) for x in run_h]
        s = sum(ex)
        for x, e in zip(run_h, ex):
            x['p_fig'] = e / s
        # ML
        inv = [1 / (x['ml_dec'] + 1) for x in run_h]
        s2 = sum(inv)
        for x, v in zip(run_h, inv):
            x['p_ml'] = v / s2
        # consensus
        cons = CONS.get(key, {})
        pts = {x['pgm']: 0.0 for x in run_h}
        flags = {x['pgm']: [] for x in run_h}
        for src, picks in cons.items():
            for pg, role in picks.items():
                if pg in pts:
                    pts[pg] += ROLE_PTS[role]
                    flags[pg].append((src, role))
        smooth = 0.35
        tot = sum(v + smooth for v in pts.values())
        for x in run_h:
            x['p_cons'] = (pts[x['pgm']] + smooth) / tot
            x['cons'] = flags[x['pgm']]
        # Optix velocity component
        vels = [x['opt_vel'] for x in run_h if x['opt_vel'] is not None]
        opt_cov = len(vels) / len(run_h)
        if opt_cov >= 0.5:
            med = st.median(vels)
            vv = [x['opt_vel'] if x['opt_vel'] is not None else med for x in run_h]
            m2 = max(vv); ex2 = [math.exp((v - m2) / 0.6) for v in vv]; s4 = sum(ex2)
            for x, e in zip(run_h, ex2): x['p_opt'] = e / s4
            wf, wo, wc, wm = 0.35, 0.15, 0.20, 0.30
        else:
            for x in run_h: x['p_opt'] = None
            wf, wo, wc, wm = W_FIG, 0.0, W_CONS, W_ML
        if not cons:   # no podcast coverage: drop the handicapper weight and rescale
            tot_w = wf + wo + wm
            wf, wo, wm, wc = wf / tot_w, wo / tot_w, wm / tot_w, 0.0
        if not cons:
            for x in run_h: x['p_cons'] = None
        r['weights'] = {'fig': round(wf, 3), 'optix': round(wo, 3), 'cons': round(wc, 3), 'ml': round(wm, 3)}
        top_vel = max(vels) if vels else None
        # blend
        # horses with no figures / no Optix plot: defer to the morning line for that component
        nf = [x for x in run_h if 'imputed' in (x['fig_note'] or '')]
        if nf:
            share = sum(x['p_fig'] for x in nf); mlsh = sum(x['p_ml'] for x in nf)
            for x in nf: x['p_fig'] = x['p_ml'] / mlsh * share if mlsh else x['p_fig']
        if wo:
            no = [x for x in run_h if x['opt_vel'] is None]
            share = sum(x['p_opt'] for x in no); mlsh = sum(x['p_ml'] for x in no)
            for x in no: x['p_opt'] = x['p_ml'] / mlsh * share if mlsh else x['p_opt']
        for x in run_h:
            x['p'] = wf * x['p_fig'] + wc * (x['p_cons'] or 0) + wm * x['p_ml'] + (wo * x['p_opt'] if x['p_opt'] is not None else 0)
        if day == 'sat' and turf:   # Friday: Europeans took 9 of 9 top-3 spots in the BC turf races
            for x in run_h:
                if x.get('foreign_based'):
                    x['p'] *= EURO_TURF_BOOST; x['adj_why'] = x['adj_why'] + ['European on turf (x%.1f)' % EURO_TURF_BOOST]
        s3 = sum(x['p'] for x in run_h)
        for x in run_h:
            x['p'] /= s3
            x['edge'] = x['p'] / x['p_ml'] - 1
            x['fair'] = 1 / x['p'] - 1
            tags = []
            if x['p'] >= 0.35: tags.append('KEY')
            if x['edge'] >= 0.25 and x['ml_dec'] >= 4: tags.append('VALUE')
            if x['ml_dec'] <= 2.5 and x['edge'] <= -0.15: tags.append('FADE')
            if x['ml_dec'] >= 15 and (any(r_ == 'bomb' for _, r_ in x['cons']) or sorted(run_h, key=lambda y: -y['p_fig']).index(x) < 4):
                tags.append('BOMB')
            if any(r_ == 'against' for _, r_ in x['cons']): tags.append('AGAINST')
            if top_vel is not None and x['opt_vel'] == top_vel: tags.append('OPTIX')
            x['tags'] = tags
        ranked = sorted(run_h, key=lambda y: -y['p'])
        for i, x in enumerate(ranked):
            x['rank'] = i + 1
        for x in hs:
            if x['status'] != 'run':
                x.update({'p_opt': None, 'opt_vel': None, 'ofigs': [], 'ongs': [], 'rs': None, 'p': 0, 'p_fig': 0, 'p_cons': 0, 'p_ml': 0, 'edge': 0, 'fair': None, 'tags': [], 'cons': [], 'rank': None, 'adj': 0, 'adj_why': [], 'rating': None})
        r['optix_cov'] = round(opt_cov, 2)
        out.append({'weights': r['weights'], 'covered': bool(cons), 'optix_cov': r['optix_cov'], 'optix_par': pl.get('par'), 'day': day, 'num': r['num'], 'name': r['name'], 'short': SHORT[r['name']], 'dist': r['dist_text'],
                    'turf': turf, 'par': r['beyer_par'], 'post': r['post_time'], 'pace': pace_txt,
                    'field': len(run_h), 'horses': hs})
    return out


if __name__ == '__main__':
    fri = run('fri', json.load(open('fri.json')))
    sat = run('sat', json.load(open('sat.json')))
    allr = fri + sat
    json.dump(allr, open('model.json', 'w'), indent=1, default=str)
    for r in allr:
        print(f"\n{r['day'].upper()} R{r['num']} {r['name']} ({r['field']}) pace: {r['pace']}")
        for x in sorted([h for h in r['horses'] if h['status'] == 'run'], key=lambda y: -y['p']):
            print(f"  {x['pgm']:>2} {x['name'][:22]:22} ML {x['ml']:>5} fig {x['fig_raw']:6.1f} adj {x['adj']:+5.1f}  "
                  f"pFig {x['p_fig']*100:4.1f} pCons {(x['p_cons'] or 0)*100:4.1f} pML {x['p_ml']*100:4.1f} -> {x['p']*100:4.1f}% "
                  f"fair {x['fair']:5.1f} edge {x['edge']*100:+4.0f}% {' '.join(x['tags'])}")
