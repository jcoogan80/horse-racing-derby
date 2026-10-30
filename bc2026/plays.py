"""Per-race straight & exotic plays from the model (Derby Value rules extended to straight bets)."""
import json
M = json.load(open('model.json'))

def runners(r): return sorted([h for h in r['horses'] if h['status'] == 'run'], key=lambda h: -h['p'])
def nm(h): return h['name'].split(' (')[0]

out = {}
for r in M:
    hs = runners(r); top = hs[0]
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
        A = hs[:3]
        val = next((h for h in hs[3:] if 'VALUE' in h['tags'] and h['p'] >= 0.07), None)
        box = A + ([val] if val else [])
        plays.append({'type': 'Exacta box', 'sel': [h['pgm'] for h in box], 'units': 0.5, 'combos': len(box) * (len(box) - 1),
                      'why': 'Top three in the model' + (f' plus value horse {nm(val)}' if val else '')})
    # --- trifecta
    A = hs[:1] if key else hs[:2]
    Bt = [h for h in hs[:4] if h not in A]
    C = [h for h in hs[:6] if h not in A]
    combos = sum(1 for a in A for b in Bt for c in C if len({a['pgm'], b['pgm'], c['pgm']}) == 3)
    plays.append({'type': 'Trifecta', 'sel': [[h['pgm'] for h in A], [h['pgm'] for h in Bt], [h['pgm'] for h in C]], 'units': 0.5,
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
