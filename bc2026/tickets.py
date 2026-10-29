"""Smart-ticket scanner for BC multi-race wagers (Derby Value app rules)."""
import json, math

M = json.load(open('model.json'))
R = {(r['day'], r['num']): r for r in M}

SEQS = [
    ('fri', 'Pick 5', [1, 2, 3, 4, 5]), ('fri', 'Pick 4', [2, 3, 4, 5]), ('fri', 'Pick 5', [3, 4, 5, 6, 7]),
    ('fri', 'Pick 4', [4, 5, 6, 7]), ('fri', 'Pick 6', [5, 6, 7, 8, 9, 10]), ('fri', 'Pick 5', [6, 7, 8, 9, 10]),
    ('fri', 'Pick 4', [7, 8, 9, 10]), ('fri', 'Late Pick 3', [8, 9, 10]), ('fri', 'All-Turf Pick 3', [6, 8, 10]),
] + [('fri', 'Pick 3', [n, n + 1, n + 2]) for n in range(1, 8)] + [
    ('sat', 'Pick 5', [1, 2, 3, 4, 5]), ('sat', 'Pick 4', [2, 3, 4, 5]), ('sat', 'Pick 5', [3, 4, 5, 6, 7]),
    ('sat', 'Pick 4', [4, 5, 6, 7]), ('sat', 'Pick 5', [5, 6, 7, 8, 9]), ('sat', 'Pick 4', [6, 7, 8, 9]),
    ('sat', 'Pick 4', [7, 8, 9, 10]), ('sat', 'Pick 6', [7, 8, 9, 10, 11, 12]), ('sat', 'Pick 5', [8, 9, 10, 11, 12]),
    ('sat', 'Pick 4', [9, 10, 11, 12]), ('sat', 'Late Pick 3', [10, 11, 12]),
    ('sat', 'All-Turf Pick 4', [5, 7, 9, 11]), ('sat', 'All-Dirt Pick 4', [6, 8, 10, 12]), ('sat', 'All-Turf Pick 3', [7, 9, 11]),
] + [('sat', 'Pick 3', [n, n + 1, n + 2]) for n in range(1, 10)]


def runners(r):
    return sorted([h for h in r['horses'] if h['status'] == 'run'], key=lambda h: -h['p'])


def leg_main(r):
    hs = runners(r)
    p = [h['p'] for h in hs]
    if p[0] >= 0.35:
        n, why = 1, 'single (model %.0f%%)' % (p[0] * 100)
    elif p[0] + p[1] >= 0.52:
        n, why = 2, 'pair (top two %.0f%%)' % ((p[0] + p[1]) * 100)
    elif sum(p[:3]) >= 0.55:
        n, why = 3, 'spread 3'
    else:
        n, why = 4, 'wide open — spread 4'
    pick = hs[:n]
    # VALUE add-on: one VALUE horse with >=8% model if not already in (not on singles)
    if n >= 2:
        for h in hs[n:]:
            if 'VALUE' in h['tags'] and h['p'] >= 0.08:
                pick = pick + [h]; why += ' + value add'; break
    return pick, why


def leg_wide(r, main):
    hs = runners(r)
    extra = [h for h in hs if h not in main]
    # add next-best; for singles below 50% add the next horse; add handicapper bomb tags
    add = []
    if len(main) == 1 and main[0]['p'] < 0.5:
        add.append(extra[0])
    elif len(main) > 1:
        add.append(extra[0])
    for h in extra:
        if h not in add and any(role == 'bomb' for _, role in h['cons']):
            add.append(h)
    return main + add


def leg_against(r):
    hs = runners(r)
    top = hs[0]
    if top['p'] >= 0.35 and ('AGAINST' in top['tags'] or 'FADE' in top['tags']):
        rest = [h for h in hs[1:]][:3]
        return rest, 'press against %s' % top['name'].split(' (')[0]
    return leg_main(r)


def summarize(day, name, legs, picker):
    out_legs, combos, cov, cov_ml = [], 1, 1.0, 1.0
    for num in legs:
        r = R[(day, num)]
        if picker == 'main':
            pick, why = leg_main(r)
        elif picker == 'against':
            pick, why = leg_against(r)
        else:
            mp, _ = leg_main(r)
            pick, why = leg_wide(r, mp), 'saver'
        c = sum(h['p'] for h in pick)
        cm = sum(h['p_ml'] for h in pick)
        combos *= len(pick); cov *= c; cov_ml *= cm
        out_legs.append({'race': num, 'short': r['short'], 'pgms': [h['pgm'] for h in pick],
                         'names': [h['name'] for h in pick], 'why': why, 'cov': c, 'cov_ml': cm})
    return {'day': day, 'bet': name, 'races': legs, 'kind': picker, 'legs': out_legs, 'combos': combos,
            'hit': cov, 'hit_ml': cov_ml, 'edge': cov / cov_ml - 1}


tickets = []
for day, name, legs in SEQS:
    tickets.append(summarize(day, name, legs, 'main'))
    tickets.append(summarize(day, name, legs, 'wide'))
    if any(leg_against(R[(day, n)])[1].startswith('press') for n in legs) and len(legs) >= 4:
        tickets.append(summarize(day, name, legs, 'against'))

json.dump(tickets, open('tickets.json', 'w'), indent=1)
for t in tickets:
    legs = ' / '.join(','.join(l['pgms']) for l in t['legs'])
    print(f"{t['day']} {t['bet']:16} R{t['races'][0]}-{t['races'][-1]} {t['kind']:4} {legs:40} combos {t['combos']:4} "
          f"hit {t['hit']*100:5.1f}% (ML {t['hit_ml']*100:5.1f}%) edge {t['edge']*100:+.0f}%")
