"""Market odds for the Pikt pages: DraftKings + FanDuel game lines and player props, all free.

python -m calib.odds [--state state]

Game lines: calib.sharp pulls DraftKings and FanDuel from SharpAPI's free tier (SHARP_API_KEY); each game's line is the
one both books hang, priced at their median. Between pulls the last good lines stay, minus games that have started.
Props: ESPN's core odds feed carries DraftKings' prop prices for free (milestones and anytime scorers, all three
leagues). SharpAPI adds both books: FanDuel fills rungs DraftKings doesn't hang, each rung gets a no-vig fair chance
from the two books, and NFL props (unpriced on ESPN) come priced. The page itself refreshes DraftKings from ESPN every
30 seconds (lines) and 5 minutes (props).
Writes state/site/odds.json (kept with the state) and state/site/web/odds.json. Never raises: a failed pull keeps
the last good prices, and the pages fall back to their own when a game has none.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import unicodedata

import requests
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

PAGE = {"NHL": "data.json", "NBA": "nba.json", "NFL": "nfl.json"}
UA = {"User-Agent": "Mozilla/5.0 (Pikt odds)"}


def nm(s: str) -> str:
    """Same key the pages use (book.js bkNm): accents off, suffixes off, letters only."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s)
    return re.sub(r"[^a-z]", "", s)


def upcoming(web: str, league: str) -> int:
    """Games on the league's page that haven't started."""
    try:
        d = json.load(open(os.path.join(web, PAGE[league])))
    except (OSError, ValueError):
        return 0
    now = dt.datetime.now(dt.timezone.utc)
    n = 0
    for g in d.get("games") or []:
        t = g.get("start_utc")
        if t and dt.datetime.fromisoformat(str(t).replace("Z", "+00:00")) > now and g.get("state") not in ("post", "in"):
            n += 1
    return n


# ---------- props: DraftKings via ESPN (free) ----------
# ESPN's core odds feed (provider 100 = DraftKings) lists each player's prop bets. Only one-sided markets are used,
# so a price always belongs to "this player gets N or more": milestones ("20+ points": target 20 -> over 19.5) and
# anytime scorers (over 0.5). Two-way over/unders are skipped. Keys match the pages: "stat|line".
ESPN = {"NHL": ("hockey", "nhl"), "NBA": ("basketball", "nba"), "NFL": ("football", "nfl")}
SITE = "https://site.api.espn.com/apis/site/v2/sports/{}/{}"
CORE = "https://sports.core.api.espn.com/v2/sports/{}/leagues/{}"
RULES = {   # keyword in the market name -> the page's stat (first match wins, so combos come first)
    "NBA": [("points + rebounds + assists", "pra"), ("pts + reb + ast", "pra"), ("points, rebounds", "pra"), ("rebounds + assists", None),
            ("+", None), ("three", "fg3"), ("3-point", "fg3"), ("3pt", "fg3"), ("rebound", "reb"), ("assist", "ast"), ("point", "pts")],
    "NFL": [("+", None), ("passing yards", "pass_yds"), ("rushing yards", "rush_yds"), ("receiving yards", "rec_yds"), ("reception", "rec")],
    "NHL": [("+", None), ("shots", "sog"), ("assist", "assists"), ("point", "points"), ("goal", "goals")],
}


OTHER_MARKETS = ("power play", "powerplay", "short", "blocked", "save", "team", "hit", "faceoff", "penalt", "takeaway", "giveaway", "longest", "interception", "attempt", "completion")


def prop_kind(league: str, name: str):
    n = (name or "").lower()
    if any(w in n for w in ("1st", "2nd", "3rd", "half", "quarter", "period", "first ", "last ")):
        return None                                   # partial-game and first/last scorer markets aren't on the page
    if any(w in n for w in OTHER_MARKETS):
        return None                                   # power-play points, blocked shots, team totals... share a keyword with ours
    if league == "NFL" and "2 or more touchdowns" in n:
        return "td", 1.5
    if league == "NHL" and "score 2+ goals" in n:
        return "goals", 1.5
    if "anytime" in n:
        if league == "NFL" and ("touchdown" in n or " td" in n):
            return "td", True
        if league == "NHL" and "goal" in n:
            return "goals", True
        return None
    if "milestone" not in n:
        return None
    for kw, stat in RULES[league]:
        if kw in n:
            return (stat, False) if stat else None
    return None


def _am(v):
    t = str(v or "").strip().upper()
    if t in ("EVEN", "EV"):
        return 100
    try:
        x = int(float(t.replace("+", "")))
    except ValueError:
        return None
    return x if abs(x) >= 100 else None


