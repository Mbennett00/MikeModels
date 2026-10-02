"""The Odds API (the-odds-api.com, v4) -> canonical odds rows.

Game markets come from one call to /odds; props and period/team-total markets need
one call per event to /events/{id}/odds. Each call costs credits
(= markets x regions), so prop fetching can be limited with ``prop_markets``.
Player names are matched to NHL ids through the slate's lineups (accent/case insensitive).
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from .teams import abbrev, norm_name

BASE = "https://api.the-odds-api.com/v4/sports/icehockey_nhl"
GAME_MARKETS = "h2h,spreads,totals"
EVENT_MARKETS = ["team_totals", "totals_p1", "h2h_3_way_p1"]
PROP_MARKETS = ["player_goal_scorer_anytime", "player_shots_on_goal", "player_assists", "player_points"]
MAP = {"h2h": "moneyline", "spreads": "puckline", "totals": "total", "team_totals": "team_total",
       "totals_p1": "p1_total", "h2h_3_way_p1": "p1_3way", "player_goal_scorer_anytime": "goals",
       "player_shots_on_goal": "sog", "player_assists": "assists", "player_points": "points"}


def _et_date(ts: str) -> pd.Timestamp:
    return pd.Timestamp(ts).tz_convert("America/New_York").tz_localize(None).normalize()


def player_index(roster: pd.DataFrame) -> dict:
    """Name -> NHL id. Adds 'first-initial + last name' keys when unique, so 'Christopher Tanev'
    finds 'Chris Tanev' and 'Alex Romanov' finds 'Alexander Romanov'."""
    idx = {norm_name(n): p for n, p in zip(roster.name, roster.player_id)}
    alt: dict = {}
    for n, p in zip(roster.name, roster.player_id):
        parts = norm_name(n).split()
        if len(parts) >= 2:
            alt.setdefault(f"{parts[0][0]} {parts[-1]}", set()).add(p)
    for k, v in alt.items():
        if len(v) == 1:
            idx.setdefault(k, next(iter(v)))
    return idx


# common transliteration / short-name variants between sportsbooks and the NHL
FIRST_ALIASES = {"yegor": "egor", "egor": "yegor", "evgeny": "evgeni", "evgeni": "evgeny", "yevgeni": "evgeni",
                 "alexander": "alexandre", "alexandre": "alexander", "alex": "alexander", "nikolai": "nikolay",
                 "nikolay": "nikolai", "mitch": "mitchell", "mitchell": "mitch", "matt": "matthew", "matthew": "matt",
                 "zach": "zachary", "zachary": "zach", "josh": "joshua", "joshua": "josh", "jake": "jacob",
                 "jacob": "jake", "nick": "nicholas", "nicholas": "nick", "mike": "michael", "michael": "mike"}


def lookup(idx: dict, name: str):
    n = norm_name(name)
    if n in idx:
        return idx[n]
    parts = n.split()
    if len(parts) < 2:
        return None
    alt = FIRST_ALIASES.get(parts[0])
    if alt and f"{alt} {' '.join(parts[1:])}" in idx:
        return idx[f"{alt} {' '.join(parts[1:])}"]
    return idx.get(f"{parts[0][0]} {parts[-1]}")


def parse_event(ev: dict, schedule: pd.DataFrame, name_to_id: dict, snapshot: str, fetched_at: str) -> tuple[list, set]:
    """Rows for one event; returns (rows, unmatched player names)."""
    home, away = abbrev(ev["home_team"]), abbrev(ev["away_team"])
    date = _et_date(ev["commence_time"])
    m = schedule[(schedule.home == home) & (schedule.away == away)]
    if m.empty:
        return [], set()
    gid = int(m.game_id.iloc[0])
    side_of = {norm_name(ev["home_team"]): "home", norm_name(ev["away_team"]): "away"}
    rows, missing = [], set()
    for bk in ev.get("bookmakers", []):
        for mk in bk.get("markets", []):
            market = MAP.get(mk["key"])
            if market is None:
                continue
            for o in mk.get("outcomes", []):
                name, desc, point = o.get("name", ""), o.get("description"), o.get("point")
                sel, line, pid = None, point, np.nan
                if market in ("moneyline", "puckline", "p1_3way"):
                    sel = "draw" if norm_name(name) == "draw" else side_of.get(norm_name(name))
                    if market == "puckline" and (point is None or abs(point) != 1.5):
                        continue
                    if market != "puckline":
                        line = np.nan
                elif market in ("total", "p1_total"):
                    sel = name.lower()
                elif market == "team_total":
                    side = side_of.get(norm_name(desc or ""))
                    sel = f"{side}_{name.lower()}" if side else None
                else:   # player props
                    player = desc if desc else name
                    if name.lower() in ("over", "under"):
                        sel = name.lower()
                    elif name.lower() in ("yes", "no"):
                        sel = {"yes": "over", "no": "under"}[name.lower()]
                    else:
                        sel = "over"      # some books list the player as the outcome name for anytime scorer
                    if market == "goals" and line is None:
                        line = 0.5
                    pid = lookup(name_to_id, player)
                    if pid is None:
                        missing.add(player)
                        continue
                if sel is None:
                    continue
                rows.append(dict(date=date, game_id=gid, market=market, player_id=pid, selection=sel,
                                 line=line, price=o["price"], book=bk["key"], snapshot=snapshot,
                                 fetched_at=fetched_at))
    return rows, missing


def fetch(schedule: pd.DataFrame, lineups: pd.DataFrame, snapshot: str, api_key: str | None = None,
          regions: str = "us", props: bool = True, game_ids: set | None = None, log=print,
          bookmakers: str | None = None, game_only: bool = False) -> pd.DataFrame:
    """game_only + bookmakers='williamhill_us' (Caesars) is the lean mode: one /odds call, 3 credits."""
    import requests
    key = api_key or os.environ.get("ODDS_API_KEY")
    if not key:
        log("ODDS_API_KEY not set: no odds fetched")
        return pd.DataFrame()
    now = pd.Timestamp.now('UTC').isoformat()
    name_to_id = player_index(lineups)
    params = dict(apiKey=key, oddsFormat="american")
    if bookmakers:
        params["bookmakers"] = bookmakers      # replaces regions; cost = markets x 1
    else:
        params["regions"] = regions
    r = requests.get(f"{BASE}/odds", params=dict(params, markets=GAME_MARKETS), timeout=30)
    r.raise_for_status()
    log(f"odds api: {r.headers.get('x-requests-remaining')} credits left")
    rows, missing = [], set()
    events = r.json()
    with_book = sum(1 for ev in events if ev.get("bookmakers"))
    log(f"odds api: {len(events)} NHL events returned, {with_book} with {bookmakers or regions} prices")
    for ev in events:
        rr, mm = parse_event(ev, schedule, name_to_id, snapshot, now)
        rows += rr; missing |= mm
    extra = [] if game_only else EVENT_MARKETS + (PROP_MARKETS if props else [])
    for ev in (events if extra else []):
        home, away = abbrev(ev["home_team"]), abbrev(ev["away_team"])
        m = schedule[(schedule.home == home) & (schedule.away == away)]
        if m.empty or (game_ids is not None and int(m.game_id.iloc[0]) not in game_ids):
            continue
        r = requests.get(f"{BASE}/events/{ev['id']}/odds", params=dict(params, markets=",".join(extra)), timeout=30)
        if r.status_code != 200:
            log(f"odds api event {ev['id']}: HTTP {r.status_code} {r.text[:200]}")
            continue
        rr, mm = parse_event(r.json(), schedule, name_to_id, snapshot, now)
        rows += rr; missing |= mm
    if missing:
        log(f"odds api: {len(missing)} player names not matched to lineups, e.g. {sorted(missing)[:5]}")
    out = pd.DataFrame(rows)
    if game_ids is not None and len(out):
        out = out[out.game_id.isin(game_ids)]
    return out
