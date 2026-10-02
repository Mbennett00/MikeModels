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
            "passer_player_name", "qb_epa", "rusher_player_id", "down",
            "receiver_player_id", "receiver_player_name", "rusher_player_name", "complete_pass", "receiving_yards",
            "rushing_yards", "passing_yards", "pass_touchdown", "rush_touchdown", "yardline_100", "two_point_attempt",
            "pass_attempt", "rush_attempt", "sack", "interception", "td_player_id", "td_team"]


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


def player_games(p: pd.DataFrame) -> pd.DataFrame:
    """Per player-game box score (all downs, garbage time included, as the books settle props).

    targets / receptions / receiving yards & TDs, carries / rushing yards & TDs, pass attempts / yards / TDs,
    plus red-zone (inside the 10) targets and carries, which predict touchdowns better than past TDs do."""
    x = p[p.play_type.isin(["pass", "run"]) & (p.two_point_attempt.fillna(0) == 0) & p.posteam.notna()].copy()
    x["rz"] = (x.yardline_100 <= 10).astype(int)
    base = ["game_id", "season", "week", "game_date", "posteam", "defteam"]
    rec = x[x.receiver_player_id.notna() & (x.pass_attempt == 1) & (x.sack.fillna(0) == 0)]
    rec = rec.assign(tgt=1, rz_tgt=rec.rz, rec=rec.complete_pass.fillna(0),
                     rec_yds=rec.receiving_yards.fillna(0), rec_td=rec.pass_touchdown.fillna(0))
    r1 = rec.groupby(base + ["receiver_player_id"]).agg(name=("receiver_player_name", "first"), tgt=("tgt", "sum"),
                                                        rz_tgt=("rz_tgt", "sum"), rec=("rec", "sum"),
                                                        rec_yds=("rec_yds", "sum"), rec_td=("rec_td", "sum")).reset_index()
    r1 = r1.rename(columns={"receiver_player_id": "player_id"})
    ru = x[x.rusher_player_id.notna() & (x.rush_attempt == 1)]
    ru = ru.assign(car=1, rz_car=ru.rz, rush_yds=ru.rushing_yards.fillna(0), rush_td=ru.rush_touchdown.fillna(0))
    r2 = ru.groupby(base + ["rusher_player_id"]).agg(name=("rusher_player_name", "first"), car=("car", "sum"),
                                                     rz_car=("rz_car", "sum"), rush_yds=("rush_yds", "sum"),
                                                     rush_td=("rush_td", "sum")).reset_index()
    r2 = r2.rename(columns={"rusher_player_id": "player_id"})
    pa = x[x.passer_player_id.notna() & (x.pass_attempt == 1) & (x.sack.fillna(0) == 0)]
    pa = pa.assign(att=1, cmp=pa.complete_pass.fillna(0), pass_yds=pa.passing_yards.fillna(0),
                   pass_td=pa.pass_touchdown.fillna(0), ints=pa.interception.fillna(0))
    r3 = pa.groupby(base + ["passer_player_id"]).agg(name=("passer_player_name", "first"), att=("att", "sum"),
                                                     cmp=("cmp", "sum"), pass_yds=("pass_yds", "sum"),
                                                     pass_td=("pass_td", "sum"), ints=("ints", "sum")).reset_index()
    r3 = r3.rename(columns={"passer_player_id": "player_id"})
    keys = base + ["player_id"]
    out = r1.merge(r2, on=keys, how="outer", suffixes=("", "_r")).merge(r3, on=keys, how="outer", suffixes=("", "_p"))
    out["name"] = out.name.fillna(out.name_r).fillna(out.name_p)
    out = out.drop(columns=["name_r", "name_p"]).fillna({c: 0 for c in ("tgt", "rz_tgt", "rec", "rec_yds", "rec_td", "car",
                                                                         "rz_car", "rush_yds", "rush_td", "att", "cmp",
                                                                         "pass_yds", "pass_td", "ints")})
    return out.rename(columns={"posteam": "team", "defteam": "opp", "game_date": "date"})


