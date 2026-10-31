// =============================================================
//  KEE BC TAB — Breeders' Cup 2026 at Keeneland
//  Loads data/kee_bc_2026.json (model output from bc2026/ pipeline),
//  applies scratches from data/scratches.json (ScratchWatcher, track KEE)
//  plus any scratches tapped in on this device, then re-prices each race
//  and rebuilds plays + multi-race tickets with the Smart Scanner rules.
// =============================================================
const KBC = { data: null, kee: null, watcher: null, day: 'fri', view: 'races', race: null, tf: 'big', base: 0.5, manual: {}, loading: false, live: null, liveErr: null, livePolls: 0 };
const KBC_SC = {1:['#d0202e','#fff'],2:['#ffffff','#111'],3:['#1f4fbf','#fff'],4:['#f6d32d','#111'],5:['#1e7b3a','#fff'],6:['#111','#f6d32d'],
  7:['#f28c1b','#111'],8:['#f6a1c0','#111'],9:['#2bc3c8','#111'],10:['#6c2c91','#fff'],11:['#9aa0a6','#b4141d'],12:['#a6d84a','#111'],
  13:['#6b4423','#fff'],14:['#7b1e2b','#f6d32d'],15:['#c3b091','#111'],16:['#7fb8e6','#b4141d'],17:['#1c2b5a','#fff'],18:['#2f6b3a','#f6d32d']};
const KBC_SRC = { Aaron: 'A', Magic: 'M', Jon: 'J', RD: 'RD' };
const KBC_ROLE = { top: 'top', single: 'single', '2': '2nd', '3': '3rd', '4': '4th', use: 'use', bomb: 'bomb', against: 'against' };

function kbcEsc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
function kbcPct(p, d = 0) { return (p * 100).toFixed(d) + '%'; }
function kbcOdds(f) { if (f == null || !isFinite(f)) return '—'; return (f < 1 ? f.toFixed(2).replace(/^0/, '') : (f >= 10 ? Math.round(f) : f.toFixed(1))) + '-1'; }
function kbcChip(pgm) { const c = KBC_SC[parseInt(pgm, 10)] || ['#777', '#fff']; return `<span class="kbc-sc" style="background:${c[0]};color:${c[1]}">${kbcEsc(pgm)}</span>`; }
function kbcMlDec(ml) { const m = String(ml).split('-'); return m.length === 2 ? (+m[0]) / (+m[1]) : 5; }
function kbcName(h) { return h.name.split(' (')[0]; }

function kbcLoadManual() { try { KBC.manual = JSON.parse(localStorage.getItem('kbc-manual') || '{}'); } catch (e) { KBC.manual = {}; } }
function kbcSaveManual() { try { localStorage.setItem('kbc-manual', JSON.stringify(KBC.manual)); } catch (e) {} }

async function kbcInit() {
  if (KBC.data || KBC.loading) { kbcRender(); return; }
  KBC.loading = true; kbcLoadManual();
  try {
    const r = await fetch('data/kee_bc_2026.json?t=' + Date.now());
    KBC.data = await r.json();
  } catch (e) {
    document.getElementById('kbc-body').innerHTML = '<div class="kbc-empty">Could not load data/kee_bc_2026.json. Check your connection and reopen the tab.</div>';
    KBC.loading = false; return;
  }
  try { const r = await fetch('dashboard_data.json?t=' + Date.now()); const d = await r.json(); KBC.kee = (d.sequences || {}).KEE || null; } catch (e) {}
  await kbcLoadWatcher(); await kbcLivePoll(true);
  // default day: Saturday once Friday's card is over (local date)
  const today = new Date().toISOString().slice(0, 10);
  if (today >= KBC.data.meta.dates.sat) KBC.day = 'sat';
  KBC.loading = false;
  kbcRender();
  setInterval(async () => { if (document.getElementById('tab-keebc').classList.contains('active')) { await kbcLoadWatcher(); kbcRender(); } }, 120000);
  setInterval(async () => { if (document.getElementById('tab-keebc').classList.contains('active')) { await kbcLivePoll(false); kbcRender(); } }, 60000);
}

