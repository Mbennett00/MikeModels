"""Decay-weighted, leakage-free rate snapshots.

``build_snapshot(tables, date, half_life)`` uses only rows with ``date < game date``
from the current and previous season(s). Each entity's games are weighted by
0.5 ** (games_ago / half_life), counting that entity's own games.

The snapshot stores *weighted sums* (sufficient statistics) so the shrinkage
constants k, m can be varied in tuning without recomputing it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

TEAM_SUMS = ["toi_5v5", "xgf_5v5_adj", "xga_5v5_adj", "cf_5v5", "ca_5v5", "toi_pp", "xgf_pp",
             "toi_pk", "xga_pk", "pen_taken", "pen_drawn", "toi_all", "sog_for", "sog_against",
             "goals_nonen"]
PLAYER_SUMS = ["toi_5v5", "toi_pp", "ixg_5v5", "ixg_pp", "sog_5v5", "sog_pp", "a1_5v5", "a2_5v5",
               "a1_pp", "a2_pp", "ixg_nonen", "g_nonen", "goals", "assists", "sog", "en_goals"]


def role_5v5(pos: str, line: str) -> str:
    line = str(line)
    if pos == "D":
        return "D_top" if line in ("D1", "D2") else "D_bot"
    return "F_top" if line in ("F1", "F2") else "F_bot"


def role_pp(pos: str, unit) -> str:
    try:
        u = int(unit)
    except (TypeError, ValueError):
        u = 0
    return f"{pos}_PP{u}" if u in (1, 2) else f"{pos}_PP0"


def decay_weights(df: pd.DataFrame, key: str, half_life: float) -> np.ndarray:
    ago = df.sort_values("date").groupby(key).cumcount(ascending=False)
    return (0.5 ** (ago.reindex(df.index) / half_life)).to_numpy()


def in_window(df: pd.DataFrame, date, season: int, seasons_back: int) -> pd.DataFrame:
    d = pd.Timestamp(date)
    return df[(df["date"] < d) & (df["season"] > season - seasons_back)]


@dataclass
class Snapshot:
    date: pd.Timestamp
    season: int
    half_life: float
    team: pd.DataFrame            # weighted sums per team (+ w = sum of weights)
    goalie: pd.DataFrame          # weighted xga, ga per goalie
    goalie_team_avg: pd.DataFrame  # fallback: team's weighted goalie ratio
    player: pd.DataFrame          # weighted sums per player
    player_recent: pd.DataFrame   # last N games per player (unweighted), for TOI + linemates
    lines_hist: pd.DataFrame      # (game_id, team, line, player_id) for games in player_recent
    role5: pd.DataFrame           # league rates per 5v5 role
    rolepp: pd.DataFrame          # league rates per PP role
    league: dict = field(default_factory=dict)
    last_game: dict = field(default_factory=dict)   # team -> (date, opp_home_team) of last game
    n_team_games: int = 0
    _recent_idx: dict = field(default=None, repr=False)
    _lines_idx: dict = field(default=None, repr=False)
    _game_lines: dict = field(default=None, repr=False)

    def recent(self, pid) -> pd.DataFrame:
        if self._recent_idx is None:
            self._recent_idx = {k: v for k, v in self.player_recent.groupby("player_id")}
        return self._recent_idx.get(pid, self.player_recent.iloc[:0])

    def lines_of(self, pid) -> list:
        """[(game_id, team, line)] for the player's recent games."""
        if self._lines_idx is None:
            lh = self.lines_hist
            self._lines_idx = {k: list(zip(v.game_id, v.team, v.line)) for k, v in lh.groupby("player_id")}
            self._game_lines = {k: list(v) for k, v in lh.groupby(["game_id", "team", "line"]).player_id}
        return self._lines_idx.get(pid, [])

    def mates_in(self, game_id, team, line) -> list:
        return self._game_lines.get((game_id, team, line), [])


