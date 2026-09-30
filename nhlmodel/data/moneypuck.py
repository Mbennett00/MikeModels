"""MoneyPuck game-by-game adapter -> team_games, player_games, goalie_games.

Expected raw files (download manually; this container cannot reach moneypuck.com):
  <raw>/teams/*.csv    team game-by-game   (e.g. careers/gameByGame/all_teams.csv)
  <raw>/skaters/*.csv  skater game-by-game (one file per player, or concatenated)
  <raw>/goalies/*.csv  goalie game-by-game

Column names below are MoneyPuck's as I understand them. They could not be checked
against live files from here: if a load fails, the error lists the missing columns
and you only need to edit the maps below.

Historical lines / PP units are not in MoneyPuck. They are inferred from TOI rank
within each team-game (F: 1-3 -> F1, 4-6 -> F2, ...; D: 1-2 -> D1; PP units from
5on4 TOI rank). This is a proxy: real Daily Faceoff lines are only used for live slates.
"""
from __future__ import annotations

import glob
import os

import numpy as np
import pandas as pd

KEYS = dict(game="gameId", team="playerTeam", opp="opposingTeam", venue="home_or_away", date="gameDate",
            season="season", situation="situation")
TEAM_COLS = dict(toi="iceTime", xgf="xGoalsFor", xga="xGoalsAgainst",
                 xgf_adj="scoreVenueAdjustedxGoalsFor", xga_adj="scoreVenueAdjustedxGoalsAgainst",
                 cf="shotAttemptsFor", ca="shotAttemptsAgainst", sogf="shotsOnGoalFor", soga="shotsOnGoalAgainst",
                 # ASSUMPTION: penaltiesFor = penalties drawn by the team, penaltiesAgainst = taken. Verify.
                 pen_drawn="penaltiesFor", pen_taken="penaltiesAgainst")
SKATER_COLS = dict(pid="playerId", name="name", pos="position", toi="icetime", ixg="I_F_xGoals",
                   g="I_F_goals", sog="I_F_shotsOnGoal", a1="I_F_primaryAssists", a2="I_F_secondaryAssists")
GOALIE_COLS = dict(pid="playerId", name="name", toi="icetime", xga="xGoals", ga="goals")
S5, SPP, SPK, SALL = "5on5", "5on4", "4on5", "all"


def _read(pattern: str) -> pd.DataFrame:
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(pattern)
    return pd.concat((pd.read_csv(f) for f in files), ignore_index=True)


def _need(df, cols, what):
    miss = [c for c in cols if c not in df.columns]
    if miss:
        raise ValueError(f"MoneyPuck {what}: missing columns {miss}; edit the column maps in {__file__}")


def _date(s):
    return pd.to_datetime(s.astype(str), format="%Y%m%d", errors="coerce").fillna(pd.to_datetime(s, errors="coerce"))