// ── Live tote odds (Netlify function kee-live → TwinSpires program API) ──
// Polls every 60 s while the tab is open; full card (scratches) every 5th poll, otherwise only races within 20 MTP.
function kbcOddsDec(s) {
  if (s == null) return null; s = String(s).trim().toLowerCase();
  if (!s || s === 'scr' || s === '-') return null;
  if (s === 'even' || s === 'evn' || s === 'e') return 1;
  const m = s.match(/^(\d+(?:\.\d+)?)\s*[\/\-]\s*(\d+(?:\.\d+)?)$/); if (m) return +m[2] ? +m[1] / +m[2] : null;
  return isFinite(+s) ? +s : null;
}
async function kbcLivePoll(force) {
  const today = new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
  if (!KBC.data || !Object.values(KBC.data.meta.dates).includes(today)) return;   // only on race days
  const full = force || !KBC.live || KBC.livePolls % 5 === 0;
  KBC.livePolls++;
  try {
    const r = await fetch('/.netlify/functions/kee-live' + (full ? '?full=1' : '') + (full ? '&' : '?') + 't=' + Date.now());
    const d = await r.json();
    if (d.error) throw new Error(d.error);
    const prev = KBC.live || { entries: {} };
    d.entries = Object.assign({}, full ? {} : prev.entries, d.entries);
    KBC.live = d; KBC.liveErr = null;
  } catch (e) { KBC.liveErr = e.message; }
}
function kbcLiveRace(day, num) {
  const L = KBC.live; if (!L) return null;
  const rr = (L.races || []).find(x => x.num === num && x.date === KBC.data.meta.dates[day]);
  if (!rr) return null;
  const es = L.entries[num]; const by = {};
  if (Array.isArray(es)) es.forEach(e => { by[e.pgm] = e; });
  return { ...rr, by };
}

async function kbcLoadWatcher() {
  try { const r = await fetch('data/scratches.json?t=' + Date.now()); KBC.watcher = await r.json(); } catch (e) { KBC.watcher = null; }
}

// Scratched program numbers for a race: watcher (if it's for KEE and this day) + manual taps
function kbcScratched(day, num) {
  const out = new Set();
  const w = KBC.watcher, date = KBC.data.meta.dates[day];
  if (w && w.track === 'KEE' && w.date === date) {
    (w.scratches || []).forEach(s => { if (+s.race === num && /scratch/i.test(s.change_type || '')) out.add(String(s.pgm).replace(/^0+/, '')); });
  }
  const lr = kbcLiveRace(day, num);
  if (lr) Object.values(lr.by).forEach(e => { if (e.scr) out.add(e.pgm); });
  Object.keys(KBC.manual).forEach(k => { const [d, n, p] = k.split('|'); if (d === day && +n === num && KBC.manual[k]) out.add(p); });
  return out;
}

// Re-price a race after scratches: drop scratched runners, renormalize model and ML, re-tag.
function kbcPrice(r) {
  const scr = kbcScratched(r.day, r.num);
  const live = r.horses.filter(h => h.status === 'run' && !scr.has(h.pgm)).map(h => ({ ...h, ml_dec: kbcMlDec(h.ml) }));
  const sp = live.reduce((a, h) => a + h.p, 0) || 1, sm = live.reduce((a, h) => a + h.p_ml, 0) || 1;
  const lr = kbcLiveRace(r.day, r.num);
  live.forEach(h => {
    const le = lr && lr.by[h.pgm]; h.live = le ? le.live : null; h.live_dec = kbcOddsDec(h.live); h.live_fav = le ? le.fav : false;
    h.p = h.p / sp; h.p_ml = h.p_ml / sm; h.edge = h.p / h.p_ml - 1; h.fair = 1 / h.p - 1;
    const keep = (h.tags || []).filter(t => ['BOMB', 'AGAINST', 'OPTIX'].includes(t));
    const t = [];
    if (h.p >= 0.35) t.push('KEY');
    if (h.edge >= 0.25 && h.ml_dec >= 4) t.push('VALUE');
    if (h.ml_dec <= 2.5 && h.edge <= -0.15) t.push('FADE');
    if (h.live_dec != null && h.live_dec >= 1.33 * h.fair) t.push('OVERLAY');
    h.tags = t.concat(keep);
  });
  live.sort((a, b) => b.p - a.p);
  return { live, scr, lr };
}

