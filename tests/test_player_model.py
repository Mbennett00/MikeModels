import numpy as np
import pandas as pd
import pytest

from nhlmodel.config import DEFAULT
from nhlmodel.params import FittedParams
from nhlmodel.player_model import player_market_prob, project_team_players
from nhlmodel.ratings import build_snapshot
from nhlmodel.team_model import TeamModel, shrink


def test_shrinkage_formula():
    # (n*rate + k*prior)/(n+k)
    assert shrink(60 * 10, 400, 1.0, 400) == pytest.approx((400 * 1.5 + 400 * 1.0) / 800)


def _one(league, cfg=DEFAULT):
    tables, _ = league
    g = tables["games"][tables["games"].date == pd.Timestamp("2024-12-10")].iloc[0]
    snap = build_snapshot(tables, g.date, 2024, cfg.half_life_games)
    P = FittedParams()
    tm = TeamModel(cfg, snap, P)
    gp = tm.project(g.home, g.away, date=g.date)
    lu = tables["lineups"]
    lu = lu[(lu.game_id == g.game_id) & (lu.team == g.home)]
    return project_team_players(tm, gp, "home", lu, P, cfg), P


def test_consistency_within_tolerance(league):
    (df, rep), _ = _one(league)
    after = df.lam_goals_nonen.sum() / rep["target_goals"] - 1
    assert abs(after) <= DEFAULT.consistency_tol + 1e-9
    assert (df.lam_goals > 0).all() and (df.lam_sog > 0).all()
    assert np.allclose(df.lam_pts, df.lam_goals + df.lam_ast)


def test_consistency_rescales_when_off(league):
    cfg = DEFAULT.with_(consistency_tol=0.0)
    (df, rep), _ = _one(league, cfg)
    assert df.lam_goals_nonen.sum() == pytest.approx(rep["target_goals"])


def test_unconfirmed_flagged(league):
    tables, _ = league
    lu = tables["lineups"].copy()
    lu["confirmed"] = False
    t = dict(tables, lineups=lu)
    (df, _), _ = _one((t, None))
    assert df["flags"].str.contains("UNCONFIRMED").all()


def test_market_probs(league):
    (df, _), P = _one(league)
    r = df.iloc[0].to_dict()
    assert player_market_prob(r, "goals", 0.5, P) == pytest.approx(1 - np.exp(-r["lam_goals"]))
    assert player_market_prob(r, "points", 0.5, P) == pytest.approx(1 - np.exp(-r["lam_pts"]))
    assert player_market_prob(r, "sog", 1.5, P) > player_market_prob(r, "sog", 2.5, P)
