"""One-off: the raw DraftKings prop items ESPN serves for one NHL star, packed into a few workflow notices."""
import json
import requests

H = {"User-Agent": "Mozilla/5.0", "Origin": "https://mbennett00.github.io"}
STAR, KINDS = "Nathan MacKinnon", ("Points Milestones", "Total Points", "Assists Milestones", "Total Assists")


def note(t, s):
    print(f"::notice title={t}::{s[:3800]}")


evs = [e for e in requests.get("https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard", headers=H, timeout=30).json().get("events", [])]
for ev in evs:
    sid = None
    for c in ev["competitions"][0]["competitors"]:
        r = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/teams/{c['team']['id']}/roster", headers=H, timeout=30).json()
        for grp in r.get("athletes", []):
            for a in grp.get("items", [grp]):
                if (a.get("fullName") or a.get("displayName")) == STAR: sid = str(a["id"])
    if not sid: continue
    pb = requests.get(f"https://sports.core.api.espn.com/v2/sports/hockey/leagues/nhl/events/{ev['id']}/competitions/{ev['id']}/odds/100/propBets", params={"limit": 1000}, headers=H, timeout=40).json()
    mine = [it for it in pb.get("items", []) if f"/athletes/{sid}" in (it.get("athlete") or {}).get("$ref", "") and (it.get("type") or {}).get("name") in KINDS]
    rows = [json.dumps({"t": it["type"]["name"], **{x: v for x, v in it.items() if x not in ("athlete", "links", "$ref", "propBets", "type", "competition", "provider", "lastUpdated")}}, separators=(",", ":")) for it in mine]
    note("prop count", f"{ev['shortName']} {ev['status']['type']['state']} {len(mine)} items of {len(pb.get('items', []))} pages {pb.get('pageCount')}")
    buf, n = "", 0
    for r in rows:
        if len(buf) + len(r) > 3700 and n < 8: note(f"prop rows {n}", buf); buf, n = "", n + 1
        buf += r + " || "
    if buf and n < 9: note(f"prop rows {n}", buf)
    break
else:
    note("prop count", f"{STAR} not on today's slate ({len(evs)} games)")