// ── Plays (port of bc2026/plays.py) ──
function kbcPlays(r, live) {
  const plays = [], notes = [];
  if (!live.length) return { plays, notes, units: 0 };
  if (r.day === 'sat') return kbcSatPlays(r, live);
  const top = live[0], key = top.p >= 0.35;
  const fav = live.reduce((a, h) => (h.ml_dec < a.ml_dec ? h : a), live[0]);
  const nfts = live.filter(h => /imputed/.test(h.fig_note || '')).length;
  const over = h => h.ml_dec >= 1.33 * h.fair;
  live.forEach(h => {
    if (h.tags.includes('VALUE') && h.p >= 0.10 && over(h)) {
      const u = (h.edge >= 0.75 && h.p >= 0.15 && nfts < 3) ? 2 : 1;
      plays.push({ type: 'Win', sel: [h.pgm], units: u, combos: 1, why: `${kbcName(h)}: model ${kbcPct(h.p)} (fair ${kbcOdds(h.fair)}) vs ML ${h.ml}` });
    } else if (h.ml_dec >= 12 && h.p >= 0.06 && (h.tags.includes('VALUE') || h.tags.includes('BOMB'))) {
      plays.push({ type: 'Win/Place', sel: [h.pgm], units: 0.5, combos: 2, why: `${kbcName(h)}: price play, model ${kbcPct(h.p)} at ${h.ml}` });
    }
  });
  if (key && over(top) && !plays.some(p => p.sel[0] === top.pgm)) plays.push({ type: 'Win', sel: [top.pgm], units: 1, combos: 1, why: `${kbcName(top)}: KEY at ${kbcPct(top.p)}, fair ${kbcOdds(top.fair)} vs ML ${top.ml} (only if odds hold)` });
  if (key) {
    const B = live.slice(1, 4);
    plays.push({ type: 'Exacta', sel: [[top.pgm], B.map(h => h.pgm)], units: 1, combos: B.length, why: `Key ${kbcName(top)} over the next three` });
    plays.push({ type: 'Exacta saver', sel: [B.slice(0, 2).map(h => h.pgm), [top.pgm]], units: 0.5, combos: Math.min(2, B.length), why: `${kbcName(top)} 2nd behind the two most likely upsetters` });
  } else {
    const A = live.slice(0, 3); const val = live.slice(3).find(h => h.tags.includes('VALUE') && h.p >= 0.07);
    const box = val ? A.concat([val]) : A;
    plays.push({ type: 'Exacta box', sel: box.map(h => h.pgm), units: 0.5, combos: box.length * (box.length - 1), why: 'Top three in the model' + (val ? ` plus value horse ${kbcName(val)}` : '') });
  }
  const A = key ? live.slice(0, 1) : live.slice(0, 2);
  const Bt = live.slice(0, 4).filter(h => !A.includes(h)), C = live.slice(0, 6).filter(h => !A.includes(h));
  let tc = 0; A.forEach(a => Bt.forEach(b => C.forEach(c => { if (new Set([a.pgm, b.pgm, c.pgm]).size === 3) tc++; })));
  plays.push({ type: 'Trifecta', sel: [A.map(h => h.pgm), Bt.map(h => h.pgm), C.map(h => h.pgm)], units: 0.5, combos: tc, why: 'A / B / C part-wheel from the model ranks' });
  if (fav.tags.includes('FADE')) notes.push(`Favorite ${kbcName(fav)} (${fav.ml}) rates below its price: lean against it on top.`);
  else if (fav.tags.includes('AGAINST')) notes.push(`${(fav.cons || []).filter(c => c[1] === 'against').map(c => c[0]).join(', ')} is against favorite ${kbcName(fav)}; the Against tickets cover that view.`);
  if (!plays.some(p => p.type.startsWith('Win'))) notes.push('No straight bet: nothing beats the morning line by enough. Use this race in exotics and multi-race spreads.');
  if (nfts) notes.push(`${nfts} runner(s) without speed figures are priced off the morning line; watch the board and paddock.`);
  return { plays, notes, units: +plays.reduce((a, p) => a + p.units * p.combos, 0).toFixed(2) };
}

