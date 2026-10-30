import json, re
M=json.load(open('model.json')); T=json.load(open('tickets.json'))
old=json.load(open('page_data.json'))
NOTES={(r['day'],r['num']):r['note'] for r in old['races'] if r.get('covered',True) and r['num']>=4 or (r['day']=='fri' and r['num']>=6)}
NOTES={k:v for k,v in NOTES.items() if not v.startswith('No podcast')}
PLAYS=json.load(open('plays.json'))
NOTES[('fri',9)] = NOTES[('fri',9)].replace('Gaudreau scratched.','Gaudreau and Earth Song scratched (field of 6).')
NOTES[('fri',8)] = NOTES[('fri',8)].split(' Go for Launch')[0] + " Go for Launch is missing from the Optix program, so it's treated as scratched and Silent Beauty drawn in."
import re as _re
MON={'â':'Jan','á':'Feb','à':'Mar','ß':'Apr','Ü':'May','Þ':'Jun','Û':'Jul','Ý':'Aug','æ':'Sep','å':'Oct','ä':'Nov','ã':'Dec'}
FR={'¦':'.2','§':'.4','¨':'.6','©':'.8'}
_pat=_re.compile(r'(ò)?([âáàßÜÞÛÝæåäã])(\d{1,2})(\S+?)(\s?ú)?\s?(\d)f\s+(\S+)\s+(\d?:?\d\d)([¦§¨©]?)\s+(\S+)\s+(\d+)/(\d+)')
def _fmt(w):
    out=[]
    for m in _pat.finditer(w or ''):
        bul,mon,day,trk,syn,dist,cond,sec,fr,how,rk,of=m.groups()
        turf='ê' in trk; trk=_re.sub(r'tr\.t$',' trn',trk.replace('ê',''))
        out.append(f"{'★ ' if bul else ''}{MON[mon]} {day} {trk} {dist}f{' turf' if turf else (' synth' if syn else '')} {cond} {sec+(FR.get(fr,'') if fr else '')} {how.replace('(d)','')} {rk}/{of}")
    return out[:4]
WORKS={}
for f,dd in [('fri.json','fri'),('sat.json','sat')]:
    for rr in json.load(open(f)):
        for hh in rr['horses']: WORKS[(dd,rr['num'],hh['pgm'])]=_fmt(hh.get('works_raw'))
DM={'1 MILE':'1 mile','1 ¶ MILES':'1½ miles','1° MILES':'1⅛ miles','1± MILES':'1⅜ miles','1² MILES':'1¼ miles','1Â MILES':'1 1/16 miles','5ô Furlongs':'5½ furlongs','6 Furlongs':'6 furlongs','7 Furlongs':'7 furlongs','6ô Furlongs':'6½ furlongs'}
races=[]
for r in M:
    hs=[]
    for h in r['horses']:
        d={k:h.get(k) for k in ['pgm','name','ml','jockey','trainer','status','p','p_fig','p_cons','p_ml','p_opt','edge','fair','tags','rank','tfus_early','tfus_late','days_off','adj_why','fig_note','fig_raw','adj','opt_vel','opt_pos','opt_std','opt_sd','ofigs','ongs','rs']}
        d.update({'cons':[[s,ro] for s,ro in h['cons']], 'figs':h['figs'][:3],
                  'lr':[[x['date'][5:],x['track'],x['surf'],x['fin'],x['field'],x['fig'],x['kind']] for x in h['last_races'][:5]],
                  'kee':(h.get('records') or {}).get('Kee'),'dst':(h.get('records') or {}).get('Dst'),'life':(h.get('records') or {}).get('Life'),
                  'works':WORKS.get((r['day'],r['num'],h['pgm']),[])})
        for k in ['p','p_fig','p_cons','p_ml','p_opt','edge','fair','fig_raw','adj']:
            if isinstance(d[k],float): d[k]=round(d[k],4)
        hs.append(d)
    races.append({k:r[k] for k in ['day','num','name','short','turf','par','pace','field','optix_cov','optix_par']}|{'dist':DM[r['dist']],'post':r['post'].replace(' ET',''),'note':NOTES.get((r['day'],r['num']),'No podcast coverage for this race. The model uses DRF figures, OptixEQ and the morning line only.'),'covered':r['covered'],'weights':r['weights'],'plays':PLAYS[f"{r['day']}-{r['num']}"],'horses':hs})
for t in T:
    for l in t['legs']:
        l['cov']=round(l['cov'],4); l['cov_ml']=round(l['cov_ml'],4)
    t['hit']=round(t['hit'],5); t['hit_ml']=round(t['hit_ml'],5); t['edge']=round(t['edge'],3)
json.dump({'races':races,'tickets':T},open('page_data.json','w'),separators=(',',':'))
t=open('template.html').read()
open('bc_card.html','w').write(t.replace('__DATA__',open('page_data.json').read().replace('</','<\\/')))
print('built')