def _price(it: dict):
    """The item's American price wherever ESPN put it: an "american" value (dict or string) or a "decimal" one,
    searched through odds / current / the item itself."""
    def amer(v):
        if isinstance(v, dict):
            for k in ("value", "alternateDisplayValue", "displayValue"):
                a = _am(v.get(k))
                if a is not None:
                    return a
            return None
        return _am(v)
    def dec(v):
        try:
            d = float(v.get("value") if isinstance(v, dict) else v)
        except (TypeError, ValueError):
            return None
        return None if d <= 1 else (round((d - 1) * 100) if d >= 2 else round(-100 / (d - 1)))
    stack = [it.get("odds"), it.get("current"), {k: v for k, v in it.items() if k not in ("athlete", "type", "links", "odds", "current")}]
    while stack:
        x = stack.pop(0)
        if isinstance(x, list):
            stack += x
        elif isinstance(x, dict):
            if "american" in x and amer(x["american"]) is not None:
                return amer(x["american"])
            if "decimal" in x and dec(x["decimal"]) is not None:
                return dec(x["decimal"])
            stack += [v for k, v in x.items() if isinstance(v, (dict, list))]
    return None


def _get(url, **kw):
    return requests.get(url, headers=UA, timeout=25, **kw).json()


def espn_props(league: str, log=print) -> dict:
    """{player key: {"stat|line": american}} for the league's upcoming games; {} when ESPN is unavailable."""
    sport, lg = ESPN[league]
    try:
        evs = [e for e in _get(SITE.format(sport, lg) + "/scoreboard").get("events", []) if ((e.get("status") or {}).get("type") or {}).get("state") == "pre"]
    except Exception as e:
        log(f"odds: {league} props scoreboard failed ({e})"); return {}
    names, teams, out, seen = {}, set(), {}, {}
    for ev in evs:
        for c in ((ev.get("competitions") or [{}])[0]).get("competitors", []):
            tid = (c.get("team") or {}).get("id")
            if not tid or tid in teams:
                continue
            teams.add(tid)
            try:
                for grp in _get(SITE.format(sport, lg) + f"/teams/{tid}/roster").get("athletes", []):
                    for a in (grp.get("items", []) if isinstance(grp, dict) and "items" in grp else [grp]):
                        if a.get("id") and (a.get("fullName") or a.get("displayName")):
                            names[str(a["id"])] = nm(a.get("fullName") or a.get("displayName"))
            except Exception:
                continue
    items = []
    for ev in evs:
        eid, page = ev.get("id"), 1
        while page:
            try:
                pb = _get(CORE.format(sport, lg) + f"/events/{eid}/competitions/{eid}/odds/100/propBets", params={"limit": 1000, "page": page})
            except Exception as e:
                log(f"odds: {league} props event {eid} failed ({e})"); break
            items += pb.get("items", [])
            page = page + 1 if page < int(pb.get("pageCount") or 1) else 0
    refs = {}
    for it in items:
        ref = (it.get("athlete") or {}).get("$ref", ""); m = re.search(r"/athletes/(\d+)", ref)
        if m and m.group(1) not in names and prop_kind(league, ((it.get("type") or {}).get("name") or "")):
            refs[m.group(1)] = ref
    if refs:
        from concurrent.futures import ThreadPoolExecutor
        def one(kv):
            try:
                a = _get(kv[1].replace("http://", "https://"))
                return kv[0], a.get("fullName") or a.get("displayName")
            except Exception:
                return kv[0], None
        with ThreadPoolExecutor(12) as ex:
            for aid, full in ex.map(one, list(refs.items())[:900]):
                if full:
                    names[aid] = nm(full)
    miss = {"name": 0, "price": 0}
    for it in items:
        tn = ((it.get("type") or {}).get("name") or "").strip()
        seen[tn] = seen.get(tn, 0) + 1
        k = prop_kind(league, tn)
        m = re.search(r"/athletes/(\d+)", (it.get("athlete") or {}).get("$ref", ""))
        if not k or not m:
            continue
        price = _price(it)
        if price is None and not miss.get("sample"):
            miss["sample"] = json.dumps({k: v for k, v in it.items() if k not in ("athlete", "links", "$ref")})[:600]
        if m.group(1) not in names or price is None:
            miss["name" if m.group(1) not in names else "price"] += 1
            continue
        stat, how = k
        if isinstance(how, float):
            line = how                                  # "2 or more touchdowns" = over 1.5
        elif how:
            line = 0.5                                  # anytime scorer
        else:
            tgt = ((it.get("current") or {}).get("target") or {}).get("value")
            if tgt is None:
                continue
            line = float(tgt) - 0.5                     # milestone "N+" = over N - 0.5
        out.setdefault(names[m.group(1)], {})[f"{stat}|{line:g}"] = price
    top = ", ".join(f"{k} ({v})" for k, v in sorted(seen.items(), key=lambda kv: -kv[1])[:14])
    log(f"odds: {league} DraftKings props for {len(out)} players ({len(names)} names, {len(refs)} looked up, dropped {miss['name']} unnamed / {miss['price']} unpriced) from {len(evs)} games · markets seen: {top or 'none'}")
    if miss.get("sample") and not out:
        log(f"odds: {league} unpriced prop sample: {miss['sample']}")
    return out


