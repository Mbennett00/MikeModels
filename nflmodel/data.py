"""nflverse data (https://github.com/nflverse/nflverse-data): schedule with lines, and play-by-play.

nflverse refreshes the current season's play-by-play overnight after each game day and the schedule
(results, lines, projected starting QBs) several times a day. Every run re-downloads the schedule and
the current season; finished seasons are reduced to small per-game tables and kept in the cache.
"""
from __future__ import annotations

import io
import os

import numpy as np
import pandas as pd
import requests

REL = "https://github.com/nflverse/nflverse-data/releases/download"
SCHEDULE_URLS = (REL + "/schedules/games.csv", "https://github.com/nflverse/nfldata/raw/master/data/games.csv")
PBP_URL = REL + "/pbp/play_by_play_{season}.parquet"
LOCAL = os.environ.get("NFL_LOCAL_DIR")   # tests / offline: read games.csv and pbp{season}.parquet from here
FIRST_SEASON = 2018
TEAM_FIX = {"OAK": "LV", "SD": "LAC", "STL": "LA", "LAR": "LA"}
PBP_COLS = ["game_id", "season", "week", "season_type", "game_date", "home_team", "away_team", "posteam", "defteam",
            "play_type", "epa", "success", "wp", "pass", "rush", "qb_dropback", "passer_player_id",
            "passer_player_name", "qb_epa", "rusher_player_id", "down"]


def _get(url: str) -> bytes:
    r = requests.get(url, timeout=180, headers={"User-Agent": "Mozilla/5.0 (nflmodel)"})
    r.raise_for_status()
    return r.content


def schedule() -> pd.DataFrame:
    """Every game since 1999 with results, closing-ish lines (spread_line = home margin), QBs, roof, weather."""
    if LOCAL:
        raw = open(os.path.join(LOCAL, "games.csv"), "rb").read()
    else:
        for i, url in enumerate(SCHEDULE_URLS):
            try:
                raw = _get(url)
                break
            except Exception:
                if i == len(SCHEDULE_URLS) - 1:
                    raise
    g = pd.read_csv(io.BytesIO(raw), low_memory=False)
    for c in ("home_team", "away_team"):
        g[c] = g[c].replace(TEAM_FIX)
    g["gameday"] = pd.to_datetime(g.gameday)
    return g


def season_of(date) -> int:
    d = pd.Timestamp(date)
    return d.year if d.month >= 3 else d.year - 1


def _pbp(season: int) -> pd.DataFrame:
    if LOCAL:
        p = pd.read_parquet(os.path.join(LOCAL, f"pbp{season}.parquet"), columns=PBP_COLS)
    else:
        p = pd.read_parquet(io.BytesIO(_get(PBP_URL.format(season=season))), columns=PBP_COLS)
    for c in ("home_team", "away_team", "posteam", "defteam"):
        p[c] = p[c].replace(TEAM_FIX)
    return p


def reduce_pbp(p: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per team-game offense (EPA per pass / rush play, competitive downs only) and per QB-game dropbacks."""
    x = p[p.play_type.isin(["pass", "run"]) & p.epa.notna() & p.posteam.notna()].copy()
    x = x[(x.wp >= 0.05) & (x.wp <= 0.95)]          # drop garbage time
    x["is_pass"] = (x.qb_dropback == 1) | (x["pass"] == 1)
    x["epa_pass"] = np.where(x.is_pass, x.epa, 0.0)
    x["epa_rush"] = np.where(~x.is_pass, x.epa, 0.0)
    tg = x.groupby(["game_id", "posteam"]).agg(
        season=("season", "first"), week=("week", "first"), season_type=("season_type", "first"),
        date=("game_date", "first"), opp=("defteam", "first"), home_team=("home_team", "first"),
        n_pass=("is_pass", "sum"), n_rush=("is_pass", lambda s: int((~s).sum())),
        epa_pass=("epa_pass", "sum"), epa_rush=("epa_rush", "sum"), success=("success", "mean")).reset_index()
    tg = tg.rename(columns={"posteam": "team"})
    db = x[x.is_pass & x.passer_player_id.notna()]
    qb = db.groupby(["game_id", "posteam", "passer_player_id"]).agg(
        season=("season", "first"), date=("game_date", "first"), name=("passer_player_name", "first"),
        dropbacks=("epa", "size"), epa=("qb_epa", "sum")).reset_index().rename(columns={"posteam": "team",
                                                                                        "passer_player_id": "qb_id"})
    return tg, qb


def load(cache: str, seasons=None, log=print) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(schedule, team-games, qb-games). Finished seasons come from the cache; the current one is refetched."""
    os.makedirs(cache, exist_ok=True)
    sched = schedule()
    cur = season_of(pd.Timestamp.now(tz="America/New_York").tz_localize(None))
    played = sched[sched.result.notna()]
    cur = max(cur if cur in set(sched.season) else played.season.max(), FIRST_SEASON)
    seasons = seasons or list(range(FIRST_SEASON, cur + 1))
    tgs, qbs = [], []
    for s in seasons:
        ft, fq = os.path.join(cache, f"team_games_{s}.csv"), os.path.join(cache, f"qb_games_{s}.csv")
        if s < cur and os.path.exists(ft) and os.path.exists(fq):
            tgs.append(pd.read_csv(ft)); qbs.append(pd.read_csv(fq))
            continue
        try:
            tg, qb = reduce_pbp(_pbp(s))
        except Exception as e:   # current season before week 1, or a network hiccup: keep the cached copy
            log(f"nfl pbp {s}: {e}")
            if os.path.exists(ft):
                tgs.append(pd.read_csv(ft)); qbs.append(pd.read_csv(fq))
            continue
        tg.to_csv(ft, index=False); qb.to_csv(fq, index=False)
        log(f"nfl pbp {s}: {tg.game_id.nunique()} games, through {tg.date.max()}")
        tgs.append(tg); qbs.append(qb)
    tg = pd.concat(tgs, ignore_index=True)
    qb = pd.concat(qbs, ignore_index=True)
    for d in (tg, qb):
        d["date"] = pd.to_datetime(d.date)
    return sched, tg, qb
