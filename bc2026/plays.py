"""Per-race straight & exotic plays from the model (Derby Value rules extended to straight bets)."""
import json
M = json.load(open('model.json'))

def runners(r): return sorted([h for h in r['horses'] if h['status'] == 'run'], key=lambda h: -h['p'])
def nm(h): return h['name'].split(' (')[0]

ADJ = {('fri', n) for n in (7, 8, 9, 10)}   # races adjusted after Friday R1-R6

def closer(r, hs):
    """Dirt: best late-pace runner (TFUS late) with a live chance; ran 2nd in 4 of 6 Friday dirt races."""
    if r['turf']: return None
    c = [h for h in hs if h.get('tfus_late') and h['p'] >= 0.03]
    return max(c, key=lambda h: h['tfus_late']) if c else None


def sat_plays(r, hs):
    """Saturday rules from Friday's results (see BC 2026 Friday Takeaways doc)."""
    top = hs[0]; key = top['p'] >= 0.35; plays = []; notes = []
    over = lambda h: h['ml_dec'] >= 1.33 * h['fair']
    cl = closer(r, hs)
    euros = [h for h in hs if h.get('foreign_based') and h['p'] >= 0.04]
    val = [h for h in hs[1:8] if 'VALUE' in h['tags'] and h['p'] >= 0.05]
    def add(lst, extra):
        for h in extra:
            if h and h not in lst: lst.append(h)
        return lst
    def ok_mid(h):   # on turf, US horses outside the model top 2 go only in the 3rd slot
        return (not r['turf']) or h.get('foreign_based') or hs.index(h) < 2
    # straight: only a KEY that is an overlay
    if key and over(top):
        plays.append({'type': 'Win', 'sel': [top['pgm']], 'units': 1, 'combos': 1,
                      'why': f"{nm(top)}: KEY at {top['p']*100:.0f}%, fair {top['fair']:.1f}-1 vs ML {top['ml']} (only if odds hold)"})
    if key:
        B = [h for h in hs[1:5] if ok_mid(h)]
        B = add(B, [cl] + val[:1] + (euros[:2] if r['turf'] else []))
        B = [h for h in B if h is not top]
        plays.append({'type': 'Exacta', 'sel': [[top['pgm']], [h['pgm'] for h in B]], 'units': 1, 'combos': len(B),
                      'why': f"Key {nm(top)} over " + ', '.join(nm(h) for h in B)})
        S = hs[1:3]
        plays.append({'type': 'Exacta (saver)', 'sel': [[h['pgm'] for h in S], [top['pgm']]], 'units': 0.5, 'combos': len(S),
                      'why': f"{nm(top)} 2nd behind the two most likely upsetters"})
        A = [top]; Bt = list(B); C = add(list(B), hs[1:7] + euros[:3])
        C = [h for h in C if h is not top]
    else:
        # Sat R1-R3: putting the non-KEY model #1 underneath missed (it ran 3rd, 1st, 2nd). It goes back on top.
        W = [h for h in hs[1:5] if ok_mid(h)]
        if r['turf']: W = add([h for h in euros if h is not top][:3], W)
        T3 = [top] + [h for h in W if h is not top][:2]
        B = add(list(T3), [cl] + val[:1])[:5]
        ex = sum(1 for a in T3 for b in B if a is not b)
        plays.append({'type': 'Exacta part-wheel', 'sel': [[h['pgm'] for h in T3], [h['pgm'] for h in B]], 'units': 0.5, 'combos': ex,
                      'why': 'Model top three over the same' + (' plus the best closer' if cl and cl in B and cl not in T3 else '') + (' and VALUE' if any(v in B and v not in T3 for v in val[:1]) else '')})
        A = T3
        Bt = list(B)
        C = add(list(Bt), [h for h in hs if h not in Bt][:3])[:7]
    combos = sum(1 for a in A for b in Bt for c in C if len({a['pgm'], b['pgm'], c['pgm']}) == 3)
    u = 0.5 if combos <= 24 else 0.2
    plays.append({'type': 'Trifecta', 'sel': [[h['pgm'] for h in A], [h['pgm'] for h in Bt], [h['pgm'] for h in C]], 'units': u,
                  'combos': combos, 'why': ('KEY on top' if key else 'model top three on top') + '; VALUE and ' + ('Europeans' if r['turf'] else 'the best closer') + ' underneath'})
    if cl and cl is not top: notes.append(f"Best closer: {nm(cl)} ({cl['ml']}). On Friday the top late-pace dirt horse ran 2nd in 4 of 6 races; it's in the 2nd slot.")
    if r['turf'] and euros: notes.append('Europeans took 9 of 9 top-3 spots in Friday\'s BC turf races; foreign-based runners get a 1.5x boost here and fill the 2nd slot. US horses outside the model top 2 are 3rd-slot only.')
    if not key: notes.append(f"No KEY: model #1 {nm(top)} ({top['p']*100:.0f}%) is back on top with the next two (the underneath rule missed in Sat R1-R3).")
    elif top['p'] >= 0.40: notes.append(f"KEY single for multi-race tickets: {nm(top)} at {top['p']*100:.0f}% (Friday KEYs won 3 of 4).")
    else: notes.append(f"{nm(top)} is a KEY at {top['p']*100:.0f}% but under the 40% single line: paired in multi-race tickets.")
    if not any(p['type'] == 'Win' for p in plays): notes.append('No straight bet (Saturday rule: win bets only on an overlaid KEY). Use exotics and multi-race savers.')
    if any(ro == 'against' for h in hs for _, ro in h['cons']): notes.append("Magic's against calls went 0 for 2 Friday; no Against tickets Saturday.")
    return plays, notes


