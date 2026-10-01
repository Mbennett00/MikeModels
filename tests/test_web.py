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
    # matchup breakdown: every factor present, and the projected goals match the card
    mx = g["mx"]
    for side in ("home", "away"):
        assert set(mx[side]) >= {"off", "dfn", "pp", "pk", "gk", "ppc", "rest", "home", "lam"}
    assert abs(mx["home"]["lam"] - g["lam_home"]) < 1e-3 and abs(mx["away"]["lam"] - g["lam_away"]) < 1e-3
    # rink view: every skater in the lines has an id and a matchup effect
    assert d["lines"] and all(x["id"] is not None and x["mx_pts"] is not None for x in d["lines"])


def test_web_build_without_games(tmp_path):
    web.build(None, pd.DataFrame(), dict(date="2026-07-01"), None, None, None, str(tmp_path))
    d = json.load(open(tmp_path / "data.json"))
    assert d["games"] == [] and d["meta"]["games"] == 0


def test_previous_slate_is_kept_for_last_night(tmp_path):
    from nhlmodel.daily import _publish_web
    site = tmp_path
    json.dump(dict(meta=dict(date="2026-09-29"), games=[{"game_id": 1}]), open(site / "web_data.json", "w"))
    _publish_web(str(site), None, pd.DataFrame(), dict(date="2026-09-30"))
    assert json.load(open(site / "web" / "prev.json"))["meta"]["date"] == "2026-09-29"
    assert json.load(open(site / "web_data.json"))["meta"]["date"] == "2026-09-30"
    # a second run the same day keeps last night's slate
    _publish_web(str(site), None, pd.DataFrame(), dict(date="2026-09-30"))
    assert json.load(open(site / "web" / "prev.json"))["meta"]["date"] == "2026-09-29"


def test_changelog_lists_what_moved():
    from nhlmodel.changelog import diff
    base = dict(slate="2026-10-01", data_through="2026-09-30", constants="tuned",
                params=dict(lam_scale=1.006, home_edge=0.022), recal={}, teams={"TOR": dict(off=1.0, dfn=1.0, pp=1.0, pk=1.0)},
                goalies={"NYI": ["Ilya Sorokin", "Likely"]}, injuries=[], trust={"total": "OK"},
                prices={"1": dict(matchup="NYI @ TOR", ml_home=0.45, over65=0.44)})
    cur = json.loads(json.dumps(base))
    cur["params"]["lam_scale"] = 1.010
    cur["goalies"]["NYI"] = ["Ilya Sorokin", "Confirmed"]
    cur["injuries"] = ["TOR|John Tavares|Day-to-day"]
    cur["prices"]["1"]["ml_home"] = 0.47
    cur["teams"]["TOR"]["off"] = 1.03
    text = " | ".join(i["text"] for i in diff(base, cur))
    for s in ("scoring calibration: 1.006 → 1.010", "Sorokin Likely → Confirmed", "Tavares listed Day-to-day",
              "TOR win 45% → 47%", "TOR attack +3%"):
        assert s in text, (s, text)
    assert diff(base, base) == []
    assert diff(None, base)[0]["icon"] == "🟢"
