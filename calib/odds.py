"""Market odds for the Pikt pages: consensus game lines (The Odds API) and DraftKings player props (ESPN's free feed).

python -m calib.odds [--state state]

Game lines: one /odds request per league returns every upcoming game (spread, total, moneyline from US books) and
costs 3 credits. The consensus is the most common line across books, priced at the median of the books on it.
Budget: a league is pulled only when it has games coming up and its last pull is old enough (NHL / NBA twice a day,
NFL once), and never once the month's usage would pass ODDS_MONTH_CAP (480 of 500 by default). Usage is read for
free from /v4/sports before any paid call, so the cap holds whatever else uses the key.
Props: ESPN's core odds feed carries DraftKings' prop prices for free (no key). NHL milestones and anytime goals are
used (nhlmodel.espn_props); NFL and NBA props keep the pages' own prices for now.
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
def pull_props(prev: dict, web: str, log=print) -> dict:
    props = dict(prev.get("props") or {})
    if upcoming(web, "NHL"):
        try:
            from nhlmodel import espn_props
            d = json.load(open(os.path.join(web, PAGE["NHL"])))
            got = espn_props.fetch((d.get("meta") or {}).get("date") or dt.date.today().isoformat(), log=log)
            if got.get("players"):
                props["NHL"] = {"book": "DraftKings", "fetched_at": got["fetched_at"],
                                "players": {nm(k): v for k, v in got["players"].items()}}
        except Exception as e:
            log(f"odds: NHL props failed ({e})")
    return props


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
