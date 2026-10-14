"""NBA model: ESPN parsing, the team-rating fit, game projections and player projections (synthetic data)."""
import datetime as dt

import numpy as np
import pandas as pd

from nbamodel import data, model
from nbamodel.daily import build, next_slate

TEAMS = [f"T{i:02d}" for i in range(30)]


def synth_season(seed=0, n_days=150, start=dt.date(2025, 10, 21)):
    rng = np.random.default_rng(seed)
    off = dict(zip(TEAMS, rng.normal(0, 4, 30)))
    dfn = dict(zip(TEAMS, rng.normal(0, 4, 30)))
    rows, gid = [], 0
    for k in range(n_days):
        d = start + dt.timedelta(days=k)
        order = rng.permutation(TEAMS)
        for i in range(0, 14, 2):
            h, a = order[i], order[i + 1]
            hs = 113 + 2.5 + off[h] - dfn[a] + rng.normal(0, 10)
            as_ = 113 + off[a] - dfn[h] + rng.normal(0, 10)
            gid += 1
            rows.append(dict(game_id=str(gid), start_utc=pd.Timestamp(d).tz_localize("America/New_York").tz_convert("UTC").isoformat(),
                             date=str(d), season_type=2, season=2026, state="post", detail="Final", neutral=False,
                             home=h, away=a, home_score=round(hs), away_score=round(as_),
                             home_name=h, away_name=a, home_city="", away_city="", home_color="#123456", away_color="#654321",
                             home_logo="x/500/h.png", away_logo="x/500/a.png", home_tid="1", away_tid="2"))
    return pd.DataFrame(rows), off, dfn


def test_fit_recovers_team_strength_and_home_court():
    g, off, dfn = synth_season()
    R = model.fit_ratings(model.add_rest(g), pd.Timestamp("2026-04-01"))
    true_net = pd.Series({t: off[t] + dfn[t] for t in TEAMS})
    fit_net = pd.Series({t: R["off"][t] + R["dfn"][t] for t in TEAMS})
    assert np.corrcoef(true_net, fit_net)[0, 1] > 0.85
    assert 1.0 < R["hca"] < 4.0
    assert 11 <= R["sd_margin"] < 17


def test_projection_is_consistent():
    g, _, _ = synth_season()
    R = model.fit_ratings(model.add_rest(g), pd.Timestamp("2026-04-01"))
    p = model.project_game(R, "T00", "T01")
    q = model.project_game(R, "T01", "T00")
    assert abs(p["total"] - (p["pts_home"] + p["pts_away"])) < 0.2
    assert 0 < p["p_home"] < 1 and p["margin"] > q["margin"] - 2 * R["hca"] - 0.5   # home court helps the home side
    assert abs(model.project_game(R, "T00", "T01", neutral=True)["margin"] + model.project_game(R, "T01", "T00", neutral=True)["margin"]) < 1e-6


def test_summer_break_does_not_age_last_season():
    d = pd.Series(["2026-04-12", "2026-10-21"])
    s = pd.Series([2026, 2027])
    age = model.game_days_age(d, s, pd.Timestamp("2026-10-25"))
    assert age[0] < 15 and age[1] == 4


def test_back_to_back_flags():
    g = pd.DataFrame(dict(game_id=["1", "2", "3"], date=["2026-01-01", "2026-01-02", "2026-01-04"], home=["A", "B", "A"], away=["C", "A", "B"]))
    r = model.add_rest(g)
    assert list(r.b2b_away) == [False, True, False] and list(r.b2b_home) == [False, False, False]


def test_player_projections_balance_minutes_and_points():
    g, _, _ = synth_season(n_days=40)
    rng = np.random.default_rng(1)
    rows = []
    for gid, h, a in g[["game_id", "home", "away"]].itertuples(index=False):
        for t in (h, a):
            mins = [36, 34, 32, 30, 28, 24, 20, 18, 12, 6]
            for j, m in enumerate(mins):
                rows.append(dict(game_id=gid, team=t, player_id=f"{t}p{j}", name=f"{t} P{j}", pos="G", starter=j < 5, min=m,
                                 pts=m * 0.48 + rng.normal(0, 3), reb=m * 0.18, ast=m * 0.12, fg3=m * 0.05))
    box = pd.DataFrame(rows)
    slate = [dict(game_id="x", home="T00", away="T01", pts_home=118.0, pts_away=110.0)]
    inj = pd.DataFrame([dict(player_id="T00p0", name="T00 P0", team="T00", status="Out", detail="knee")])
    P = model.player_projections(box, g, None, inj, slate)
    home = [p for p in P if p["team"] == "T00"]
    assert "T00p0" not in {p["id"] for p in home}                      # out = not projected
    assert abs(sum(p["min"] for p in home) - 240) < 6                  # minutes re-balanced to a full game
    assert abs(sum(p["pts"] for p in home) - 118.0) < 8                # points track the team's projection
    assert all(p["sd"]["pts"] > 2 for p in home)


