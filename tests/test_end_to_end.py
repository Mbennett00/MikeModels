import numpy as np
import pandas as pd

from nhlmodel.backtest import walk_forward
from nhlmodel.config import DEFAULT
from nhlmodel.slate import price_slate
from nhlmodel.validation import (attach_baselines, bet_summary, calibration_table, flagged_bets,
                                 market_report)


def test_walk_forward_and_validation(league):
    tables, _ = league
    cfg = DEFAULT.with_(refit_every_days=7)
    bt = walk_forward(tables, cfg, "2024-11-20", "2024-12-05")
    assert len(bt["games"]) > 20 and len(bt["player_markets"]) > 1000
    assert bt["game_markets"].p_model.between(0, 1).all()
    gm, pm = attach_baselines(bt, tables, cfg)
    summary, calib = market_report(pd.concat([gm, pm]), cfg)
    assert {"goals", "sog", "moneyline", "total"} <= set(summary.market)
    assert summary.status.notna().all()
    bets = flagged_bets(pd.concat([gm, pm]), tables["odds"], cfg)
    assert {"edge", "clv_prob", "flag"} <= set(bets.columns)
    bet_summary(bets)


def test_calibration_low_sample_warning():
    p = np.r_[np.full(50, 0.05), np.full(500, 0.5)]
    y = np.r_[np.zeros(50), np.ones(250), np.zeros(250)]
    tab = calibration_table(p, y, DEFAULT.calib_edges)
    assert tab.set_index("bucket").loc["0%-10%", "low_sample"]
    assert not tab.set_index("bucket").loc["50%-60%", "low_sample"]


def test_slate_outputs_required_columns(league):
    tables, _ = league
    day = pd.Timestamp("2024-12-10")
    sched = tables["games"][tables["games"].date == day][["game_id", "date", "home", "away"]]
    lineups = tables["lineups"][tables["lineups"].game_id.isin(sched.game_id)]
    odds = tables["odds"][tables["odds"].game_id.isin(sched.game_id) & (tables["odds"].snapshot == "open")]
    hist = {k: v[v.date < day] for k, v in tables.items()}
    plays, cons, warnings, _ = price_slate(hist, sched, lineups, odds, DEFAULT, None, day)
    for c in ("projection", "p_model", "fair_odds", "p_novig", "book_novig_odds", "edge", "flag", "confidence"):
        assert c in plays.columns
    priced = plays[plays.p_novig.notna()]
    assert len(priced) > 0
    assert np.allclose(priced.edge, priced.p_model - priced.p_novig)
    assert len(cons) == 2 * len(sched)
