"""One-off: what ESPN's public odds look like right now, and whether a browser may call it (printed as workflow notices)."""
import json
import re
import requests

H = {"User-Agent": "Mozilla/5.0", "Origin": "https://mbennett00.github.io"}
LG = {"nhl": "hockey/nhl", "nfl": "football/nfl", "nba": "basketball/nba"}


def note(t, s):
    print(f"::notice title={t}::{s[:3800]}")


for k, path in LG.items():
    r = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard", headers=H, timeout=30)
    note(f"{k} site headers", f"{r.status_code} ACAO={r.headers.get('access-control-allow-origin')} cache={r.headers.get('cache-control')}")
    evs = r.json().get("events", [])
    shown = 0
    for ev in evs:
        c = ev["competitions"][0]
        st = ev["status"]["type"]["state"]
        odds = c.get("odds") or []
        note(f"{k} ev {ev['id']} {st}", f"{ev.get('shortName')} odds_n={len(odds)} " + json.dumps(odds[0] if odds else None)[:3000])
        shown += 1
        if st == "in" or shown >= 2:
            break
    live = [e for e in evs if e["status"]["type"]["state"] == "in"]
    for ev in (live or evs)[:1]:
        lg = path.split("/")
        u = f"https://sports.core.api.espn.com/v2/sports/{lg[0]}/leagues/{lg[1]}/events/{ev['id']}/competitions/{ev['id']}/odds"
        r2 = requests.get(u, headers=H, timeout=30)
        note(f"{k} core odds headers", f"{r2.status_code} ACAO={r2.headers.get('access-control-allow-origin')}")
        try:
            items = r2.json().get("items", [])
            note(f"{k} core providers", json.dumps([(i.get("provider", {}).get("id"), i.get("provider", {}).get("name")) for i in items]))
            dk = next((i for i in items if str(i.get("provider", {}).get("id")) == "100"), items[0] if items else None)
            if dk:
                slim = {x: dk.get(x) for x in ("details", "overUnder", "spread", "moneyline", "awayTeamOdds", "homeTeamOdds", "current", "open", "close", "live")}
                note(f"{k} core DK {ev['status']['type']['state']}", json.dumps(slim)[:3500])
        except Exception as e:
            note(f"{k} core err", str(e))


# props: the raw DraftKings prop items for one star per league, to check how lines and prices are laid out
STARS = {"nhl": ("Nathan MacKinnon", ("Points Milestones", "Assists Milestones", "Total Points")), "nba": ("", ("Points Milestones", "Total Points")),
         "nfl": ("", ("Receiving Yards Milestones", "Rushing Yards Milestones"))}
for k, path in LG.items():
    sport, lg = path.split("/")
    evs = [e for e in requests.get(f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard", headers=H, timeout=30).json().get("events", []) if e["status"]["type"]["state"] == "pre"]
    star, kinds = STARS[k]
    for ev in evs[:6]:
        names = {}
        for c in ev["competitions"][0]["competitors"]:
            r = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/{path}/teams/{c['team']['id']}/roster", headers=H, timeout=30).json()
            for grp in r.get("athletes", []):
                for a in grp.get("items", [grp]) if isinstance(grp, dict) else []:
                    if a.get("id"): names[str(a["id"])] = a.get("fullName") or a.get("displayName")
        pb = requests.get(f"https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{lg}/events/{ev['id']}/competitions/{ev['id']}/odds/100/propBets", params={"limit": 1000}, headers=H, timeout=40).json()
        items = pb.get("items", [])
        want = None
        if star:
            sid = next((i for i, n in names.items() if n == star), None)
            if not sid: continue
            want = sid
        else:
            import collections
            cnt = collections.Counter(re.search(r"/athletes/(\d+)", (it.get("athlete") or {}).get("$ref", "") or "x").group(1) if re.search(r"/athletes/(\d+)", (it.get("athlete") or {}).get("$ref", "") or "") else None for it in items if (it.get("type") or {}).get("name") in kinds)
            want = next((a for a, _ in cnt.most_common() if a), None)
        mine = [it for it in items if want and f"/athletes/{want}" in (it.get("athlete") or {}).get("$ref", "") and (it.get("type") or {}).get("name") in kinds]
        note(f"{k} props {names.get(want, want)}", f"{len(mine)} items of {len(items)} (pages {pb.get('pageCount')})")
        for it in mine[:9]:
            slim = {x: v for x, v in it.items() if x not in ("athlete", "links", "$ref", "propBets")}
            note(f"{k} prop {(it.get('type') or {}).get('name')}", json.dumps(slim)[:1500])
        break
