"""NFL game lines for the model: the DraftKings + FanDuel consensus that calib.odds saves from SharpAPI (odds.json).

from_market() turns that file's NFL games into the event shape consensus() and match() read, so the model prices off
the two books' line (the most common line, median no-vig chance). No paid feed: when odds.json has no NFL games the
model uses nflverse's posted lines.
"""
from __future__ import annotations

import json
import os
import statistics

import pandas as pd

from .teams import FULL


def implied(a: float) -> float:
    return -a / (-a + 100.0) if a < 0 else 100.0 / (a + 100.0)


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


def from_market(path: str) -> dict | None:
    """odds.json NFL games -> {"fetched_at", "events": [...]} in the shape consensus() and match() read."""
    try:
        d = json.load(open(path))
    except (OSError, ValueError):
        return None
    L = (d.get("lines") or {}).get("NFL") or {}
    evs = []
    for g in L.get("games") or []:
        if not g.get("home") or not g.get("away") or not g.get("t"):
            continue
        h, a, m = g["home"], g["away"], []
        if g.get("ml"):
            m.append({"key": "h2h", "outcomes": [{"name": h, "price": g["ml"]["home"]}, {"name": a, "price": g["ml"]["away"]}]})
        if g.get("spread"):
            sp = g["spread"]
            m.append({"key": "spreads", "outcomes": [{"name": h, "point": sp["home"], "price": sp["home_price"]},
                                                     {"name": a, "point": -sp["home"], "price": sp["away_price"]}]})
        if g.get("total"):
            t = g["total"]
            m.append({"key": "totals", "outcomes": [{"name": "Over", "point": t["line"], "price": t["over"]},
                                                    {"name": "Under", "point": t["line"], "price": t["under"]}]})
        if m:
            evs.append({"home_team": h, "away_team": a, "commence_time": g["t"], "bookmakers": [{"key": "consensus", "markets": m}]})
    return {"fetched_at": L.get("fetched_at") or d.get("generated_at"), "events": evs} if evs else None


def load_cached(path: str) -> dict | None:
    try:
        return json.load(open(path)) if os.path.exists(path) else None
    except (OSError, ValueError):
        return None
