"""NFL game lines from The Odds API (americanfootball_nfl): one /odds call, all US books, 3 credits.

The market price for each game is the consensus: the line most books hang, and the median no-vig
chance across the books at that line. The chosen book's own price (Caesars) is kept when it is in the feed.
"""
from __future__ import annotations

import json
import os
import statistics

import pandas as pd
import requests

from .teams import FULL

URL = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds"


def implied(a: float) -> float:
    return -a / (-a + 100.0) if a < 0 else 100.0 / (a + 100.0)


def fetch(key: str, log=print) -> dict:
    r = requests.get(URL, params=dict(apiKey=key, regions="us", markets="h2h,spreads,totals", oddsFormat="american"),
                     timeout=60)
    r.raise_for_status()
    log(f"nfl odds: {len(r.json())} events, credits left {r.headers.get('x-requests-remaining')}")
    return dict(fetched_at=pd.Timestamp.now(tz="UTC").isoformat(), events=r.json(),
                remaining=r.headers.get("x-requests-remaining"))


def _book_key(bk: dict) -> str:
    return "williamhill_us" if "caesars" in bk.get("title", "").lower() else bk.get("key", "")


def consensus(ev: dict, book: str | None = None) -> dict:
    """{'ml': {...}, 'spread': {...}, 'total': {...}} for one event; sides are home/away and over/under."""
    home, away = ev["home_team"], ev["away_team"]
    ml, sp, tt = [], [], []
    for bk in ev.get("bookmakers", []):
        bkey = _book_key(bk)
        for mk in bk.get("markets", []):
            oc = {o["name"]: o for o in mk.get("outcomes", [])}
            try:
                if mk["key"] == "h2h" and home in oc and away in oc:
                    ml.append((bkey, oc[home]["price"], oc[away]["price"]))
                elif mk["key"] == "spreads" and home in oc and away in oc:
                    sp.append((bkey, oc[home]["point"], oc[home]["price"], oc[away]["price"]))
                elif mk["key"] == "totals" and "Over" in oc and "Under" in oc:
                    tt.append((bkey, oc["Over"]["point"], oc["Over"]["price"], oc["Under"]["price"]))
            except KeyError:
                continue
    out = {}

    def nv(a, b):
        ia, ib = implied(a), implied(b)
        return ia / (ia + ib)
    if ml:
        mine = next((x for x in ml if x[0] == book), None)
        out["ml"] = dict(p_home=statistics.median(nv(h, a) for _, h, a in ml), n=len(ml),
                         book_home=mine[1] if mine else None, book_away=mine[2] if mine else None)
    for name, rows in (("spread", sp), ("total", tt)):
        if not rows:
            continue
        pts = [r[1] for r in rows]
        line = max(set(pts), key=lambda p: (pts.count(p), -abs(p - statistics.median(pts))))
        at = [r for r in rows if r[1] == line]
        mine = next((x for x in at if x[0] == book), None)
        d = dict(line=line, p_first=statistics.median(nv(r[2], r[3]) for r in at), n=len(at),
                 book_first=mine[2] if mine else None, book_second=mine[3] if mine else None)
        out[name] = d
    return out


def match(events: list, games: pd.DataFrame) -> dict:
    """game_id -> event, matching team names and kickoff within a day."""
    out = {}
    for ev in events:
        h, a = FULL.get(ev.get("home_team")), FULL.get(ev.get("away_team"))
        t = pd.Timestamp(ev["commence_time"]).tz_convert("America/New_York").tz_localize(None)
        m = games[(games.home_team == h) & (games.away_team == a) & ((games.gameday - t.normalize()).abs() <= pd.Timedelta(days=1))]
        if len(m):
            out[m.game_id.iloc[0]] = ev
    return out


def load_cached(path: str) -> dict | None:
    try:
        return json.load(open(path)) if os.path.exists(path) else None
    except (OSError, ValueError):
        return None


def due(cached: dict | None, now_et: pd.Timestamp, has_games: bool, force: bool = False) -> bool:
    """One pull a day: the first run after 10:30am ET on a day with games in the coming week."""
    if force:
        return True
    if not has_games or now_et.hour + now_et.minute / 60 < 10.5:
        return False
    if not cached:
        return True
    last = pd.Timestamp(cached["fetched_at"]).tz_convert("America/New_York")
    return last.date() < now_et.date()