// ── Saturday rules (from Friday's results; port of plays.py sat_plays / tickets.py leg_sat_*) ──
function kbcCloser(r, live) {
  if (r.turf) return null;
  const c = live.filter(h => h.tfus_late && h.p >= 0.03);
  return c.length ? c.reduce((a, h) => (h.tfus_late > a.tfus_late ? h : a), c[0]) : null;
}
function kbcSatPlays(r, live) {
  const plays = [], notes = [];
  const top = live[0], key = top.p >= 0.35, over = h => (h.live_dec != null ? h.live_dec : h.ml_dec) >= 1.33 * h.fair;
  const cl = kbcCloser(r, live);
  const euros = live.filter(h => h.foreign_based && h.p >= 0.04);
  const val = live.slice(1, 8).filter(h => h.tags.includes('VALUE') && h.p >= 0.05);
  const add = (lst, extra) => { extra.forEach(h => { if (h && !lst.includes(h)) lst.push(h); }); return lst; };
  const okMid = h => !r.turf || h.foreign_based || live.indexOf(h) < 2;
  const nm = kbcName;
  if (key && over(top)) plays.push({ type: 'Win', sel: [top.pgm], units: 1, combos: 1, why: `${nm(top)}: KEY at ${kbcPct(top.p)}, fair ${kbcOdds(top.fair)} vs ${top.live ? 'live ' + top.live : 'ML ' + top.ml} (only if odds hold)` });
  let A, Bt, C;
  if (key) {
    let B = live.slice(1, 5).filter(okMid);
    B = add(B, [cl].concat(val.slice(0, 1), r.turf ? euros.slice(0, 2) : [])).filter(h => h !== top);
    plays.push({ type: 'Exacta', sel: [[top.pgm], B.map(h => h.pgm)], units: 1, combos: B.length, why: `Key ${nm(top)} over ` + B.map(nm).join(', ') });
    const S = live.slice(1, 3);
    plays.push({ type: 'Exacta (saver)', sel: [S.map(h => h.pgm), [top.pgm]], units: 0.5, combos: S.length, why: `${nm(top)} 2nd behind the two most likely upsetters` });
    A = [top]; Bt = B.slice(); C = add(B.slice(), live.slice(1, 7).concat(euros.slice(0, 3))).filter(h => h !== top);
  } else {
    let W = live.slice(1, 5).filter(okMid);
    if (r.turf) W = add(euros.filter(h => h !== top).slice(0, 3), W);
    W = add(W.slice(0, 3), val.slice(0, 1)).filter(h => h !== top).slice(0, 4);
    plays.push({ type: 'Exacta', sel: [W.map(h => h.pgm), [top.pgm]], units: 1, combos: W.length, why: `Model #1 ${nm(top)} underneath: ` + W.map(nm).join(', ') + ` over ${nm(top)}` });
    plays.push({ type: 'Exacta (saver)', sel: [[top.pgm], W.map(h => h.pgm)], units: 0.5, combos: W.length, why: `Smaller saver in case ${nm(top)} does win` });
    A = W.slice(0, 2);
    Bt = add([top].concat(W.slice(0, 3)), [cl]).slice(0, 5);
    C = add(Bt.slice(), live.filter(h => !Bt.includes(h)).slice(0, 3)).slice(0, 7);
  }
  let tc = 0; A.forEach(a => Bt.forEach(b => C.forEach(c => { if (new Set([a.pgm, b.pgm, c.pgm]).size === 3) tc++; })));
  plays.push({ type: 'Trifecta', sel: [A.map(h => h.pgm), Bt.map(h => h.pgm), C.map(h => h.pgm)], units: tc <= 24 ? 0.5 : 0.2, combos: tc,
    why: (key ? 'KEY on top' : `${nm(top)} 2nd/3rd only`) + '; VALUE and ' + (r.turf ? 'Europeans' : 'the best closer') + ' underneath' });
  if (cl && cl !== top) notes.push(`Best closer: ${nm(cl)} (${cl.ml}). On Friday the top late-pace dirt horse ran 2nd in 4 of 6 races; it's in the 2nd slot.`);
  if (r.turf && euros.length) notes.push("Europeans took 9 of 9 top-3 spots in Friday's BC turf races; foreign-based runners get a 1.5x boost here and fill the 2nd slot. US horses outside the model top 2 are 3rd-slot only.");
  if (!key) notes.push(`No KEY: model #1 ${nm(top)} (${kbcPct(top.p)}) goes underneath. Non-KEY model #1s went 0 for 6 on top Friday but 4 ran 2nd or 3rd.`);
  else if (top.p >= 0.40) notes.push(`KEY single for multi-race tickets: ${nm(top)} at ${kbcPct(top.p)} (Friday KEYs won 3 of 4).`);
  else notes.push(`${nm(top)} is a KEY at ${kbcPct(top.p)} but under the 40% single line: paired in multi-race tickets.`);
  const ov = live.slice(0, 6).filter(h => h.tags.includes('OVERLAY'));
  if (ov.length) notes.push('Live overlays (board ≥ 1.33× fair): ' + ov.map(h => `${nm(h)} ${h.live} (fair ${kbcOdds(h.fair)})`).join(', ') + '. Use them more in the exotics; a win bet only if it is the KEY.');
  if (!plays.some(p => p.type === 'Win')) notes.push('No straight bet (Saturday rule: win bets only on an overlaid KEY). Use exotics and multi-race savers.');
  const nfts = live.filter(h => /imputed/.test(h.fig_note || '')).length;
  if (nfts) notes.push(`${nfts} runner(s) without speed figures are priced off the morning line; watch the board and paddock.`);
  return { plays, notes, units: +plays.reduce((a, p) => a + p.units * p.combos, 0).toFixed(2) };
}
function kbcLegSatTight(live) {
  if (live[0].p < 0.40 && live[0].p >= 0.35) {
    let pick = live.slice(0, 2), why = `pair (KEY under 40%: ${kbcPct(live[0].p)})`;
    const v = live.slice(2).find(h => h.tags.includes('VALUE') && h.p >= 0.08); if (v) { pick = pick.concat([v]); why += ' + value add'; }
    return { pick, why };
  }
  return kbcLegMain(live);
}
function kbcLegSatMain(r, live) {
  if (live[0].p >= 0.40) return { pick: live.slice(0, 1), why: `single (model ${kbcPct(live[0].p)})` };
  const base = kbcLegSatTight(live); let why = base.why; const pick = base.pick.slice();
  const extra = live.filter(h => !pick.includes(h));
  if (extra[0]) pick.push(extra[0]);
  if (r.turf) { const e = live.slice(0, 8).find(h => h.foreign_based && !pick.includes(h)); if (e) { pick.push(e); why += ' + Euro'; } }
  extra.forEach(h => { if (!pick.includes(h) && (h.cons || []).some(c => c[1] === 'bomb')) pick.push(h); });
  return { pick: pick.slice(0, 6), why: why.split(' (')[0].replace('single', 'pair') + ' + saver' };
}

