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


# ---- DraftKings player props (The Odds API event odds: 1 credit per market per game) ----
EVENT_URL = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/events/{}/odds"
PROP_MARKETS = {"player_anytime_td": "td", "player_reception_yds": "rec_yds", "player_rush_yds": "rush_yds",
                "player_pass_yds": "pass_yds", "player_receptions": "rec"}


def parse_props(ev: dict, norm, book: str = "draftkings") -> dict:
    """One event's odds -> {normalised name: {"market|line": {"o": over price, "u": under price}}}."""
    out: dict = {}
    for bk in ev.get("bookmakers", []):
        if bk.get("key") != book:
            continue
        for mk in bk.get("markets", []):
            m = PROP_MARKETS.get(mk.get("key"))
            if not m:
                continue
            for o in mk.get("outcomes", []):
                who, side, price = o.get("description"), str(o.get("name", "")).lower(), o.get("price")
                if not who or price is None or side not in ("over", "under", "yes", "no"):
                    continue
                line = 0.5 if m == "td" else o.get("point")
                if line is None:
                    continue
                d = out.setdefault(norm(who), {}).setdefault(f"{m}|{float(line):g}", {})
                d["o" if side in ("over", "yes") else "u"] = int(round(price))
    return out


def props_due(cached: dict | None, now_et: pd.Timestamp, events_today: list, force: bool = False) -> bool:
    """One props pull per game day (first run after 7am ET), for that day's games only."""
    if not events_today:
        return False
    if force:
        return True
    if now_et.hour < 7:
        return False
    last = (cached or {}).get("pulled_on")
    return last != str(now_et.date())


def fetch_props(key: str, events: list, norm, log=print, book: str = "draftkings") -> dict:
    """{event id: {"commence": ..., "players": {...}}} for the given events; skips any that fail."""
    out, left = {}, None
    for ev in events:
        try:
            r = requests.get(EVENT_URL.format(ev["id"]), params=dict(apiKey=key, regions="us", bookmakers=book,
                             markets=",".join(PROP_MARKETS), oddsFormat="american"), timeout=60)
            r.raise_for_status()
            left = r.headers.get("x-requests-remaining", left)
            out[ev["id"]] = dict(commence=ev.get("commence_time"), home=ev.get("home_team"), away=ev.get("away_team"),
                                 players=parse_props(r.json(), norm, book))
        except Exception as e:
            log(f"nfl props odds: {ev.get('home_team')} failed ({e})")
    log(f"nfl props odds: DraftKings props for {sum(len(v['players']) for v in out.values())} players "
        f"in {len(out)} games, credits left {left}")
    return out


# ---- anytime TD consensus (every US book; the events list is free, the TD market is 1 credit a game) ----
EVENTS_URL = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/events"


def fetch_events(key: str, log=print) -> list:
    """Upcoming NFL events (ids, teams, kickoff). Costs no credits."""
    try:
        r = requests.get(EVENTS_URL, params=dict(apiKey=key), timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log(f"nfl events: {e}")
        return []


def _dec(a: float) -> float:
    return 1 + a / 100 if a > 0 else 1 + 100 / -a


def _am(d: float) -> int:
    return int(round(100 * (d - 1))) if d >= 2 else int(round(-100 / (d - 1)))


def parse_td(ev: dict, norm) -> dict:
    """{normalised name: {"td|0.5": {"o": consensus price, "n": books, "best": best price}}}.
    Consensus = the median implied probability of 'Yes' across books, back to American odds."""
    by: dict = {}
    for bk in ev.get("bookmakers", []):
        for mk in bk.get("markets", []):
            if mk.get("key") != "player_anytime_td":
                continue
            for o in mk.get("outcomes", []):
                who, side, price = o.get("description"), str(o.get("name", "")).lower(), o.get("price")
                if who and price is not None and side in ("yes", "over") and abs(price) >= 100:
                    by.setdefault(norm(who), []).append(float(price))
    out = {}
    for who, prices in by.items():
        imp = sorted(1 / _dec(p) for p in prices)
        n = len(imp); med = imp[n // 2] if n % 2 else (imp[n // 2 - 1] + imp[n // 2]) / 2
        out[who] = {"td|0.5": {"o": _am(1 / med), "n": n, "best": int(max(prices, key=_dec))}}
    return out


def fetch_td(key: str, events: list, norm, log=print) -> dict:
    """{event id: {"commence", "players": parse_td(...)}} for the given events (1 credit each)."""
    out, left = {}, None
    for ev in events:
        try:
            r = requests.get(EVENT_URL.format(ev["id"]), params=dict(apiKey=key, regions="us", markets="player_anytime_td",
                             oddsFormat="american"), timeout=60)
            r.raise_for_status()
            left = r.headers.get("x-requests-remaining", left)
            out[ev["id"]] = dict(gid=ev.get("gid"), commence=ev.get("commence_time"), home=ev.get("home_team"), away=ev.get("away_team"), players=parse_td(r.json(), norm))
        except Exception as e:
            log(f"nfl td odds: {ev.get('home_team')} failed ({e})")
    log(f"nfl td odds: consensus anytime-TD prices for {sum(len(v['players']) for v in out.values())} players in {len(out)} games, credits left {left}")
    return out
