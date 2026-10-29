import re, json, subprocess, sys
RL = re.compile(r'(\d+(?:\.\d+)?f|-)\s+([A-Z]{2,4}_\d{4}-\d\d-\d\d_\d+|-)\s+(.*?)\s+(EX|[A-F][+-]?|-)\s+(\d{2,3}|-)\s+(\d{1,2}|-)(?:\s+(.*))?$')
HEAD = re.compile(r'^\s{2,}([A-Z0-9\'\.\-& ()]+?(?:\([A-Z]{2,3}\))?)\s{2,}(\d+(?:\.\d+)?)\s+(\d+|FTS)\s+(.*)$')
def parse(fn, pages):
    out = {}
    for race, pgs in pages.items():
        txt = ''.join(subprocess.run(['pdftotext','-f',str(a),'-l',str(a),'-layout',fn,'-'],capture_output=True,text=True).stdout for a in pgs)
        horses = []; cur = None
        for ln in txt.split('\n'):
            if ln.strip().startswith('PN ') or 'Register at optixeq' in ln: continue
            m = HEAD.match(ln)
            if m and not ln.strip().startswith(('J:','T:')) and m.group(1).strip() not in ('KEE',):
                cur = {'name': m.group(1).strip(), 'ml': float(m.group(2)), 'dlr': m.group(3), 'runs': [], 'rs': None}
                horses.append(cur); rest = m.group(4)
            elif cur and ln.strip().startswith(('J:','T:')):
                s = ln.strip()
                key = 'jockey' if s.startswith('J:') else 'trainer'
                mm = re.match(r'[JT]: (.+?)(?:\s{2,}(.*))?$', s)
                cur[key] = mm.group(1).strip(); rest = mm.group(2) or ''
            else:
                continue
            r = RL.search(rest.strip()) if rest else None
            if r:
                tail = (r.group(7) or '').strip()
                run = {'dist': r.group(1), 'key': r.group(2), 'cls': r.group(3).strip(), 'ong': r.group(4), 'ofig': None if r.group(5)=='-' else int(r.group(5)), 'fin': None if r.group(6)=='-' else int(r.group(6))}
                cur['runs'].append(run)
                rs = re.search(r'\b(EP|PC|E|P|C|S|NA)\s*$', tail)
                if rs and not cur['rs']: cur['rs'] = rs.group(1)
        out[race] = horses
    return out
if __name__ == '__main__':
    fri = parse('657beffe-OptixPlot___KEE_R10_2026-10-30.PDF', {1:[1,2],2:[3,4],3:[5,6],4:[7,8],5:[9,10],6:[11,12],7:[13,14],8:[15,16],9:[17,18],10:[19,20]})
    sat = parse('a5e135d9-OptixPlot___KEE_R12_2026-10-31.PDF', {1:[1,2],2:[3,4],3:[5,6],4:[7,8],5:[9,10],6:[11,12],7:[13,14],8:[15,16],9:[17,18],10:[19,20],11:[21,22],12:[23,24]})
    json.dump({'fri':fri,'sat':sat}, open('optix.json','w'), indent=1)
    for d,x in [('fri',fri),('sat',sat)]:
        for r,hs in x.items():
            print(d, r, len(hs))
            for h in hs: print('   ', h['name'][:24].ljust(24), h['ml'], h['dlr'], h['rs'], [(z['ong'], z['ofig'], z['fin']) for z in h['runs']])
