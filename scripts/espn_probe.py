"""One-off: what odds does ESPN's free API return? Prints trimmed samples (scoreboard odds, core odds, prop bets)."""
import json
import requests

H = {"User-Agent": "Mozilla/5.0"}
SB = {"nfl": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
      "nhl": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard"}
CORE = {"nfl": "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl", "nhl": "https://sports.core.api.espn.com/v2/sports/hockey/leagues/nhl"}


def get(u):
    r = requests.get(u, headers=H, timeout=30)
    return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:300]), dict(r.headers)


for sp in ("nfl", "nhl"):
    code, sb, hd = get(SB[sp])
    print(f"\n===== {sp} scoreboard {code} CORS={hd.get('Access-Control-Allow-Origin')}")
    evs = sb.get("events", []) if isinstance(sb, dict) else []
    for ev in evs[:2]:
        c = ev["competitions"][0]
        print(ev["name"], ev["status"]["type"]["state"])
        print(json.dumps(c.get("odds"), indent=1)[:2500])
    pre = [e for e in evs if e["status"]["type"]["state"] == "pre"] or evs
    if not pre:
        continue
    ev = pre[0]; eid = ev["id"]
    code, od, hd = get(f"{CORE[sp]}/events/{eid}/competitions/{eid}/odds")
    print(f"\n----- {sp} core odds {code} CORS={hd.get('Access-Control-Allow-Origin')} items={len(od.get('items', [])) if isinstance(od, dict) else '?'}")
    for it in (od.get("items", []) if isinstance(od, dict) else [])[:3]:
        print(json.dumps({k: it.get(k) for k in ("provider", "details", "spread", "overUnder", "awayTeamOdds", "homeTeamOdds", "moneyline", "propBets")}, indent=1)[:2000])
    items = od.get("items", []) if isinstance(od, dict) else []
    if items:
        pid = (items[0].get("provider") or {}).get("id")
        code, pb, hd = get(f"{CORE[sp]}/events/{eid}/competitions/{eid}/odds/{pid}/propBets?limit=40")
        print(f"\n----- {sp} propBets provider {pid}: {code} count={pb.get('count') if isinstance(pb, dict) else '?'}")
        for it in (pb.get("items", []) if isinstance(pb, dict) else [])[:6]:
            print(json.dumps(it, indent=1)[:900])
