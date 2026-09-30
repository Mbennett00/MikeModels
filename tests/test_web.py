import json

import numpy as np
import pandas as pd

from nhlmodel import web
from nhlmodel.config import DEFAULT
from nhlmodel.slate import build_state, price_state


def test_web_build_exports_prices_that_match_the_model(league, tmp_path):
    tables, _ = league
    day = pd.Timestamp("2024-12-10")
    sched = tables["games"][tables["games"].date == day][["game_id", "date", "home", "away"]]
    lineups = tables["lineups"][tables["lineups"].game_id.isin(sched.game_id)]
    hist = {k: v[v.date < day] for k, v in tables.items() if not k.startswith("_")}
    st = build_state(hist, sched, lineups, None, DEFAULT, None, day)
    plays, _, _ = price_state(st)
    news = dict(injuries=[dict(team=sched.home.iloc[0], name="Hurt Guy", status="IR")])
    out = web.build(st, plays, dict(date="2024-12-10", generated_at="x"), news, None, None, str(tmp_path / "web"))
    for f in ("index.html", ".nojekyll", "apple-touch-icon.png", "manifest.webmanifest"):
        assert (tmp_path / "web" / f).exists()
    d = json.load(open(f"{out}/data.json"))
    assert len(d["games"]) == len(sched) and d["players"]
    g = d["games"][0]
    assert g["home"]["injuries"][0]["name"] == "Hurt Guy"
    # the page prices moneylines from the exported matrix + OT split; it must equal the model's price
    m = np.array(g["reg"])
    hw, tie = np.tril(m, -1).sum(), np.trace(m)
    ml = plays[(plays.game_id == g["game_id"]) & (plays.market == "moneyline") & (plays.selection == "home")]
    assert abs(hw + tie * g["p_ot_home"] - ml.p_model.iloc[0]) < 1e-3
    assert abs(m.sum() - 1) < 1e-3


def test_web_build_without_games(tmp_path):
    web.build(None, pd.DataFrame(), dict(date="2026-07-01"), None, None, None, str(tmp_path))
    d = json.load(open(tmp_path / "data.json"))
    assert d["games"] == [] and d["meta"]["games"] == 0