// ── Tickets (port of bc2026/tickets.py) ──
function kbcLegMain(live) {
  const p = live.map(h => h.p); let n, why;
  if (p[0] >= 0.35) { n = 1; why = `single (model ${kbcPct(p[0])})`; }
  else if (p[0] + (p[1] || 0) >= 0.52) { n = 2; why = `pair (top two ${kbcPct(p[0] + p[1])})`; }
  else if (p.slice(0, 3).reduce((a, b) => a + b, 0) >= 0.55) { n = 3; why = 'spread 3'; }
  else { n = 4; why = 'wide open — spread 4'; }
  let pick = live.slice(0, n);
  if (n >= 2) { const v = live.slice(n).find(h => h.tags.includes('VALUE') && h.p >= 0.08); if (v) { pick = pick.concat([v]); why += ' + value add'; } }
  return { pick, why };
}
function kbcLegWide(live, main) {
  const extra = live.filter(h => !main.includes(h)); const add = [];
  if ((main.length === 1 && main[0].p < 0.5) || main.length > 1) { if (extra[0]) add.push(extra[0]); }
  extra.forEach(h => { if (!add.includes(h) && (h.cons || []).some(c => c[1] === 'bomb')) add.push(h); });
  return main.concat(add);
}
function kbcLegAgainst(live) {
  const top = live[0];
  if (top && top.p >= 0.35 && (top.tags.includes('AGAINST') || top.tags.includes('FADE'))) return { pick: live.slice(1, 4), why: `press against ${kbcName(top)}`, pressed: true };
  return { ...kbcLegMain(live), pressed: false };
}
function kbcTickets(day) {
  const seqs = []; const seen = new Set();
  KBC.data.tickets.filter(t => t.day === day).forEach(t => { const k = t.bet + '|' + t.races.join('-'); if (!seen.has(k)) { seen.add(k); seqs.push({ bet: t.bet, races: t.races }); } });
  const byNum = {}, raceBy = {}; KBC.data.races.filter(r => r.day === day).forEach(r => { byNum[r.num] = kbcPrice(r).live; raceBy[r.num] = r; });
  return seqs.map(s => {
    const kinds = day === 'sat' ? ['main', 'tight'] : ['main', 'wide'];
    if (day !== 'sat' && s.races.length >= 4 && s.races.some(n => kbcLegAgainst(byNum[n]).pressed)) kinds.push('against');
    const vars = kinds.map(kind => {
      let combos = 1, hit = 1, hitMl = 1; const legs = [];
      s.races.forEach(n => {
        const live = byNum[n]; let pick, why;
        if (kind === 'main' && day === 'sat') ({ pick, why } = kbcLegSatMain(raceBy[n], live));
        else if (kind === 'tight') ({ pick, why } = kbcLegSatTight(live));
        else if (kind === 'main') ({ pick, why } = kbcLegMain(live));
        else if (kind === 'against') ({ pick, why } = kbcLegAgainst(live));
        else { pick = kbcLegWide(live, kbcLegMain(live).pick); why = 'saver'; }
        const c = pick.reduce((a, h) => a + h.p, 0), cm = pick.reduce((a, h) => a + h.p_ml, 0);
        combos *= pick.length; hit *= c; hitMl *= cm;
        legs.push({ race: n, pick, why, cov: c });
      });
      return { kind, legs, combos, hit, hitMl };
    });
    return { ...s, vars };
  });
}
function kbcOverlay(races) {
  if (!KBC.kee || races.some((n, i) => i && n !== races[i - 1] + 1)) return null;
  const bt = { 3: 'P3', 4: 'P4', 5: 'P5', 6: 'P6' }[races.length];
  const b = KBC.kee[bt]; if (!b || !b.by_position) return null;
  return b.by_position[races.join('-')] || null;
}

