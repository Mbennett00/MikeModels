"""One-off: what odds does ESPN's free API return? Compact answers to specific questions."""
import collections
import json
import requests

H = {"User-Agent": "Mozilla/5.0"}
SB = {"nfl": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
      "nhl": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard"}
CORE = {"nfl": "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl", "nhl": "https://sports.core.api.espn.com/v2/sports/hockey/leagues/nhl"}
get = lambda u: requests.get(u, headers=H, timeout=30).json()

for sp in ("nfl", "nhl"):
    sb = get(SB[sp]); evs = sb.get("events", [])
    pre = [e for e in evs if e["status"]["type"]["state"] == "pre"]
    print(f"\n===== {sp}: {len(evs)} events, {len(pre)} pre")
    pick = (pre or evs)
    if not pick:
        continue
    print("states:", collections.Counter(e["status"]["type"]["state"] for e in evs), "| odds present:", sum(bool(e["competitions"][0].get("odds")) for e in evs))
    o = pick[0]["competitions"][0].get("odds")
    print("SCOREBOARD odds keys:", [list(x.keys()) for x in o] if o else o)
    if o:
        x = o[0]; print("provider", x.get("provider", {}).get("name"), "details", x.get("details"), "OU", x.get("overUnder"), "spread", x.get("spread"))
        print("home", json.dumps(x.get("homeTeamOdds"))[:400]); print("ml", json.dumps(x.get("moneyline"))[:400]); print("ps", json.dumps(x.get("pointSpread"))[:400]); print("tot", json.dumps(x.get("total"))[:400])
    eid = pick[0]["id"]
    pb = get(f"{CORE[sp]}/events/{eid}/competitions/{eid}/odds/100/propBets?limit=1000")
    items = pb.get("items", [])
    print("propBets", pb.get("count"), "fields:", sorted({k for it in items for k in it}))
    print("types:", collections.Counter(it["type"]["name"] for it in items).most_common(25))
    ath = items[0]["athlete"]["$ref"] if items else None
    same = [it for it in items if it["athlete"]["$ref"] == ath]
    for it in same[:8]:
        it = {k: v for k, v in it.items() if k not in ("competition", "athlete", "provider")}
        print(json.dumps(it))
    if ath:
        a = get(ath.replace("http://", "https://")); print("athlete:", a.get("id"), a.get("displayName"), a.get("position", {}).get("abbreviation"))
