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


def test_intermediate_dates_with_mixed_formats_load(tmp_path):
    import pandas as pd
    from nhlmodel.data.nhl_pipeline import load_intermediate, save_intermediate
    g = pd.DataFrame(dict(game_id=[1, 2], date=["2026-09-30", "2026-10-01 00:00:00"]))
    g.to_csv(tmp_path / "games.csv.gz", index=False, compression="gzip")
    inter = load_intermediate(str(tmp_path))
    assert inter["games"].date.tolist() == ["2026-09-30", "2026-10-01"]
    pd.to_datetime(inter["games"].date)      # strict parse no longer fails
    save_intermediate({"games": g}, str(tmp_path))
    assert pd.read_csv(tmp_path / "games.csv.gz").date.tolist() == ["2026-09-30", "2026-10-01"]


def test_lean_odds_mode_is_one_book_call(monkeypatch):
    import pandas as pd
    import requests
    from nhlmodel.data import odds_api
    calls = []

    class R:
        status_code = 200
        headers = {"x-requests-remaining": "497"}
        def raise_for_status(self): pass
        def json(self):
            return [dict(id="e1", home_team="Toronto Maple Leafs", away_team="New York Islanders",
                         commence_time="2026-10-01T23:00:00Z",
                         bookmakers=[dict(key="williamhill_us", markets=[dict(key="h2h", outcomes=[
                             dict(name="Toronto Maple Leafs", price=-130), dict(name="New York Islanders", price=110)])])])]

    monkeypatch.setattr(requests, "get", lambda url, params=None, timeout=None: calls.append((url, params)) or R())
    sched = pd.DataFrame(dict(game_id=[1], home=["TOR"], away=["NYI"], date=[pd.Timestamp("2026-10-01")]))
    out = odds_api.fetch(sched, pd.DataFrame(columns=["player_id", "name"]), "bet", api_key="k",
                         bookmakers="williamhill_us", game_only=True)
    assert len(calls) == 1                                   # no per-event calls
    assert calls[0][1]["bookmakers"] == "williamhill_us" and "regions" not in calls[0][1]
    assert calls[0][1]["markets"] == "h2h,spreads,totals"    # 3 credits
    assert set(out.selection) == {"home", "away"} and set(out.book) == {"williamhill_us"}


def test_book_match_finds_caesars_by_name_whatever_its_key(monkeypatch):
    import pandas as pd
    import requests
    from nhlmodel.data import odds_api

    class R:
        status_code = 200
        headers = {"x-requests-remaining": "480"}
        def raise_for_status(self): pass
        def json(self):
            h2h = lambda a, b: [dict(key="h2h", outcomes=[dict(name="Toronto Maple Leafs", price=a),
                                                           dict(name="New York Islanders", price=b)])]
            return [dict(id="e1", home_team="Toronto Maple Leafs", away_team="New York Islanders",
                         commence_time="2026-10-02T23:00:00Z",
                         bookmakers=[dict(key="draftkings", title="DraftKings", markets=h2h(-130, 110)),
                                     dict(key="caesars", title="Caesars", markets=h2h(-125, 105))])]

    calls = []
    monkeypatch.setattr(requests, "get", lambda url, params=None, timeout=None: calls.append(params) or R())
    sched = pd.DataFrame(dict(game_id=[1], home=["TOR"], away=["NYI"], date=[pd.Timestamp("2026-10-02")]))
    out = odds_api.fetch(sched, pd.DataFrame(columns=["player_id", "name"]), "bet", api_key="k", regions="us",
                         game_only=True, book_match=("williamhill_us", "Caesars"))
    assert len(calls) == 1 and calls[0]["regions"] == "us"
    assert set(out.book) == {"williamhill_us"} and sorted(out.price) == [-125, 105]   # Caesars only