// ── Render ──
function kbcRender() {
  if (!KBC.data) return;
  const D = KBC.data;
  document.getElementById('kbc-day').innerHTML = [['fri', 'Friday'], ['sat', 'Saturday']].map(([k, l]) => `<button class="${KBC.day === k ? 'on' : ''}" onclick="KBC.day='${k}';KBC.race=null;kbcRender()">${l}</button>`).join('');
  document.getElementById('kbc-view').innerHTML = [['races', 'Races & plays'], ['tix', 'Tickets']].map(([k, l]) => `<button class="${KBC.view === k ? 'on' : ''}" onclick="KBC.view='${k}';kbcRender()">${l}</button>`).join('');
  // status line
  const w = KBC.watcher, date = D.meta.dates[KBC.day];
  let ws;
  if (w && w.track === 'KEE' && w.date === date) ws = `<span class="ok">Live scratches on</span> · watcher file ${kbcEsc(w.date)} updated ${kbcEsc(w.generated_at || '')} · ${(w.scratches || []).filter(s => /scratch/i.test(s.change_type || '')).length} scratches`;
  else if (KBC.live && !KBC.liveErr) ws = `<span class="ok">Scratches from the tote</span> (scratch watcher file not running for KEE; not needed while live odds are on)`;
  else ws = `<span class="warn">Watcher not running for KEE ${date}</span>${w ? ` (scratches.json is ${kbcEsc(w.track)} ${kbcEsc(w.date)})` : ''}. Tap “Scr” on a horse to scratch it by hand.`;
  const nman = Object.keys(KBC.manual).filter(k => KBC.manual[k] && k.startsWith(KBC.day + '|')).length;
  document.getElementById('kbc-status').innerHTML = `${ws}${nman ? ` · <b>${nman}</b> tapped in on this device <button class="kbc-x" onclick="kbcClearManual()">Clear</button>` : ''}<br>Model built ${kbcEsc(D.meta.generated_at)} · ${kbcEsc(D.meta.model)}. ${kbcLiveStatus()}`;
  const body = document.getElementById('kbc-body');
  body.innerHTML = KBC.view === 'races' ? kbcRacesHtml() : kbcTixHtml();
}
function kbcLiveStatus() {
  const L = KBC.live;
  if (KBC.liveErr) return `<br><span class="warn">Live odds unavailable (${kbcEsc(KBC.liveErr)})</span>. Odds shown are morning line.`;
  if (!L) return '<br>Live odds start on race day. Odds shown are morning line.';
  const t = new Date(L.fetched_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', second: '2-digit' });
  const nx = (L.races || []).filter(x => x.date === KBC.data.meta.dates[KBC.day] && x.mtp != null && !/official|closed|final/i.test(x.status || '')).sort((a, b) => a.num - b.num)[0];
  return `<br><span class="ok">Live odds on</span> (TwinSpires, updated ${t}, every 60 s)${nx ? ` · next: <b>R${nx.num}</b> ${nx.mtp <= 60 ? nx.mtp + ' MTP' : 'post ' + new Date(nx.post).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}` : ''}. Scratches from the tote are applied automatically.`;
}
function kbcClearManual() { Object.keys(KBC.manual).forEach(k => { if (k.startsWith(KBC.day + '|')) delete KBC.manual[k]; }); kbcSaveManual(); kbcRender(); }
function kbcToggle(day, num, pgm) { const k = `${day}|${num}|${pgm}`; KBC.manual[k] = !KBC.manual[k]; if (!KBC.manual[k]) delete KBC.manual[k]; kbcSaveManual(); kbcRender(); }

function kbcRacesHtml() {
  const rs = KBC.data.races.filter(r => r.day === KBC.day);
  if (KBC.race == null) KBC.race = rs.find(r => r.covered) ? rs.find(r => r.covered).num : rs[0].num;
  const chips = rs.map(r => { const { live } = kbcPrice(r); const t = live[0];
    const lrc = kbcLiveRace(r.day, r.num); const mtpTxt = lrc && lrc.mtp != null && lrc.mtp <= 30 && !/official|closed|final/i.test(lrc.status || '') ? ` <span class="kbc-mtp">${lrc.mtp} MTP</span>` : (lrc && /official|final/i.test(lrc.status || '') ? ' <span class="kbc-jt">done</span>' : '');
    return `<button class="${r.num === KBC.race ? 'on' : ''}" onclick="KBC.race=${r.num};kbcRender()">R${r.num} ${kbcEsc(r.short)}${mtpTxt}<small>${t ? kbcEsc(kbcName(t)) + ' ' + kbcPct(t.p) : ''}</small></button>`; }).join('');
  const r = rs.find(x => x.num === KBC.race);
  const { live, scr, lr } = kbcPrice(r);
  const P = kbcPlays(r, live);
  const mx = Math.max(...live.map(h => h.p), 0.01);
  let rows = '';
  live.forEach(h => {
    const figs = (h.figs || []).map(Math.round).join('·');
    const vel = h.opt_vel == null ? '—' : `<span class="${h.opt_vel >= 0.5 ? 'kbc-pos' : (h.opt_vel <= -0.5 ? 'kbc-neg' : '')}">${h.opt_vel > 0 ? '+' : ''}${h.opt_vel.toFixed(1)}</span>`;
    rows += `<tr><td>${kbcChip(h.pgm)}</td><td><div class="kbc-hn">${kbcEsc(h.name)}</div><div class="kbc-jt">${kbcEsc(h.jockey || '')} · ${kbcEsc(h.trainer || '')}</div></td>
      <td class="n">${kbcEsc(h.ml)}</td>
      <td class="n"><b class="${h.live_dec == null ? '' : (h.live_dec >= 1.33 * h.fair ? 'kbc-pos' : (h.live_dec < 0.75 * h.fair ? 'kbc-neg' : ''))}">${h.live ? kbcEsc(h.live) : '—'}</b>${h.live_fav ? '<span class="kbc-jt"> fav</span>' : ''}</td>
      <td><div class="kbc-bar2"><i><b style="width:${(h.p / mx * 100).toFixed(0)}%"></b></i>${kbcPct(h.p)}</div></td>
      <td class="n">${kbcOdds(h.fair)}</td>
      <td class="n ${h.edge >= 0 ? 'kbc-pos' : 'kbc-neg'}">${h.edge >= 0 ? '+' : ''}${Math.round(h.edge * 100)}%</td>
      <td class="n kbc-hide">${figs || '—'}</td><td class="n kbc-hide">${vel}</td>
      <td>${(h.tags || []).map(t => `<span class="kbc-tag ${t}">${t}</span>`).join('')}${(h.cons || []).map(c => `<span class="kbc-hc">${KBC_SRC[c[0]]}·${KBC_ROLE[c[1]]}</span>`).join('')}</td>
      <td><button class="kbc-x" onclick="kbcToggle('${r.day}',${r.num},'${h.pgm}')">Scr</button></td></tr>`;
  });
  r.horses.filter(h => h.status !== 'run' || scr.has(h.pgm)).forEach(h => {
    const manual = KBC.manual[`${r.day}|${r.num}|${h.pgm}`];
    rows += `<tr class="scr"><td>${kbcChip(h.pgm)}</td><td><div class="kbc-hn">${kbcEsc(h.name)}</div></td><td class="n">${kbcEsc(h.ml)}</td><td colspan="7">${h.status !== 'run' ? kbcEsc(h.status) : (manual ? 'Scratched (tapped)' : (lr && lr.by[h.pgm] && lr.by[h.pgm].scr ? 'Scratched (tote)' : 'Scratched (watcher)'))}</td>
      <td>${manual ? `<button class="kbc-x on" onclick="kbcToggle('${r.day}',${r.num},'${h.pgm}')">Undo</button>` : ''}</td></tr>`;
  });
  const sel = p => p.type.startsWith('Win') ? kbcChip(p.sel[0]) : (p.type === 'Exacta box' ? p.sel.map(kbcChip).join('') + ' <span class="kbc-jt">box</span>' : p.sel.map(l => l.map(kbcChip).join('')).join(' / '));
  const plays = P.plays.map(p => `<div class="kbc-play"><span class="t">${kbcEsc(p.type)}</span><span class="s">${sel(p)} <span class="kbc-jt">${p.units}u × ${p.combos}</span></span><span class="w">${kbcEsc(p.why)}</span></div>`).join('');
  return `<div class="kbc-chips">${chips}</div>
  <div class="kbc-card">
    <div class="kbc-rh"><h3>R${r.num} · ${kbcEsc(r.name)}</h3><div class="kbc-facts"><span>${kbcEsc(r.dist)} ${r.turf ? 'turf' : 'dirt'}</span><span>Post ${kbcEsc(r.post)} ET</span><span>Par ${r.par ?? '—'}</span><span>Pace: ${kbcEsc(r.pace)}</span><span>${live.length} running</span>${lr && lr.mtp != null && !/official|final/i.test(lr.status || '') ? `<span class="kbc-mtp">${lr.mtp} MTP</span>` : ''}</div></div>
    <div class="kbc-note">${kbcEsc(r.note)}</div>
    <div class="kbc-plays"><div class="kbc-h4">Plays · ${P.units} units</div>${plays}${P.notes.map(n => `<div class="kbc-pn">${kbcEsc(n)}</div>`).join('')}</div>
    <div class="kbc-scroll"><table class="kbc-t"><thead><tr><th>#</th><th>Horse</th><th class="n">ML</th><th class="n">Live</th><th>Win %</th><th class="n">Fair</th><th class="n">Edge</th><th class="n kbc-hide">Last 3 figs</th><th class="n kbc-hide">Optix</th><th>Tags</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>
  </div>`;
}

function kbcTixHtml() {
  const T = kbcTickets(KBC.day).filter(s => KBC.tf === 'all' || (KBC.tf === 'p3' ? s.races.length === 3 : s.races.length >= 4));
  const seg = (arr, cur, fn) => `<div class="kbc-seg">${arr.map(([k, l]) => `<button class="${cur === k ? 'on' : ''}" onclick="${fn}('${k}')">${l}</button>`).join('')}</div>`;
  const names = {}; KBC.data.races.filter(r => r.day === KBC.day).forEach(r => { names[r.num] = r.short; });
  let html = `<div class="kbc-bar">${seg([['big', 'Pick 4–6'], ['p3', 'Pick 3s'], ['all', 'All']], KBC.tf, 'kbcSetTf')}${seg([['0.2', '$0.20'], ['0.5', '$0.50'], ['1', '$1'], ['2', '$2']], String(KBC.base), 'kbcSetBase')}</div>
    <div class="kbc-jt">Hit % = model chance the ticket wins. "If ML right" = same ticket priced by the morning line. KEE history = this sequence's past payout vs. parlay at the regular meet (BC pools are bigger, so treat it as directional).</div>`;
  const KN = { main: KBC.day === 'sat' ? 'Main (saver rules)' : 'Main', wide: 'Saver', tight: 'Tight backup', against: 'Against the chalk' };
  T.forEach(s => {
    const ov = kbcOverlay(s.races);
    html += `<div class="kbc-slip"><div class="kbc-rh"><h3>${kbcEsc(s.bet)} · R${s.races.join(', R')}</h3>${ov ? `<span class="kbc-ovl ${ov.overlay_ratio >= 1.2 ? 'hot' : ''}">KEE history ${ov.overlay_ratio}× · ${ov.times_hit} hits${ov.thin_sample ? ' (thin)' : ''}</span>` : ''}</div>
      <div class="kbc-jt">${s.races.map(n => kbcEsc(names[n])).join(' → ')}</div><div class="kbc-vars">`;
    s.vars.forEach(v => {
      const txt = `KEE ${KBC.day === 'fri' ? 'Fri' : 'Sat'} R${s.races[0]} ${s.bet}: ` + v.legs.map(l => l.pick.map(h => h.pgm).join(',')).join(' / ');
      html += `<div class="kbc-var ${v.kind === 'main' ? 'main' : ''}"><div class="k">${KN[v.kind]}<button class="kbc-copy" data-t="${kbcEsc(txt)}" onclick="kbcCopy(this)">Copy</button></div>
        ${v.legs.map(l => `<div class="kbc-leg"><span class="r">R${l.race}</span><span class="c">${l.pick.map(h => kbcChip(h.pgm)).join('')} <span class="kbc-jt">${kbcPct(l.cov)} · ${kbcEsc(l.why)}</span></span></div>`).join('')}
        <div class="kbc-stats"><span>Combos <b>${v.combos}</b></span><span>Cost <b>$${(v.combos * KBC.base).toFixed(2)}</b></span><span>Hit <b>${kbcPct(v.hit, 1)}</b></span><span>If ML right <b>${kbcPct(v.hitMl, 1)}</b></span></div>
        <div class="kbc-txt">${kbcEsc(txt)}</div></div>`;
    });
    html += `</div></div>`;
  });
  return html;
}
function kbcSetTf(k) { KBC.tf = k; kbcRender(); }
function kbcSetBase(k) { KBC.base = parseFloat(k); kbcRender(); }
function kbcCopy(b) {
  const t = b.dataset.t;
  const done = () => { b.textContent = 'Copied'; setTimeout(() => { b.textContent = 'Copy'; }, 1200); };
  try { navigator.clipboard.writeText(t).then(done).catch(() => {}); } catch (e) {}
}