out = {}
for r in M:
    hs = runners(r); top = hs[0]
    if r['day'] == 'sat':
        plays, notes = sat_plays(r, hs)
        fts = [h for h in hs if 'imputed' in (h.get('fig_note') or '')]
        if fts: notes.append(f"{len(fts)} runner(s) without speed figures are priced off the morning line; watch the board and paddock.")
        out[f"sat-{r['num']}"] = {'plays': plays, 'notes': notes, 'units': round(sum(p['units'] * p['combos'] for p in plays), 2)}
        continue
    fav = min(hs, key=lambda h: h['ml_dec'] if h.get('ml_dec') else 99)
    plays, notes = [], []
    key = top['p'] >= 0.35
    # --- straight bets
    nfts = sum(1 for h in hs if 'imputed' in (h.get('fig_note') or ''))
    over = lambda h: h['ml_dec'] >= 1.33 * h['fair']      # ML odds at least a third above fair odds
    for h in hs:
        if 'VALUE' in h['tags'] and h['p'] >= 0.10 and over(h):
            u = 2 if (h['edge'] >= 0.75 and h['p'] >= 0.15 and nfts < 3) else 1
            plays.append({'type': 'Win', 'sel': [h['pgm']], 'units': u, 'combos': 1,
                          'why': f"{nm(h)}: model {h['p']*100:.0f}% (fair {h['fair']:.1f}-1) vs ML {h['ml']}"})
        elif h['ml_dec'] >= 12 and h['p'] >= 0.06 and ('VALUE' in h['tags'] or 'BOMB' in h['tags']):
            plays.append({'type': 'Win/Place', 'sel': [h['pgm']], 'units': 0.5, 'combos': 2,
                          'why': f"{nm(h)}: price play, model {h['p']*100:.0f}% at {h['ml']}"})
    if key and over(top) and not any(p['sel'] == [top['pgm']] for p in plays):
        plays.append({'type': 'Win', 'sel': [top['pgm']], 'units': 1, 'combos': 1,
                      'why': f"{nm(top)}: KEY at {top['p']*100:.0f}%, fair {top['fair']:.1f}-1 vs ML {top['ml']} (only if odds hold)"})
    # --- exacta
    if key:
        B = hs[1:4]
        plays.append({'type': 'Exacta', 'sel': [[top['pgm']], [h['pgm'] for h in B]], 'units': 1, 'combos': len(B),
                      'why': f"Key {nm(top)} over the next three"})
        plays.append({'type': 'Exacta (saver)', 'sel': [[h['pgm'] for h in B[:2]], [top['pgm']]], 'units': 0.5, 'combos': 2,
                      'why': f"{nm(top)} 2nd behind the two most likely upsetters"})
    else:
        A = hs[:4] if (r['day'], r['num']) in ADJ else hs[:3]
        val = next((h for h in hs[len(A):] if 'VALUE' in h['tags'] and h['p'] >= 0.07), None)
        box = A + ([val] if val else [])
        plays.append({'type': 'Exacta box', 'sel': [h['pgm'] for h in box], 'units': 0.5, 'combos': len(box) * (len(box) - 1),
                      'why': 'Top three in the model' + (f' plus value horse {nm(val)}' if val else '')})
    # --- trifecta
    adj = (r['day'], r['num']) in ADJ
    A = hs[:1] if key else hs[:2]
    Bt = [h for h in hs[:4] if h not in A]
    C = [h for h in hs[:6] if h not in A]
    if adj:   # today's lesson: two or three on top, top horses can also run 2nd/3rd, Europeans added on turf
        A = hs[:2] if key else hs[:3]
        Bt = hs[:5]
        C = hs[:7]
        if r['turf']:
            for h in [x for x in hs[:9] if x.get('foreign_based')][:2]:
                if h not in Bt: Bt.append(h)
                if h not in C: C.append(h)
    combos = sum(1 for a in A for b in Bt for c in C if len({a['pgm'], b['pgm'], c['pgm']}) == 3)
    plays.append({'type': 'Trifecta', 'sel': [[h['pgm'] for h in A], [h['pgm'] for h in Bt], [h['pgm'] for h in C]], 'units': (0.2 if adj and combos > 24 else 0.5),
                  'combos': combos, 'why': 'A / B / C part-wheel from the model ranks'})
    # --- notes
    if 'FADE' in fav['tags']:
        notes.append(f"Favorite {nm(fav)} ({fav['ml']}) rates below its price: lean against it on top.")
    elif 'AGAINST' in fav['tags']:
        who = ', '.join(s for s, ro in fav['cons'] if ro == 'against')
        if fav is top:
            notes.append(f"{who} is against favorite {nm(fav)} ({fav['ml']}), but the model still has it on top; the Against tickets cover that view.")
        else:
            notes.append(f"{who} is against favorite {nm(fav)} ({fav['ml']}), and the model also rates it below the top choice.")
    if not any(p['type'].startswith('Win') for p in plays):
        notes.append("No straight bet: nothing beats the morning line by enough. Use this race for exotics and multi-race spreads.")
    if (r['day'], r['num']) in ADJ:
        notes.append('Adjusted after Friday R1–R6: favorites and model singles lost 5 of 6, Europeans ran 1-2-3-4 in the turf sprint. Trifecta now uses two or three on top' + (', with Europeans added underneath.' if r['turf'] else '.'))
    fts = [h for h in hs if 'imputed' in (h.get('fig_note') or '')]
    if fts:
        notes.append(f"{len(fts)} runner(s) without speed figures (first-time starters or no US/Euro figs) are priced off the morning line; watch the board and paddock.")
    cost = sum(p['units'] * p['combos'] for p in plays)
    out[f"{r['day']}-{r['num']}"] = {'plays': plays, 'notes': notes, 'units': round(cost, 2)}
json.dump(out, open('plays.json', 'w'), indent=1)
for k, v in out.items():
    print(k, v['units'], 'u')
    for p in v['plays']: print('   ', p['type'], p['sel'], p['units'], 'u x', p['combos'], '-', p['why'])
    for n in v['notes']: print('    *', n)
