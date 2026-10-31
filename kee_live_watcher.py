"""
kee_live_watcher.py — live tote odds, MTP and scratches for Keeneland, pushed to Firebase
for the KEE BC tab (horse-racing-derby.netlify.app).

TwinSpires' public program API answers home connections but not cloud servers, so this runs
on your PC during the card (double-click run_kee_live.bat). Every 60 s it reads the race list
(post times, MTP, status) and the entries (live odds, scratches) for every race within 20 MTP;
every 5th cycle it reads the whole card so scratches in later races show up too. Each cycle is
written to Firebase at archive/kee-live, which the app polls once a minute.

Usage:
    python kee_live_watcher.py           # run until the last race is official
    python kee_live_watcher.py --once    # one full fetch, print a summary, push
    python kee_live_watcher.py --print   # run, print, don't push

Requires: pip install requests curl_cffi
"""
import sys, time, json
from datetime import datetime, timezone
import requests

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = "https://www.twinspires.com/adw/todays-tracks/KEE/Thoroughbred"
FIREBASE = "https://caw-live-default-rtdb.firebaseio.com/archive/kee-live.json"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Referer": "https://www.twinspires.com/bet/program/classic/keeneland/kee/Thoroughbred/1/basic",
}
POLL_SECONDS = 60
HOT_MTP = 20
FULL_EVERY = 5
DONE = ("official", "closed", "final", "resulted")

# TwinSpires' bot shield stalls plain Python requests (read timeouts) because their TLS handshake
# doesn't look like a browser's. curl_cffi makes the same request with Chrome's handshake.
PROGRAM_PAGE = "https://www.twinspires.com/bet/program/classic/breeders-cup-at-keeneland/kee/Thoroughbred/1/basic"
try:
    from curl_cffi import requests as browser_requests
    S = browser_requests.Session(impersonate="chrome")
    S.headers.update({"Accept": "application/json, text/plain, */*", "Referer": HEADERS["Referer"]})
    ENGINE = "curl_cffi (Chrome handshake)"
except ImportError:
    S = requests.Session()
    S.headers.update(HEADERS)
    ENGINE = "requests (may be blocked; pip install curl_cffi)"
_warm = {"done": False}


def warm_up():
    """Load the program page once, like a browser would, to pick up the site's cookies."""
    try:
        S.get(PROGRAM_PAGE, timeout=20, headers={"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"})
    except Exception as ex:
        print(f"warm-up: {ex}", flush=True)
    _warm["done"] = True


def get(path):
    if not _warm["done"]:
        warm_up()
    try:
        r = S.get(f"{BASE}{path}", params={"affid": "2800"}, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception:
        _warm["done"] = False   # re-warm on the next call
        raise


def entries(n):
    try:
        return [{"pgm": str(e.get("programNumber")), "name": e.get("name"), "live": e.get("liveOdds"),
                 "ml": e.get("morningLineOdds"), "scr": bool(e.get("scratched")),
                 "fav": bool(e.get("liveOddsFavorite")), "ae": bool(e.get("alsoEligible"))}
                for e in get(f"/races/{n}/entries")]
    except Exception as ex:
        return {"error": str(ex)}


def cycle(full, prev):
    races = get("/races")
    lst = [{"num": r["raceNumber"], "date": r.get("raceDate"), "post": r.get("postTime"),
            "postTs": r.get("postTimeStamp"), "mtp": r.get("mtp"), "status": r.get("status")} for r in races]
    want = [r["num"] for r in lst] if full else [
        r["num"] for r in lst if r["mtp"] is not None and r["mtp"] <= HOT_MTP
        and not any(d in (r["status"] or "").lower() for d in DONE)]
    ent = {} if full else dict(prev.get("entries", {}))
    for n in want:
        ent[str(n)] = entries(n)
    return {"track": "KEE", "source": "TwinSpires program API via kee_live_watcher.py",
            "fetched_at": datetime.now(timezone.utc).isoformat(), "races": lst, "entries": ent}, lst


def summary(d):
    nxt = [r for r in d["races"] if not any(x in (r["status"] or "").lower() for x in DONE)]
    head = f"R{nxt[0]['num']} {nxt[0]['mtp']} MTP" if nxt else "card done"
    scr = sum(1 for es in d["entries"].values() if isinstance(es, list) for e in es if e["scr"])
    parts = []
    if nxt and str(nxt[0]["num"]) in d["entries"] and isinstance(d["entries"][str(nxt[0]["num"])], list):
        es = [e for e in d["entries"][str(nxt[0]["num"])] if not e["scr"]]
        parts = [f"{e['pgm']}:{e['live'] or '-'}" for e in es]
    return f"{datetime.now().strftime('%H:%M:%S')}  {head}  scratches seen {scr}  {' '.join(parts)}"


def push(d):
    r = requests.put(FIREBASE, data=json.dumps(d), timeout=15)
    r.raise_for_status()


def main():
    once, dry = "--once" in sys.argv, "--print" in sys.argv
    prev, i = {}, 0
    print(f"KEE live watcher: {ENGINE}. Writing to Firebase every {POLL_SECONDS} s. Leave this window open.", flush=True)
    while True:
        try:
            d, lst = cycle(once or i % FULL_EVERY == 0, prev)
            prev = d
            print(summary(d), flush=True)
            if not dry:
                push(d)
            if once:
                return
            if lst and all(any(x in (r["status"] or "").lower() for x in DONE) for r in lst):
                print("All races official. Done.")
                sys.exit(3)
        except Exception as ex:
            print(f"{datetime.now().strftime('%H:%M:%S')}  error: {ex}", flush=True)
        i += 1
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