def team_games(raw: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    _need(raw, list(KEYS.values()) + list(TEAM_COLS.values()), "teams")
    K, C = KEYS, TEAM_COLS
    piv = {}
    for s in (S5, SPP, SPK, SALL):
        piv[s] = raw[raw[K["situation"]] == s].set_index([K["game"], K["team"]])
    b = piv[SALL]
    out = pd.DataFrame(index=b.index)
    out["date"] = _date(b[K["date"]]); out["season"] = b[K["season"]].astype(int)
    out["opp"] = b[K["opp"]]; out["is_home"] = (b[K["venue"]].str.upper() == "HOME").astype(int)
    f5, fpp, fpk = piv[S5].reindex(out.index), piv[SPP].reindex(out.index), piv[SPK].reindex(out.index)
    out["toi_5v5"] = f5[C["toi"]] / 60; out["xgf_5v5"] = f5[C["xgf"]]; out["xga_5v5"] = f5[C["xga"]]
    out["xgf_5v5_adj"] = f5[C["xgf_adj"]]; out["xga_5v5_adj"] = f5[C["xga_adj"]]
    out["cf_5v5"] = f5[C["cf"]]; out["ca_5v5"] = f5[C["ca"]]
    out["toi_pp"] = fpp[C["toi"]] / 60; out["xgf_pp"] = fpp[C["xgf"]]
    out["toi_pk"] = fpk[C["toi"]] / 60; out["xga_pk"] = fpk[C["xga"]]
    out["pen_taken"] = b[C["pen_taken"]]; out["pen_drawn"] = b[C["pen_drawn"]]
    out["toi_all"] = b[C["toi"]] / 60; out["sog_for"] = b[C["sogf"]]; out["sog_against"] = b[C["soga"]]
    out = out.reset_index().rename(columns={K["game"]: "game_id", K["team"]: "team"})
    # regulation non-EN goals come from the NHL API games table
    g = games[["game_id", "home", "away", "home_reg_nonen", "away_reg_nonen"]]
    h = g.rename(columns={"home": "team", "home_reg_nonen": "goals_nonen"})[["game_id", "team", "goals_nonen"]]
    a = g.rename(columns={"away": "team", "away_reg_nonen": "goals_nonen"})[["game_id", "team", "goals_nonen"]]
    out = out.merge(pd.concat([h, a]), on=["game_id", "team"], how="inner")
    return out.fillna({"toi_pp": 0, "xgf_pp": 0, "toi_pk": 0, "xga_pk": 0})


def player_games(raw: pd.DataFrame, goal_events: pd.DataFrame | None) -> pd.DataFrame:
    _need(raw, list(KEYS.values()) + list(SKATER_COLS.values()), "skaters")
    K, C = KEYS, SKATER_COLS
    idx = [K["game"], C["pid"]]
    piv = {s: raw[raw[K["situation"]] == s].set_index(idx) for s in (S5, SPP, SPK, SALL)}
    b = piv[SALL]
    f5, fpp, fpk = (piv[s].reindex(b.index) for s in (S5, SPP, SPK))
    out = pd.DataFrame(index=b.index)
    out["date"] = _date(b[K["date"]]); out["season"] = b[K["season"]].astype(int)
    out["name"] = b[C["name"]]; out["team"] = b[K["team"]]; out["opp"] = b[K["opp"]]
    out["is_home"] = (b[K["venue"]].str.upper() == "HOME").astype(int)
    out["pos"] = np.where(b[C["pos"]].astype(str).str.upper().str.startswith("D"), "D", "F")
    z = lambda s: s.fillna(0)
    out["toi_5v5"] = z(f5[C["toi"]]) / 60; out["toi_pp"] = z(fpp[C["toi"]]) / 60
    out["ixg_5v5"] = z(f5[C["ixg"]]); out["ixg_pp"] = z(fpp[C["ixg"]])
    out["g_5v5"] = z(f5[C["g"]]); out["g_pp"] = z(fpp[C["g"]])
    out["sog_5v5"] = z(f5[C["sog"]]); out["sog_pp"] = z(fpp[C["sog"]])
    out["a1_5v5"] = z(f5[C["a1"]]); out["a2_5v5"] = z(f5[C["a2"]])
    out["a1_pp"] = z(fpp[C["a1"]]); out["a2_pp"] = z(fpp[C["a2"]])
    # ASSUMPTION: 5on5 + 5on4 + 4on5 approximates "non-empty-net" (drops 4v4/3v3/6v5 as well)
    out["ixg_nonen"] = out.ixg_5v5 + out.ixg_pp + z(fpk[C["ixg"]])
    out["g_nonen"] = out.g_5v5 + out.g_pp + z(fpk[C["g"]])
    out["goals"] = b[C["g"]]; out["assists"] = b[C["a1"]] + b[C["a2"]]
    out["sog"] = b[C["sog"]]; out["points"] = out.goals + out.assists
    out = out.reset_index().rename(columns={K["game"]: "game_id", C["pid"]: "player_id"})
    out["en_goals"] = 0
    if goal_events is not None and len(goal_events):
        en = goal_events[goal_events.empty_net].groupby(["game_id", "scorer"]).size().rename("en")
        out = out.merge(en.reset_index().rename(columns={"scorer": "player_id"}), on=["game_id", "player_id"], how="left")
        out["en_goals"] = out.en.fillna(0).astype(int); out = out.drop(columns="en")
    return infer_lines(out)


def infer_lines(pg: pd.DataFrame) -> pd.DataFrame:
    """Proxy lines from TOI rank within each team-game (see module docstring)."""
    pg = pg.copy()
    r5 = pg.groupby(["game_id", "team", "pos"]).toi_5v5.rank(ascending=False, method="first").astype(int)
    pg["line"] = np.where(pg.pos == "F", "F" + ((r5 - 1) // 3 + 1).clip(upper=4).astype(str),
                          "D" + ((r5 - 1) // 2 + 1).clip(upper=3).astype(str))
    rpp = pg.groupby(["game_id", "team"]).toi_pp.rank(ascending=False, method="first").astype(int)
    pg["pp_unit"] = np.where(pg.toi_pp < 0.5, 0, np.where(rpp <= 5, 1, np.where(rpp <= 10, 2, 0)))
    return pg


def goalie_games(raw: pd.DataFrame) -> pd.DataFrame:
    _need(raw, [KEYS["game"], KEYS["team"], KEYS["date"], KEYS["season"], KEYS["situation"]]
          + list(GOALIE_COLS.values()), "goalies")
    K, C = KEYS, GOALIE_COLS
    b = raw[raw[K["situation"]] == SALL]
    return pd.DataFrame(dict(game_id=b[K["game"]], date=_date(b[K["date"]]), season=b[K["season"]].astype(int),
                             goalie_id=b[C["pid"]], name=b[C["name"]], team=b[K["team"]],
                             toi=b[C["toi"]] / 60, xga=b[C["xga"]], ga=b[C["ga"]]))


def build(raw_dir: str, nhl: dict) -> dict:
    games = nhl["games"]
    tg = team_games(_read(os.path.join(raw_dir, "teams", "*.csv")), games)
    pg = player_games(_read(os.path.join(raw_dir, "skaters", "*.csv")), nhl.get("goal_events"))
    gg = goalie_games(_read(os.path.join(raw_dir, "goalies", "*.csv")))
    keep = set(games.game_id)
    tg, pg, gg = (d[d.game_id.isin(keep)] for d in (tg, pg, gg))
    # historical "lineups" = who actually dressed, with inferred lines (confirmed by construction)
    lu = pg[["date", "game_id", "team", "player_id", "name", "pos", "line", "pp_unit"]].assign(confirmed=True)
    sg = nhl.get("starting_goalies")
    if sg is not None and len(sg):
        lu = pd.concat([lu, sg[["date", "game_id", "team", "player_id", "name", "pos", "line", "pp_unit",
                                "confirmed"]]], ignore_index=True)
    return dict(games=games, team_games=tg, goalie_games=gg, player_games=pg, lineups=lu)