def load_players(cache: str, seasons) -> pd.DataFrame:
    """Player-game box scores written by load() (one file per season)."""
    parts = [pd.read_csv(os.path.join(cache, f"player_games_{s}.csv")) for s in seasons
             if os.path.exists(os.path.join(cache, f"player_games_{s}.csv"))]
    d = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    if len(d):
        d["date"] = pd.to_datetime(d.date)
        for c in ("team", "opp"):
            d[c] = d[c].replace(TEAM_FIX)
    return d


def rosters(season: int, cache: str, log=print) -> pd.DataFrame:
    """Latest weekly roster entry per player: position, status (ACT / RES ...), headshot."""
    f = os.path.join(cache, f"roster_{season}.csv")
    cols = ["season", "week", "team", "position", "status", "full_name", "gsis_id", "headshot_url", "jersey_number"]
    try:
        if LOCAL:
            r = pd.read_csv(os.path.join(LOCAL, f"roster{season}.csv"), usecols=lambda c: c in cols)
        else:
            r = pd.read_csv(io.BytesIO(_get(REL + f"/weekly_rosters/roster_weekly_{season}.csv")), usecols=lambda c: c in cols)
        r.to_csv(f, index=False)
    except Exception as e:
        log(f"nfl roster {season}: {e}")
        if not os.path.exists(f):
            return pd.DataFrame(columns=cols)
        r = pd.read_csv(f)
    r["team"] = r.team.replace(TEAM_FIX)
    return r.sort_values("week").drop_duplicates("gsis_id", keep="last").set_index("gsis_id")


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
        fp = os.path.join(cache, f"player_games_{s}.csv")
        if s < cur and os.path.exists(ft) and os.path.exists(fq) and os.path.exists(fp):
            tgs.append(pd.read_csv(ft)); qbs.append(pd.read_csv(fq))
            continue
        try:
            raw = _pbp(s)
            tg, qb = reduce_pbp(raw)
            player_games(raw).to_csv(fp, index=False)
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


SNAP_URL = REL + "/snap_counts/snap_counts_{season}.csv"
INJ_URL = REL + "/injuries/injuries_{season}.csv"
SNAP_COLS = ["game_id", "season", "week", "player", "position", "team", "offense_pct", "defense_pct"]
INJ_COLS = ["season", "game_type", "team", "week", "gsis_id", "position", "full_name", "report_status"]


def _csv(url: str, local: str, cols: list) -> pd.DataFrame:
    if LOCAL:
        d = pd.read_csv(os.path.join(LOCAL, local), usecols=lambda c: c in cols)
    else:
        d = pd.read_csv(io.BytesIO(_get(url)), usecols=lambda c: c in cols)
    for c in ("team",):
        d[c] = d[c].replace(TEAM_FIX)
    return d


def load_rosters(cache: str, seasons, log=print) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(snap counts, official injury reports) for the seasons; the latest season is always refetched."""
    os.makedirs(cache, exist_ok=True)
    cur = max(seasons)
    out = {"snaps": [], "inj": []}
    for s in seasons:
        for kind, url, local, cols in (("snaps", SNAP_URL, f"snap{s}.csv", SNAP_COLS),
                                       ("inj", INJ_URL, f"inj{s}.csv", INJ_COLS)):
            f = os.path.join(cache, f"{kind}_{s}.csv")
            if s < cur and os.path.exists(f):
                out[kind].append(pd.read_csv(f))
                continue
            try:
                d = _csv(url.format(season=s), local, cols)
                d.to_csv(f, index=False)
            except Exception as e:
                log(f"nfl {kind} {s}: {e}")
                if not os.path.exists(f):
                    continue
                d = pd.read_csv(f)
            out[kind].append(d)
    if out["snaps"]:
        log(f"nfl snaps: {sum(len(x) for x in out['snaps'])} rows; injury reports: {sum(len(x) for x in out['inj'])} rows")
    cat = lambda xs, cols: pd.concat(xs, ignore_index=True) if xs else pd.DataFrame(columns=cols)
    return cat(out["snaps"], SNAP_COLS), cat(out["inj"], INJ_COLS)
