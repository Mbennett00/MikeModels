"""Market odds for the Pikt pages: consensus game lines (The Odds API) and DraftKings player props (ESPN's free feed).

python -m calib.odds [--state state]

Game lines: one /odds request per league returns every upcoming game (spread, total, moneyline from US books) and
costs 3 credits. The consensus is the most common line across books, priced at the median of the books on it.
Budget: a league is pulled only when it has games coming up and its last pull is old enough (NHL / NBA twice a day,
NFL once), and never once the month's usage would pass ODDS_MONTH_CAP (480 of 500 by default). Usage is read for
free from /v4/sports before any paid call, so the cap holds whatever else uses the key.
Props: ESPN's core odds feed carries DraftKings' prop prices for free (no key): milestones and anytime scorers for
all three leagues. The pages show props at DraftKings' lines and prices only.
Writes state/site/odds.json (kept with the state) and state/site/web/odds.json. Never raises: a failed pull keeps
the last good prices, and the pages fall back to their own when a game has none.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import statistics
import unicodedata

import requests

API = "https://api.the-odds-api.com/v4"
LEAGUES = {"NHL": ("icehockey_nhl", 10), "NBA": ("basketball_nba", 10), "NFL": ("americanfootball_nfl", 22)}   # key, hours between pulls
PAGE = {"NHL": "data.json", "NBA": "nba.json", "NFL": "nfl.json"}
COST = 3   # h2h + spreads + totals, one region
CAP = int(os.environ.get("ODDS_MONTH_CAP", "480"))
UA = {"User-Agent": "Mozilla/5.0 (Pikt odds)"}


def nm(s: str) -> str:
    """Same key the pages use (book.js bkNm): accents off, suffixes off, letters only."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s)
    return re.sub(r"[^a-z]", "", s)


def to_prob(a: float) -> float:
    return 100 / (a + 100) if a > 0 else -a / (-a + 100)


def to_am(p: float) -> int:
    p = min(max(p, 0.01), 0.99)
    return round(-100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)


def mid_price(prices: list) -> int | None:
    """Median price, taken in probability space so +/- odds average properly."""
    return to_am(statistics.median(to_prob(x) for x in prices)) if prices else None


def consensus(ev: dict) -> dict | None:
    home, away = ev.get("home_team"), ev.get("away_team")
    ml_h, ml_a, sp, tot = [], [], {}, {}
    for bk in ev.get("bookmakers") or []:
        for m in bk.get("markets") or []:
            o = {x.get("name"): x for x in m.get("outcomes") or []}
            if m.get("key") == "h2h" and home in o and away in o:
                ml_h.append(o[home]["price"]); ml_a.append(o[away]["price"])
            elif m.get("key") == "spreads" and home in o and away in o and o[home].get("point") is not None:
                sp.setdefault(float(o[home]["point"]), []).append((o[home]["price"], o[away]["price"]))
            elif m.get("key") == "totals" and "Over" in o and "Under" in o and o["Over"].get("point") is not None:
                tot.setdefault(float(o["Over"]["point"]), []).append((o["Over"]["price"], o["Under"]["price"]))
    out = {"home": home, "away": away, "t": ev.get("commence_time"), "books": len(ev.get("bookmakers") or [])}
    if ml_h:
        out["ml"] = {"home": mid_price(ml_h), "away": mid_price(ml_a)}
    if sp:
        pt, L = max(sp.items(), key=lambda kv: (len(kv[1]), -abs(kv[0])))   # the line most books hang
        out["spread"] = {"home": pt, "home_price": mid_price([x[0] for x in L]), "away_price": mid_price([x[1] for x in L])}
    if tot:
        pt, L = max(tot.items(), key=lambda kv: (len(kv[1]), -abs(kv[0] - statistics.median(tot))))
        out["total"] = {"line": pt, "over": mid_price([x[0] for x in L]), "under": mid_price([x[1] for x in L])}
    return out if len(out) > 4 else None


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


def usage(key: str) -> int | None:
    """Credits used this period, from the free /sports endpoint."""
    try:
        r = requests.get(f"{API}/sports", params={"apiKey": key}, timeout=20)
        return int(r.headers.get("x-requests-used")) if r.ok else None
    except Exception:
        return None


def pull_lines(prev: dict, web: str, key: str, log=print) -> dict:
    lines = dict(prev.get("lines") or {})
    pulled = dict(prev.get("pulled") or {})
    if not key:
        log("odds: no ODDS_API_KEY; keeping the last prices"); return {"lines": lines, "pulled": pulled, "used": prev.get("used")}
    now = dt.datetime.now(dt.timezone.utc)
    due = [lg for lg, (_, hrs) in LEAGUES.items() if upcoming(web, lg)
           and (lg not in pulled or now - dt.datetime.fromisoformat(pulled[lg]) >= dt.timedelta(hours=hrs - 0.5))]
    used = prev.get("used")
    if not due:
        log("odds: nothing due (no upcoming games or pulled recently)")
        return {"lines": lines, "pulled": pulled, "used": used}
    used = usage(key)
    if used is None:
        log("odds: couldn't read usage; skipping paid pulls"); return {"lines": lines, "pulled": pulled, "used": prev.get("used")}
    for lg in due:
        if used + COST > CAP:
            log(f"odds: {used} credits used this month; {lg} skipped to stay under {CAP}"); continue
        try:
            r = requests.get(f"{API}/sports/{LEAGUES[lg][0]}/odds", timeout=30,
                             params={"apiKey": key, "regions": "us", "markets": "h2h,spreads,totals", "oddsFormat": "american"})
            r.raise_for_status()
            evs = r.json()
            used = int(r.headers.get("x-requests-used", used + COST))
        except Exception as e:
            log(f"odds: {lg} pull failed ({e})"); continue
        games = [c for c in (consensus(ev) for ev in evs) if c]
        lines[lg] = {"fetched_at": now.isoformat(timespec="seconds"), "games": games}
        pulled[lg] = now.isoformat(timespec="seconds")
        log(f"odds: {lg} consensus for {len(games)} games ({used} credits used this month)")
    return {"lines": lines, "pulled": pulled, "used": used}


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


def prop_kind(league: str, name: str):
    n = (name or "").lower()
    if any(w in n for w in ("1st", "2nd", "3rd", "half", "quarter", "period", "first ", "last ")):
        return None                                   # partial-game and first/last scorer markets aren't on the page
    if league == "NFL" and "2 or more touchdowns" in n:
        return "td", 1.5
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


def run(state: str = "state", log=print):
    site = os.path.join(state, "site"); web = os.path.join(site, "web")
    os.makedirs(web, exist_ok=True)
    p = os.path.join(site, "odds.json")
    try:
        prev = json.load(open(p))
    except (OSError, ValueError):
        prev = {}
    out = pull_lines(prev, web, os.environ.get("ODDS_API_KEY", ""), log)
    out["props"] = pull_props(prev, web, log)
    attach_gids(out.get("lines"), web, log)
    out["cap"] = CAP
    out["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    txt = json.dumps(out, separators=(",", ":"))
    for d in (site, web):
        with open(os.path.join(d, "odds.json"), "w") as f:
            f.write(txt)
    n = {lg: len(v.get("games") or []) for lg, v in (out.get("lines") or {}).items()}
    log(f"odds: lines {n} · props {[k for k in out['props']]} · {out.get('used')} credits used")


if __name__ == "__main__":
    a = argparse.ArgumentParser(prog="calib.odds")
    a.add_argument("--state", default="state")
    run(a.parse_args().state)
