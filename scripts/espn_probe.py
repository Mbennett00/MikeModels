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
    want = ("Anytime", "Milestones", "Goal Scorer", "Shots", "Points", "Assists")
    seen = collections.Counter()
    for it in items:
        nm = it["type"]["name"]
        if any(w in nm for w in want) and seen[nm] < 3 and "athlete" in it:
            seen[nm] += 1
            print(nm, "|", it["athlete"]["$ref"].split("/athletes/")[1].split("?")[0], "| odds", json.dumps(it.get("odds", {}).get("american")), "| total", json.dumps(it.get("odds", {}).get("total")), "| target", json.dumps((it.get("current") or {}).get("target")))
