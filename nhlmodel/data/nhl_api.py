"""NHL API (api-web.nhle.com) adapter: schedule, results, EN goals, P1 goals, starting goalies.

Parsing is separated from fetching so it can be unit-tested offline.
Field names follow the public gamecenter play-by-play JSON:
  plays[].typeDescKey == "goal", plays[].periodDescriptor.{number, periodType},
  plays[].situationCode = "<awayGoalie><awaySkaters><homeSkaters><homeGoalie>",
  plays[].details.{eventOwnerTeamId, scoringPlayerId, assist1PlayerId, assist2PlayerId},
  homeTeam/awayTeam.{id, abbrev, score}, gameOutcome.lastPeriodType, gameDate, season, gameType.
"""
from __future__ import annotations

import json
import os
import time

import pandas as pd

BASE = "https://api-web.nhle.com/v1"


def parse_pbp(js: dict) -> tuple[dict, list[dict]]:
    """Return (games-table row, goal events) for one completed game."""
    home, away = js["homeTeam"], js["awayTeam"]
    hid = home["id"]
    row = dict(game_id=int(js["id"]), date=pd.Timestamp(js["gameDate"]).normalize(),
               season=int(str(js["season"])[:4]), home=home["abbrev"], away=away["abbrev"],
               home_reg_nonen=0, away_reg_nonen=0, home_en_reg=0, away_en_reg=0,
               home_final=int(home.get("score", 0)), away_final=int(away.get("score", 0)),
               decision=(js.get("gameOutcome") or {}).get("lastPeriodType", "REG"),
               home_p1=0, away_p1=0)
    goals = []
    for p in js.get("plays", []):
        if p.get("typeDescKey") != "goal":
            continue
        pd_ = p.get("periodDescriptor", {})
        ptype, pnum = pd_.get("periodType", "REG"), int(pd_.get("number", 0))
        if ptype == "SO":
            continue
        det = p.get("details", {})
        is_home = det.get("eventOwnerTeamId") == hid
        sc = str(p.get("situationCode", "1551")).zfill(4)
        # empty net = the conceding team's goalie digit is 0
        en = (sc[0] == "0") if is_home else (sc[3] == "0")
        side = "home" if is_home else "away"
        if ptype == "REG":
            if en:
                row[f"{side}_en_reg"] += 1
            else:
                row[f"{side}_reg_nonen"] += 1
            if pnum == 1:
                row[f"{side}_p1"] += 1
        goals.append(dict(game_id=row["game_id"], team=row[side], period=pnum, period_type=ptype,
                          empty_net=en, scorer=det.get("scoringPlayerId"),
                          a1=det.get("assist1PlayerId"), a2=det.get("assist2PlayerId")))
    return row, goals


def parse_starting_goalies(box: dict) -> list[dict]:
    out = []
    gid = int(box["id"])
    for side in ("homeTeam", "awayTeam"):
        team = box[side]["abbrev"]
        for g in box.get("playerByGameStats", {}).get(side, {}).get("goalies", []):
            if g.get("starter"):
                out.append(dict(game_id=gid, team=team, player_id=g["playerId"],
                                name=(g.get("name") or {}).get("default", ""), pos="G", line="G1",
                                pp_unit=0, confirmed=True))
    return out


def _get(session, url, cache_dir=None, sleep=0.25):
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        f = os.path.join(cache_dir, url.replace(BASE, "").strip("/").replace("/", "_") + ".json")
        if os.path.exists(f):
            with open(f) as fh:
                return json.load(fh)
    r = session.get(url, timeout=30)
    r.raise_for_status()
    js = r.json()
    if cache_dir:
        with open(f, "w") as fh:
            json.dump(js, fh)
    time.sleep(sleep)
    return js


def fetch_games(start, end, cache_dir="data/raw/nhl_api", game_types=(2,)) -> dict:
    """Fetch completed regular-season games in [start, end]. Needs network access to api-web.nhle.com."""
    import requests
    s = requests.Session()
    games, goals, goalies = [], [], []
    d = pd.Timestamp(start)
    seen = set()
    while d <= pd.Timestamp(end):
        sched = _get(s, f"{BASE}/schedule/{d.date()}", cache_dir)
        for wk in sched.get("gameWeek", []):
            for g in wk.get("games", []):
                if g["id"] in seen or g.get("gameType") not in game_types or g.get("gameState") not in ("OFF", "FINAL"):
                    continue
                seen.add(g["id"])
                pbp = _get(s, f"{BASE}/gamecenter/{g['id']}/play-by-play", cache_dir)
                row, gl = parse_pbp(pbp)
                games.append(row); goals.extend(gl)
                box = _get(s, f"{BASE}/gamecenter/{g['id']}/boxscore", cache_dir)
                for x in parse_starting_goalies(box):
                    x["date"] = row["date"]
                    goalies.append(x)
        d += pd.Timedelta(days=7)
    games = pd.DataFrame(games)
    if len(games):
        games = games[(games.date >= pd.Timestamp(start)) & (games.date <= pd.Timestamp(end))]
    return dict(games=games, goal_events=pd.DataFrame(goals), starting_goalies=pd.DataFrame(goalies))