def test_espn_parsers():
    sb = {"events": [{"id": "401", "date": "2026-10-22T23:30Z", "season": {"year": 2027, "type": 2},
                      "status": {"type": {"state": "pre", "shortDetail": "7:30 PM"}},
                      "competitions": [{"neutralSite": False, "competitors": [
                          {"homeAway": "home", "score": "0", "team": {"abbreviation": "BOS", "shortDisplayName": "Celtics", "location": "Boston", "color": "007a33", "logo": "l/500/bos.png", "id": "2"}},
                          {"homeAway": "away", "score": "0", "team": {"abbreviation": "NY", "shortDisplayName": "Knicks", "location": "New York", "color": "1d428a", "logo": "l/500/ny.png", "id": "18"}}]}]}]}
    r = data.parse_scoreboard(sb)[0]
    assert (r["home"], r["away"], r["season_type"], r["date"], r["home_color"]) == ("BOS", "NY", 2, "2026-10-22", "#007a33")
    js = {"boxscore": {"players": [{"team": {"abbreviation": "BOS"}, "statistics": [{"labels": ["MIN", "FG", "3PT", "FT", "OREB", "DREB", "REB", "AST", "STL", "BLK", "TO", "PF", "+/-", "PTS"],
          "athletes": [{"athlete": {"id": "9", "displayName": "Jayson Tatum", "position": {"abbreviation": "F"}}, "starter": True,
                        "stats": ["37", "10-21", "4-9", "6-7", "1", "8", "9", "6", "1", "0", "3", "2", "+11", "30"]},
                       {"athlete": {"id": "10", "displayName": "Bench Guy"}, "didNotPlay": True, "stats": []}]}]}]}}
    b = data.parse_box(js, "401")
    assert len(b) == 1 and b[0]["pts"] == 30 and b[0]["reb"] == 9 and b[0]["fg3"] == 4 and b[0]["min"] == 37


def test_build_writes_an_upcoming_slate():
    g, _, _ = synth_season(n_days=60)
    future = g.tail(7).copy()
    future["game_id"] = [f"f{i}" for i in range(7)]
    future["date"] = "2026-03-01"
    future["state"] = "pre"
    future[["home_score", "away_score"]] = np.nan
    games = pd.concat([g, future], ignore_index=True)
    out = build(games, pd.DataFrame(), None, None, dt.date(2026, 2, 27))
    assert out["meta"]["upcoming"] and len(out["games"]) == 7
    gm = out["games"][0]
    assert gm["home"]["logo"].endswith("/500-dark/h.png") and 0 < gm["p_home"] < 1
    sl, up = next_slate(games, dt.date(2026, 3, 1))
    assert not up and len(sl) == 7


def _preseason(g, n=10, season=2027, date="2026-10-10", flip=True):
    """n finished preseason games where the usual favourite gets blown out (to check they only nudge the ratings)."""
    p = g.head(n).copy()
    p["game_id"] = [f"p{i}" for i in range(n)]
    p["date"], p["season"], p["season_type"] = date, season, 1
    if flip:
        p["home_score"], p["away_score"] = p["away_score"] + 30, p["home_score"]
    return p


def test_preseason_counts_but_only_a_little():
    g, _, _ = synth_season()
    base = model.fit_ratings(model.add_rest(g), pd.Timestamp("2026-10-12"))
    both = model.fit_ratings(model.add_rest(pd.concat([g, _preseason(g)], ignore_index=True)), pd.Timestamp("2026-10-12"))
    assert both["games_preseason"] == 10 and base["games_preseason"] == 0
    moved = max(abs((both["off"][t] + both["dfn"][t]) - (base["off"][t] + base["dfn"][t])) for t in TEAMS)
    assert 0.05 < moved < 6          # it learns something, but ten blowouts don't rewrite the ratings
    old = _preseason(g, season=2025, date="2024-10-10")   # an older season's preseason is ignored
    assert model.fit_ratings(model.add_rest(pd.concat([g, old], ignore_index=True)), pd.Timestamp("2026-04-01"))["games_preseason"] == 0


def test_preseason_slate_and_new_players():
    g, _, _ = synth_season(n_days=40)
    pre_fut = g.tail(5).copy()
    pre_fut["game_id"] = [f"q{i}" for i in range(5)]
    pre_fut["date"], pre_fut["state"], pre_fut["season_type"], pre_fut["season"] = "2026-10-15", "pre", 1, 2027
    pre_fut[["home_score", "away_score"]] = np.nan
    pre_done = _preseason(g, n=4, date="2026-10-08", flip=False)
    games = pd.concat([g, pre_done, pre_fut], ignore_index=True)
    sl, up = next_slate(games, dt.date(2026, 10, 15))
    assert not up and len(sl) == 5 and (sl.season_type == 1).all()
    # a rookie who has only played preseason gets a projection; a veteran's minutes aren't dragged down by short preseason nights
    t = pre_fut.iloc[0].home
    gid = pre_done.game_id.iloc[0]
    rows = [dict(game_id=gid, team=t, player_id="rook", name="Rookie", pos="G", starter=False, min=22, pts=11, reb=3, ast=2, fg3=1)]
    for gid2 in g[(g.home == t) | (g.away == t)].game_id.tail(10):
        rows.append(dict(game_id=gid2, team=t, player_id="vet", name="Vet", pos="F", starter=True, min=34, pts=20, reb=7, ast=4, fg3=2))
    rows.append(dict(game_id=gid, team=t, player_id="vet", name="Vet", pos="F", starter=True, min=16, pts=8, reb=3, ast=2, fg3=1))
    P = model.player_projections(pd.DataFrame(rows), games, None, None, [dict(game_id="q0", home=t, away=pre_fut.iloc[0].away, pts_home=112.0, pts_away=108.0)])
    by = {p["id"]: p for p in P}
    assert "rook" in by and by["rook"]["gp"] == 0 and by["rook"]["gp_pre"] == 1
    assert by["vet"]["min"] > by["rook"]["min"]
    out = build(games, pd.DataFrame(), None, None, dt.date(2026, 10, 15))
    assert out["meta"]["preseason"] and all(gm["pre"] for gm in out["games"])