def pull_props(prev: dict, web: str, log=print) -> dict:
    props = dict(prev.get("props") or {})
    for lg in ESPN:
        if not upcoming(web, lg):
            continue
        got = espn_props(lg, log)
        if got:
            props[lg] = {"book": "DraftKings", "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "players": got}
    return props


def attach_gids(lines: dict, web: str, log=print):
    """Tie each consensus game to the page's game id (team names + start time), and say how many matched."""
    for lg, blob in (lines or {}).items():
        try:
            G = json.load(open(os.path.join(web, PAGE[lg]))).get("games") or []
        except (OSError, ValueError):
            continue
        def keys(t):
            return {nm(t.get("name")), nm(f"{t.get('city') or ''} {t.get('name') or ''}"), nm(t.get("abbr"))} - {""}
        hit = 0
        for x in blob.get("games") or []:
            fh, fa = nm(x.get("home")), nm(x.get("away"))
            tx = dt.datetime.fromisoformat(str(x.get("t")).replace("Z", "+00:00")) if x.get("t") else None
            for g in G:
                kh, ka = keys(g.get("home") or {}), keys(g.get("away") or {})
                if any(fh.endswith(k) for k in kh) and any(fa.endswith(k) for k in ka):
                    tg = g.get("start_utc")
                    if tx and tg and abs(dt.datetime.fromisoformat(str(tg).replace("Z", "+00:00")) - tx) > dt.timedelta(hours=18):
                        continue
                    x["gid"] = str(g.get("game_id")); hit += 1; break
        open_games = sum(1 for g in G if g.get("state") not in ("post", "in"))
        log(f"odds: {lg} market lines matched to {hit} page games ({open_games} on the page)")


def merge_sharp(out: dict, sh: dict, log=print):
    """Fold SharpAPI's DraftKings + FanDuel pull into the page's odds: DraftKings (ESPN, the live source) keeps every rung
    it hangs; FanDuel fills the rest, tagged in "bk"; "fair" is the two-book no-vig chance; game lines are the two
    books' consensus."""
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    for lg, v in sh.items():
        if v["props"]:
            cur = out["props"].get(lg) or {}
            dk = cur.get("players") or {}
            players, bk = {}, {}
            for who, q in v["props"].items():
                players[who] = dict(q)
                tags = {k: t for k, t in (v["bk"].get(who) or {}).items() if k not in (dk.get(who) or {})}
                if tags:
                    bk[who] = tags
            for who, q in dk.items():
                players.setdefault(who, {}).update(q)
            out["props"][lg] = {"book": "DraftKings" + (" + FanDuel" if bk else ""), "fetched_at": cur.get("fetched_at") or now,
                                "players": players, "bk": bk, "fair": v["fair"], "sharp_at": v["fetched_at"]}
        if v["games"]:
            out.setdefault("lines", {})[lg] = {"fetched_at": v["fetched_at"], "books": "DraftKings + FanDuel", "games": v["games"]}


def run(state: str = "state", log=print):
    site = os.path.join(state, "site"); web = os.path.join(site, "web")
    os.makedirs(web, exist_ok=True)
    p = os.path.join(site, "odds.json")
    try:
        prev = json.load(open(p))
    except (OSError, ValueError):
        prev = {}
    now = dt.datetime.now(dt.timezone.utc)
    out = {"lines": {}}
    for lg, L in (prev.get("lines") or {}).items():      # last good lines, minus games that have started
        keep = [g for g in L.get("games") or [] if g.get("t") and dt.datetime.fromisoformat(str(g["t"]).replace("Z", "+00:00")) > now]
        if keep:
            out["lines"][lg] = dict(L, games=keep)
    out["props"] = pull_props(prev, web, log)
    from calib import sharp
    sh = sharp.pull(list(ESPN), os.environ.get("SHARP_API_KEY", ""), log)   # every league: the API only returns games to come
    out["sharp"] = {lg: {"fetched_at": v["fetched_at"], "complete": v["complete"], "games": len(v["games"]), "players": len(v["props"])} for lg, v in sh.items()}
    merge_sharp(out, sh, log)
    attach_gids(out.get("lines"), web, log)
    out["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    txt = json.dumps(out, separators=(",", ":"))
    for d in (site, web):
        with open(os.path.join(d, "odds.json"), "w") as f:
            f.write(txt)
    n = {lg: len(v.get("games") or []) for lg, v in (out.get("lines") or {}).items()}
    log(f"odds: lines {n} · props {[k for k in out['props']]}")


if __name__ == "__main__":
    a = argparse.ArgumentParser(prog="calib.odds")
    a.add_argument("--state", default="state")
    run(a.parse_args().state)
