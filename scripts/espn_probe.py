"""One-off: how complete are free DraftKings prop prices (ESPN core + DK's public feed)?"""
import collections
import json
import requests

H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"}
SB = {"nfl": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
      "nhl": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard"}
CORE = {"nfl": "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl", "nhl": "https://sports.core.api.espn.com/v2/sports/hockey/leagues/nhl"}


def get(u):
    r = requests.get(u, headers=H, timeout=30)
    return r.json()


for sp in ("nhl", "nfl"):
    try:
        evs = get(SB[sp]).get("events", [])
    except Exception as e:
        print(sp, "scoreboard fail", e); continue
    pre = [e for e in evs if e["status"]["type"]["state"] == "pre"]
    print(f"\n===== {sp}: {len(evs)} events, {len(pre)} pre")
    for ev in pre[:3]:
        eid = ev["id"]
        print("--", ev.get("shortName"))
        try:
            od = get(f"{CORE[sp]}/events/{eid}/competitions/{eid}/odds?limit=50")
            provs = [(it.get("provider", {}).get("id"), it.get("provider", {}).get("name")) for it in od.get("items", [])]
            print("providers:", provs)
        except Exception as e:
            print("odds list fail", e); provs = [("100", "DK")]
        for pid, pname in provs or [("100", "DK")]:
            try:
                pb = get(f"{CORE[sp]}/events/{eid}/competitions/{eid}/odds/{pid}/propBets?limit=1000")
            except Exception as e:
                print(" ", pid, "propBets fail", e); continue
            items = pb.get("items", [])
            ty = collections.Counter(); ty_o = collections.Counter(); ath = collections.defaultdict(set); lines = collections.defaultdict(collections.Counter)
            for it in items:
                nm = (it.get("type") or {}).get("name", "?"); ty[nm] += 1
                am = ((it.get("odds") or {}).get("american") or {}).get("value")
                if am is not None:
                    ty_o[nm] += 1
                    if "athlete" in it:
                        ath[nm].add(it["athlete"]["$ref"].split("/athletes/")[1].split("?")[0])
                    tg = ((it.get("current") or {}).get("target") or {}).get("value")
                    lines[nm][tg] += 1
            print(f"  prov {pid} {pname}: {len(items)} items")
            for nm, n in ty.most_common(40):
                print(f"    {nm}: {n} items, {ty_o[nm]} priced, {len(ath[nm])} athletes, targets {dict(lines[nm].most_common(8))}")
            # a sample of a two-sided item (over/under) if any
            for it in items:
                o = it.get("odds") or {}
                if o.get("over") or o.get("under") or o.get("total"):
                    print("    sample 2-sided:", it["type"]["name"], json.dumps(o)[:300]); break
        if sp == "nhl":
            break

# DraftKings' own public feed (used by their website)
for sp, lg in (("nhl", 42133), ("nfl", 88808)):
    for host in ("sportsbook-nash.draftkings.com/api/sportscontent/dkusnj/v1", "sportsbook-nash.draftkings.com/api/sportscontent/dkusoh/v1"):
        u = f"https://{host}/leagues/{lg}"
        try:
            r = requests.get(u, headers=H, timeout=30)
            print("\nDK", sp, u, r.status_code, len(r.content))
            j = r.json()
            print(" keys", list(j)[:10])
            cats = j.get("categories") or []
            print(" categories", [(c.get("id"), c.get("name")) for c in cats][:30])
            print(" markets", len(j.get("markets", [])), "selections", len(j.get("selections", [])), "events", len(j.get("events", [])))
        except Exception as e:
            print("DK fail", u, e)
    # subcategory listing for player props
    try:
        u = f"https://sportsbook-nash.draftkings.com/api/sportscontent/dkusnj/v1/leagues/{lg}/categories/1342" if sp == "nhl" else f"https://sportsbook-nash.draftkings.com/api/sportscontent/dkusnj/v1/leagues/{lg}/categories/1000"
        r = requests.get(u, headers=H, timeout=30); j = r.json()
        print(" cat", u, r.status_code, "subcats", [(s.get("id"), s.get("name")) for s in j.get("subcategories", [])][:30])
        print(" markets", len(j.get("markets", [])), "selections", len(j.get("selections", [])))
        for s in j.get("selections", [])[:3]:
            print("  sel", json.dumps(s)[:300])
    except Exception as e:
        print("DK cat fail", e)
