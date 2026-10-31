import json, re
M=json.load(open('model.json')); T=json.load(open('tickets.json'))
old=json.load(open('page_data.json'))
NOTES={(r['day'],r['num']):r['note'] for r in old['races'] if r.get('covered',True) and r['num']>=4 or (r['day']=='fri' and r['num']>=6)}
NOTES={k:v for k,v in NOTES.items() if not v.startswith('No podcast')}
PLAYS=json.load(open('plays.json'))
RDN={1:'Memory over Emerging Market, Stowaway, Admiral Dennis',2:'Honor Is Mine over Groves, Niosa, Maitresse',3:'Majik Mooney (10-1) over Canada, Real Goodbar, Roscoe Goose',4:'Campobasso over Cornwall Boss, Ghazaaly, High Camp',5:'Mission Integrity over Kingside, Yacht Master, McCoy'}
for _n,_t in RDN.items(): NOTES[('fri',_n)] = 'Racing Dudes card: ' + _t + '.'
for _n,_t in {6:'Brickyard Belle-Libertango-Mussab-Final Objective',7:'Emphatic-Miss Monica-Domain Expansion-Manuka Honey',8:'Sun Goddess-Amusingly-Domestic Agenda-Alwaysanangel; multi-race 9,10',9:'Hughes-Coach Pope-American History-Salahudin; multi-race 5,7',10:'Folsom Blues-Haffner-How\'s Al Today-Avec Toi'}.items():
    NOTES[('fri',_n)] = NOTES[('fri',_n)] + ' Racing Dudes card: ' + _t + '.'
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
        d={k:h.get(k) for k in ['pgm','name','ml','jockey','trainer','status','p','p_fig','p_cons','p_ml','p_opt','edge','fair','tags','rank','tfus_early','tfus_late','foreign_based','days_off','adj_why','fig_note','fig_raw','adj','opt_vel','opt_pos','opt_std','opt_sd','ofigs','ongs','rs']}
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
RES=json.load(open('results.json'))
NOTE={('fri',1):'4 of 8 scratched',('fri',5):'Dormie drew off by 7 from a 5-horse group'}
for rr in races:
    x=RES.get(rr['day'],{}).get(str(rr['num']))
    if x: rr['result']={'order':x['order'],'pays':x.get('pays',{}),'net_units':x.get('net_units'),'note':NOTE.get((rr['day'],rr['num']))}
MULTI={'fri':[{'label':'R1–3 Pick 3 saver ($190, $1 base)','net':170},{'label':'R6–8 Pick 3 main ($24, $1 base)','net':12},{'label':'R7–10 Pick 4 saver ($54, $1 base)','net':29},{'label':'R6–10 Pick 5 saver ($125, $1 base)','net':25}]}
LESSONS={'fri':['The winner has been in the model top 4 in most races, but the model #1 keeps losing: play wider tickets, two or three on top.',
 'Model singles and favorites keep getting beaten (Niosa 37% unplaced). Single only Sun Goddess and Hughes, and back them up.',
 'Europeans ran 1-2-3-4 in the Juvenile Turf Sprint (Hell of A Spin was model #9). Add Europeans in the turf races.',
 'Long layoffs (High Camp, 230 days) and big form jumps (Dormie by 7) beat us. The layoff penalty will be eased for Saturday.',
 'Price plays from figures and Optix are 0 for 6 on win bets. Straight bets cut to half size for the rest of Friday.',
 'Track fast and fair. No clear speed or post bias yet.'],
 'sat':['Saturday rules come from Friday\'s full results (see the BC 2026 Friday Takeaways doc).',
 'KEY singles: Friday KEYs won 3 of 4. Saturday singles need 40%: Englishman (R8) and Nitrogen (R10). Ways and Means (36%) is paired.',
 'Updated after Sat R3: the model #1 under 35% is back on top with the next two. Putting it underneath missed in R1 (ran 3rd), R2 (won) and R3 (ran 2nd).',
 'Europeans took 9 of 9 top-3 spots in Friday\'s BC turf races. Foreign-based runners get a 1.5x boost on turf and fill the 2nd slot; US horses outside the model top 2 are 3rd-slot only.',
 'The top late-pace dirt horse ran 2nd in 4 of 6 Friday dirt races: it goes in the 2nd slot. The lone-speed bonus is off (0 for 3).',
 'Saver tickets made the money (+228 at $1 base). The saver is now the main ticket, with a tight backup. No adjusted or Against tickets (Magic\'s against calls went 0 for 2).',
 'Straight bets only on an overlaid KEY. Price win bets went 0 for 6+ on Friday.']}
json.dump({'races':races,'tickets':T,'multi':MULTI,'lessons':LESSONS},open('page_data.json','w'),separators=(',',':'))
t=open('template.html').read()
open('bc_card.html','w').write(t.replace('__DATA__',open('page_data.json').read().replace('</','<\\/')))
print('built')
