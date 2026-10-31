// Live tote odds, scratches and minutes-to-post for today's Keeneland card.
// Proxies TwinSpires' public program API (no login) so the KEE BC tab can poll it.
//   GET /.netlify/functions/kee-live            -> race list + entries for races within 20 MTP
//   GET /.netlify/functions/kee-live?full=1     -> race list + entries for every race (scratches)
//   GET /.netlify/functions/kee-live?race=7     -> race list + entries for race 7
const BASE = 'https://www.twinspires.com/adw/todays-tracks/KEE/Thoroughbred';
const HDRS = {
  'Accept': 'application/json',
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
  'Referer': 'https://www.twinspires.com/bet/program/classic/keeneland/kee/Thoroughbred/1/basic',
};

async function getJson(path) {
  const r = await fetch(`${BASE}${path}${path.includes('?') ? '&' : '?'}affid=2800`, { headers: HDRS });
  if (!r.ok) throw new Error(`${path} -> HTTP ${r.status}`);
  return r.json();
}

exports.handler = async (event) => {
  const q = event.queryStringParameters || {};
  try {
    const races = await getJson('/races');
    const list = races.map(r => ({
      num: r.raceNumber, date: r.raceDate, post: r.postTime, postTs: r.postTimeStamp,
      mtp: r.mtp, status: r.status, current: !!r.currentRace,
    }));
    let want;
    if (q.full) want = list.map(r => r.num);
    else if (q.race) want = [parseInt(q.race, 10)];
    else want = list.filter(r => r.mtp != null && r.mtp <= 20 && !/official|closed|final/i.test(r.status || '')).map(r => r.num);
    const entries = {};
    await Promise.all(want.map(async n => {
      try {
        const es = await getJson(`/races/${n}/entries`);
        entries[n] = es.map(e => ({
          pgm: String(e.programNumber), name: e.name, live: e.liveOdds, ml: e.morningLineOdds,
          scr: !!e.scratched, fav: !!e.liveOddsFavorite, ae: !!e.alsoEligible,
        }));
      } catch (err) { entries[n] = { error: err.message }; }
    }));
    return {
      statusCode: 200,
      headers: { 'Content-Type': 'application/json', 'Cache-Control': 'public, max-age=20', 'Access-Control-Allow-Origin': '*' },
      body: JSON.stringify({ track: 'KEE', source: 'TwinSpires program API', fetched_at: new Date().toISOString(), races: list, entries }),
    };
  } catch (err) {
    return { statusCode: 502, headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }, body: JSON.stringify({ error: err.message }) };
  }
};
