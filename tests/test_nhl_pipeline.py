import numpy as np
import pandas as pd
import pytest

from nhlmodel.data import nhl_pipeline as nhl
from nhlmodel.data.schema import TABLES, validate

from .fake_nhl import game


@pytest.fixture(scope="module")
def built():
    rng = np.random.default_rng(1)
    parts = {k: [] for k in nhl.INTERMEDIATE}
    gid = 2024020000
    for d in pd.date_range("2024-10-10", periods=30):
        for home, away in ((1, 2), (3, 4)) if d.day % 2 else ((2, 3), (4, 1)):
            gid += 1
            for k, v in nhl.parse_game(*game(gid, d, home, away, rng)).items():
                parts[k].append(v)
    inter = {k: pd.concat(v, ignore_index=True) for k, v in parts.items()}
    return inter, nhl.build_tables(inter)[0]


def test_toi_from_shifts(built):
    inter, _ = built
    tt = inter["team_toi"]
    assert np.allclose(tt.toi_all, 60, atol=0.1)
    # fake away penalty: shifts starting at 30:30 and 31:15 are short-handed -> 90 s of PP per game
    per_game = tt.groupby("game_id")
    assert per_game.toi_pp.sum().eq(1.5).all() and per_game.toi_pk.sum().eq(1.5).all()
    assert per_game.toi_5v5.min().eq(58.5).all()
    g = inter["goalie_toi"]
    assert g.groupby("game_id").starter.sum().eq(2).all()


def test_tables_match_schema(built):
    _, tables = built
    for name in ("games", "team_games", "goalie_games", "player_games", "lineups"):
        validate(name, tables[name])
    pg = tables["player_games"]
    assert set(pg.pos) == {"F", "D"}
    assert (pg.toi_5v5 > 0).all()
    # settlement goals equal the games table (no EN, no OT in the fake data; SO excluded)
    g = tables["games"]
    per_game = pg.groupby("game_id").goals.sum()
    reg = (g.set_index("game_id").home_reg_nonen + g.set_index("game_id").away_reg_nonen)
    assert (per_game.reindex(reg.index).fillna(0) == reg).all()
    tg = tables["team_games"]
    assert (tg.xgf_5v5 > 0).all() and tg.pen_taken.sum() == len(g)
    assert (tables["lineups"].pos == "G").sum() == 2 * len(g)


def test_walk_forward_runs_on_api_tables(built):
    from nhlmodel.backtest import walk_forward
    from nhlmodel.config import DEFAULT
    _, tables = built
    bt = walk_forward(tables, DEFAULT.with_(seasons_back=2), "2024-10-30", "2024-11-08")
    assert len(bt["player_markets"]) > 0


def test_odds_api_parse():
    from nhlmodel.data.odds_api import parse_event
    sched = pd.DataFrame(dict(game_id=[7], home=["BOS"], away=["TOR"]))
    ev = {"home_team": "Boston Bruins", "away_team": "Toronto Maple Leafs", "commence_time": "2026-10-08T23:00:00Z",
          "bookmakers": [{"key": "dk", "markets": [
              {"key": "h2h", "outcomes": [{"name": "Boston Bruins", "price": -130}, {"name": "Toronto Maple Leafs", "price": 110}]},
              {"key": "spreads", "outcomes": [{"name": "Boston Bruins", "price": 170, "point": -1.5},
                                              {"name": "Toronto Maple Leafs", "price": -200, "point": 1.5}]},
              {"key": "totals", "outcomes": [{"name": "Over", "price": -110, "point": 6.5}, {"name": "Under", "price": -110, "point": 6.5}]},
              {"key": "team_totals", "outcomes": [{"name": "Over", "description": "Boston Bruins", "price": 100, "point": 3.5}]},
              {"key": "player_shots_on_goal", "outcomes": [{"name": "Over", "description": "Dávid Pastrňák", "price": -140, "point": 3.5},
                                                           {"name": "Under", "description": "Unknown Guy", "price": 110, "point": 3.5}]},
              {"key": "player_goal_scorer_anytime", "outcomes": [{"name": "Yes", "description": "David Pastrnak", "price": 150}]},
          ]}]}
    from nhlmodel.data.odds_api import player_index
    idx = player_index(pd.DataFrame(dict(name=["David Pastrnak", "Chris Tanev"], player_id=[8477956, 8475690])))
    ev["bookmakers"][0]["markets"].append({"key": "player_points", "outcomes": [
        {"name": "Over", "description": "Christopher Tanev", "price": 300, "point": 0.5}]})
    rows, missing = parse_event(ev, sched, idx, "bet", "now")
    df = pd.DataFrame(rows)
    assert set(df.market) == {"moneyline", "puckline", "total", "team_total", "sog", "goals", "points"}
    assert df[df.market == "points"].player_id.iloc[0] == 8475690
    from nhlmodel.data.odds_api import lookup
    assert lookup(player_index(pd.DataFrame(dict(name=["Egor Chinakhov"], player_id=[1]))), "Yegor Chinakhov") == 1
    assert df[df.market == "team_total"].selection.iloc[0] == "home_over"
    assert df[df.market == "goals"].line.iloc[0] == 0.5
    assert missing == {"Unknown Guy"}
    assert df[df.market == "puckline"].set_index("selection").line.to_dict() == {"home": -1.5, "away": 1.5}


def test_moneypuck_xg_attaches_by_game_shooter_and_time():
    import pandas as pd
    from nhlmodel.data.moneypuck_shots import attach
    ours = pd.DataFrame(dict(game_id=[2025020001, 2025020001, 2025020001, 2025020002],
                             shooter=[11, 11, 22, 11], t=[76, 300, 95, 76],
                             unblocked=[True, True, False, True]))
    mp = pd.DataFrame(dict(season=[2025, 2025, 2025], game_id=[20001, 20001, 20001], period=[1, 1, 1],
                           time=[77, 95, 600], shooterPlayerId=[11, 22, 11], xGoal=["0.05", "0.2", "0.3"],
                           event=["SHOT"] * 3, isPlayoffGame=[0] * 3))
    x = attach(ours, mp)
    assert x.iloc[0] == 0.05                  # same game + shooter, 1 s apart
    assert pd.isna(x.iloc[1])                 # no MoneyPuck shot near t=300
    assert pd.isna(x.iloc[2])                 # blocked shots are not matched
    assert pd.isna(x.iloc[3])                 # different game
