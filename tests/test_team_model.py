import numpy as np
import pandas as pd
import pytest

from nhlmodel.config import DEFAULT
from nhlmodel.params import FittedParams
from nhlmodel.ratings import build_snapshot
from nhlmodel.team_model import TeamModel, apply_en


@pytest.fixture(scope="module")
def gp(league):
    tables, _ = league
    snap = build_snapshot(tables, "2024-12-10", 2024, 25)
    return TeamModel(DEFAULT, snap, FittedParams()).project("BOS", "TOR", date="2024-12-10")


def test_sides_are_complementary(gp):
    ml = gp.moneyline()
    assert ml["home"] + ml["away"] == pytest.approx(1)
    assert gp.puckline(-1.5, "home") + gp.puckline(1.5, "away") == pytest.approx(1)
    assert gp.puckline(-1.5, "away") + gp.puckline(1.5, "home") == pytest.approx(1)
    assert sum(gp.p1_3way().values()) == pytest.approx(1)


def test_totals(gp):
    t = gp.total(6.5)
    assert t["over"] + t["under"] == pytest.approx(1) and t["push"] == 0
    w = gp.total(6)
    assert w["push"] > 0 and w["over"] + w["under"] == pytest.approx(1)
    # final total counts the OT/SO goal: odd totals get extra mass from regulation ties
    assert gp.total_dist().sum() == pytest.approx(1)
    tt = gp.team_total("home", 2.5)
    assert tt["over"] + tt["under"] == pytest.approx(1)


def test_puckline_needs_regulation_margin(gp):
    # home -1.5 can never exceed P(home regulation win)
    hw, tie, aw = gp.reg_probs()
    assert gp.puckline(-1.5, "home") < hw


def test_empty_net_shifts_tail_only():
    m = np.zeros((6, 6)); m[3, 2] = 1.0
    out = apply_en(m, {1: [0.7, 0.3, 0.0]})
    assert out[3, 2] == pytest.approx(0.7) and out[4, 2] == pytest.approx(0.3)
    m = np.zeros((6, 6)); m[2, 2] = 1.0
    assert apply_en(m, {1: [0.7, 0.3, 0.0]})[2, 2] == pytest.approx(1.0)


def test_no_leakage(league):
    """A snapshot for date D must not change when data on/after D changes."""
    tables, _ = league
    d = pd.Timestamp("2024-11-20")
    s1 = build_snapshot(tables, d, 2024, 25)
    t2 = {k: v.copy() for k, v in tables.items()}
    for k in ("team_games", "player_games", "goalie_games"):
        later = t2[k].date >= d
        num = t2[k].select_dtypes("number").columns.difference(["game_id", "season", "player_id", "goalie_id", "is_home", "pp_unit"])
        t2[k].loc[later, num] = t2[k].loc[later, num] * 5 + 3
    s2 = build_snapshot(t2, d, 2024, 25)
    pd.testing.assert_frame_equal(s1.team, s2.team)
    pd.testing.assert_frame_equal(s1.player, s2.player)
    pd.testing.assert_frame_equal(s1.goalie, s2.goalie)