def build_snapshot(tables: dict, date, season: int, half_life: float, seasons_back: int = 2,
                   toi_window: int = 10, prior_season_weight: float = 1.0) -> Snapshot:
    date = pd.Timestamp(date)
    tg = in_window(tables["team_games"], date, season, seasons_back).copy()
    gg = in_window(tables["goalie_games"], date, season, seasons_back).copy()
    pg = in_window(tables["player_games"], date, season, seasons_back).copy()

    # ---- teams
    tg["w"] = decay_weights(tg, "team", half_life)
    # rosters change between seasons: earlier seasons count less, so early-season team ratings
    # regress harder toward the league average (tuned on the backtest)
    tg.loc[tg.season < season, "w"] *= prior_season_weight
    ws = tg[TEAM_SUMS].multiply(tg["w"], axis=0)
    ws["team"] = tg["team"]; ws["w"] = tg["w"]; ws["n"] = 1
    team = ws.groupby("team").sum(numeric_only=True)

    # league averages use unweighted totals over the window (population rates)
    L = {}
    tot = tg[TEAM_SUMS].sum()
    L["xg60_5v5"] = tot.xgf_5v5_adj / tot.toi_5v5 * 60
    L["cf60_5v5"] = tot.cf_5v5 / tot.toi_5v5 * 60
    L["xg60_pp"] = tot.xgf_pp / max(tot.toi_pp, 1e-9) * 60
    L["pp_toi_pg"] = tot.toi_pp / max(len(tg), 1)
    L["pen_pg"] = tot.pen_taken / max(len(tg), 1)
    L["sog_pg"] = tot.sog_for / max(len(tg), 1)
    L["goals_pg"] = tot.goals_nonen / max(len(tg), 1)
    L["pp_xg_share"] = tot.xgf_pp / max(tot.xgf_pp + tot.xgf_5v5_adj, 1e-9)
    L["toi_all_pg"] = tot.toi_all / max(len(tg), 1)
    home = tg[tg.is_home == 1].goals_nonen.sum(); away = tg[tg.is_home == 0].goals_nonen.sum()
    L["home_ratio"] = float(np.sqrt(home / away)) if away > 0 else 1.0

    # ---- goalies
    gg["w"] = decay_weights(gg, "goalie_id", half_life)
    gg["wxga"] = gg.xga * gg.w; gg["wga"] = gg.ga * gg.w
    goalie = gg.groupby("goalie_id").agg(xga=("wxga", "sum"), ga=("wga", "sum"), w=("w", "sum"),
                                         team=("team", "last"), name=("name", "last"))
    gta = gg.groupby("team").agg(xga=("wxga", "sum"), ga=("wga", "sum"))
    L["ga_per_xga"] = float(gg.ga.sum() / max(gg.xga.sum(), 1e-9))

    # ---- players
    pg["w"] = decay_weights(pg, "player_id", half_life)
    wp = pg[PLAYER_SUMS].multiply(pg["w"], axis=0)
    wp["player_id"] = pg.player_id; wp["w"] = pg.w
    player = wp.groupby("player_id").sum(numeric_only=True)
    last = pg.sort_values("date").groupby("player_id").tail(1).set_index("player_id")
    player = player.join(last[["name", "team", "pos", "line", "pp_unit", "season"]].rename(columns={"season": "last_season"}))
    ptot = pg[PLAYER_SUMS].sum()
    L["g_per_xg"] = float(ptot.g_nonen / max(ptot.ixg_nonen, 1e-9))
    L["en_share"] = float(ptot.en_goals / max(ptot.goals, 1e-9))
    L["assists_per_goal"] = float(ptot.assists / max(ptot.goals, 1e-9))
    # share of team non-EN goals credited to skaters in player data (own goals etc. fall outside)
    L["skater_goal_share"] = float(min(1.0, ptot.g_nonen / max(tot.goals_nonen, 1e-9)))

    pg["role5"] = [role_5v5(p, l) for p, l in zip(pg.pos, pg.line)]
    pg["rolepp"] = [role_pp(p, u) for p, u in zip(pg.pos, pg.pp_unit)]
    r5 = pg.groupby("role5")[["toi_5v5", "ixg_5v5", "sog_5v5", "a1_5v5", "a2_5v5"]].sum()
    role5 = pd.DataFrame({"ixg60": r5.ixg_5v5 / r5.toi_5v5 * 60, "sog60": r5.sog_5v5 / r5.toi_5v5 * 60,
                          "a60": (r5.a1_5v5 + r5.a2_5v5) / r5.toi_5v5 * 60})
    role5["toi_pg"] = pg.groupby("role5").toi_5v5.mean()
    rp = pg.groupby("rolepp")[["toi_pp", "ixg_pp", "sog_pp", "a1_pp", "a2_pp"]].sum()
    den = rp.toi_pp.where(rp.toi_pp > 0)
    rolepp = pd.DataFrame({"ixg60": rp.ixg_pp / den * 60, "sog60": rp.sog_pp / den * 60,
                           "a60": (rp.a1_pp + rp.a2_pp) / den * 60}).fillna(0.0)
    # PP-time share by unit (player toi_pp / team toi_pp in that game)
    team_pp = tables["team_games"].set_index(["game_id", "team"]).toi_pp
    pg["pp_share"] = (pg.toi_pp / team_pp.reindex(list(zip(pg.game_id, pg.team))).to_numpy()).fillna(0).clip(0, 1)
    rolepp["pp_share"] = pg.groupby("rolepp").pp_share.mean()

    recent = pg.sort_values("date").groupby("player_id").tail(toi_window)
    recent = recent[["player_id", "game_id", "date", "team", "pos", "line", "pp_unit", "toi_5v5", "toi_pp",
                     "pp_share"]]

    lines_hist = pg[pg.game_id.isin(recent.game_id.unique())][["game_id", "team", "line", "player_id"]]

    last_game = {}
    lg = tables["team_games"]
    lg = lg[lg.date < date].sort_values("date").groupby("team").tail(1)
    for r in lg.itertuples():
        venue = r.team if r.is_home == 1 else r.opp
        last_game[r.team] = (r.date, venue)

    return Snapshot(date=date, season=season, half_life=half_life, team=team, goalie=goalie,
                    goalie_team_avg=gta, player=player, player_recent=recent, lines_hist=lines_hist, role5=role5,
                    rolepp=rolepp, league=L, last_game=last_game, n_team_games=len(tg))
