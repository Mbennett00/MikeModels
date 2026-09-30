"""Canonical tables every adapter must produce (CSV files under a data dir).

Rates are always computed from these tables filtered to ``date < game date``
(see ``nhlmodel.ratings``), which is the single leakage guard.

games            one row per game (outcomes only; never used as a feature for that game)
team_games       one row per team per game (features)
goalie_games     one row per goalie per game (features)
player_games     one row per skater per game (features + settlement outcomes)
lineups          one row per dressed player for a slate, from Daily Faceoff (confirmed flag)
odds             one row per book price
"""
from __future__ import annotations

import pandas as pd

GAMES = [
    "game_id", "date", "season", "home", "away",
    "home_reg_nonen", "away_reg_nonen",     # regulation goals excluding empty-net goals
    "home_en_reg", "away_en_reg",           # empty-net goals scored in regulation
    "home_final", "away_final",             # official final score (OT/SO winner +1)
    "decision",                             # REG | OT | SO
    "home_p1", "away_p1",                   # first-period goals
]

TEAM_GAMES = [
    "game_id", "date", "season", "team", "opp", "is_home",
    "toi_5v5", "xgf_5v5", "xga_5v5",
    "xgf_5v5_adj", "xga_5v5_adj",           # score- and venue-adjusted
    "cf_5v5", "ca_5v5",                     # shot attempts (Corsi) for/against
    "toi_pp", "xgf_pp", "toi_pk", "xga_pk",
    "pen_taken", "pen_drawn",               # minor-penalty counts
    "toi_all", "sog_for", "sog_against",
    "goals_nonen",
]

GOALIE_GAMES = ["game_id", "date", "season", "goalie_id", "name", "team", "toi", "xga", "ga"]

PLAYER_GAMES = [
    "game_id", "date", "season", "player_id", "name", "team", "opp", "is_home", "pos",
    "line", "pp_unit",
    "toi_5v5", "toi_pp",
    "ixg_5v5", "ixg_pp", "g_5v5", "g_pp",
    "sog_5v5", "sog_pp",
    "a1_5v5", "a2_5v5", "a1_pp", "a2_pp",
    "ixg_nonen", "g_nonen",                 # all situations, empty-net shots removed (finishing)
    # settlement outcomes (all situations, including EN and OT; how books grade)
    "goals", "assists", "sog", "points", "en_goals",
]

LINEUPS = ["date", "game_id", "team", "player_id", "name", "pos", "line", "pp_unit", "confirmed"]

ODDS = ["date", "game_id", "market", "player_id", "selection", "line", "price", "book", "snapshot"]
# market: moneyline | puckline | total | team_total | p1_total | p1_3way | goals | sog | assists | points
# selection: home/away/draw (sides), over/under, yes (player anytime markets: goals/points 0.5)
# snapshot: open | close | bet  (bet = price at the time you would bet; close for CLV)

TABLES = {
    "games": GAMES, "team_games": TEAM_GAMES, "goalie_games": GOALIE_GAMES,
    "player_games": PLAYER_GAMES, "lineups": LINEUPS, "odds": ODDS,
}


def validate(name: str, df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in TABLES[name] if c not in df.columns]
    if missing:
        raise ValueError(f"{name}: missing columns {missing}")
    df = df.copy()
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    return df


def load_dir(path: str) -> dict[str, pd.DataFrame]:
    import os
    out = {}
    for name in TABLES:
        f = os.path.join(path, f"{name}.csv")
        if os.path.exists(f):
            out[name] = validate(name, pd.read_csv(f))
    return out


def save_dir(tables: dict[str, pd.DataFrame], path: str) -> None:
    import os
    os.makedirs(path, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(os.path.join(path, f"{name}.csv"), index=False)
