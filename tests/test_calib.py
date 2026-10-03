"""Calibration engine: data integrity, shrinkage, bias detection, leak-free features, accept / reject."""
import sqlite3

import numpy as np
import pandas as pd
import pytest

from calib import bias as B, db, engine as E
from calib.config import CalibConfig


def _seed(site, n_games=400, bias_road=0.0, signal=0.0, noise=1.5, seed=0, sport="nhl"):
    """Synthetic team-goal predictions: actual = original + bias_road (road teams) + signal * goalie + noise."""
    rng = np.random.default_rng(seed)
    rows, res = [], []
    d0 = pd.Timestamp("2025-10-01")
    for i in range(n_games):
        date = d0 + pd.Timedelta(days=i // 4)
        gid = f"g{i}"
        for team, opp, ish in (("AAA", "BBB", 1), ("BBB", "AAA", 0)):
            g = rng.normal(0, 0.1)
            orig = 3.0 + rng.normal(0, 0.3)
            act = orig + (bias_road if ish == 0 else 0) + signal * g / 0.1 + rng.normal(0, noise)
            rows.append(dict(sport=sport, pred_key=db.key(sport, gid, "team_goals", team), source="backtest",
                             model_version="1.0", created_at=(date - pd.Timedelta(days=1)).tz_localize("UTC").isoformat(),
                             game_start=None, game_date=str(date.date()), season=2025, game_id=gid, home="AAA", away="BBB",
                             team=team, opponent=opp, is_home=ish, subject_type="team", subject_id=team, subject_name=team,
                             projection_type="team_goals", projection=orig, original=orig, confidence=0.55,
                             inputs_json=dict(off=1.0, def_opp=1.0, goalie_opp=float(np.exp(g)), pp_pk=1.0, pace=1.0, rest=1.0)))
            res.append(dict(sport=sport, game_id=gid, projection_type="team_goals", subject_id=team, actual=act))
    db.add_predictions(site, rows, dedupe_live=False)
    db.add_results(site, res)


def test_predictions_and_versions_are_immutable(tmp_path):
    site = str(tmp_path)
    _seed(site, 5)
    con = sqlite3.connect(db.path(site), isolation_level=None)   # autocommit: blocked writes leave no lock
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("UPDATE predictions SET projection = 9")
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("DELETE FROM predictions")
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("UPDATE results SET actual = 0")
    E.ensure_baseline(site, "nhl")
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("DELETE FROM model_versions")
    # a result is recorded once; re-recording can't change it
    db.add_results(site, [dict(sport="nhl", game_id="g0", projection_type="team_goals", subject_id="AAA", actual=99)])
    assert db.graded(site, "nhl").query("game_id == 'g0' and team == 'AAA'").actual.iloc[0] != 99


def test_live_rows_dedupe_and_pre_game_selection(tmp_path):
    site = str(tmp_path)
    base = dict(sport="nfl", source="live", model_version="1.0", game_start="2026-10-04T17:00:00+00:00",
                game_date="2026-10-04", season=2026, game_id="x", team="KC", opponent="LV", is_home=1,
                subject_type="team", subject_id="KC", projection_type="team_points", original=24, inputs_json={})
    k = db.key("nfl", "x", "team_points", "KC")
    db.add_predictions(site, [dict(base, pred_key=k, created_at="2026-10-03T12:00:00+00:00", projection=24.0)])
    db.add_predictions(site, [dict(base, pred_key=k, created_at="2026-10-03T18:00:00+00:00", projection=24.0)])  # unchanged
    db.add_predictions(site, [dict(base, pred_key=k, created_at="2026-10-04T15:00:00+00:00", projection=25.5)])
    db.add_predictions(site, [dict(base, pred_key=k, created_at="2026-10-04T18:00:00+00:00", projection=30.0)])  # after kickoff
    db.add_results(site, [dict(sport="nfl", game_id="x", projection_type="team_points", subject_id="KC", actual=27)])
    assert db.counts(site)["nfl"]["predictions"] == 3
    g = db.graded(site, "nfl")
    assert len(g) == 1 and g.projection.iloc[0] == 25.5     # last pre-game projection, not the post-kickoff one


def test_shrinkage_tiers_are_configurable():
    c = CalibConfig()
    assert c.shrink(10) == 0 and c.shrink(30) == 0.10 and c.shrink(75) == 0.25 and c.shrink(150) == 0.5 and c.shrink(500) == 0.75
    c2 = CalibConfig(tiers=[(0, 0.0), (10, 1.0)])
    assert c2.shrink(12) == 1.0


def test_bias_detection_needs_meaningful_samples():
    rng = np.random.default_rng(3)
    # 60 noise segments: false-discovery control should report nothing
    cands = [dict(segment=f"s{i}", what=f"seg {i}", unit="goals", e=pd.Series(rng.normal(0, 1.5, 60))) for i in range(60)]
    assert B.detect(cands, 25, 0.05) == []
    # a real bias in a decent sample is found; the same bias in a tiny sample is not
    real = dict(segment="road", what="road teams", unit="goals", e=pd.Series(rng.normal(-0.6, 1.5, 400)))
    tiny = dict(segment="tiny", what="tiny", unit="goals", e=pd.Series([-3.0, -2.5, -4.0]))
    out = B.detect(cands + [real, tiny], 25, 0.05)
    assert [r["segment"] for r in out] == ["road"] and "underestimating" in out[0]["text"]


def test_recent_form_uses_only_earlier_games():
    d = pd.DataFrame(dict(id=range(6), team=["A"] * 6, game_date=pd.to_datetime(
        ["2025-10-01", "2025-10-03", "2025-10-05", "2025-10-07", "2025-10-09", "2025-10-11"]),
        actual=[5, 5, 5, 0, 0, 0], original=[3.0] * 6))
    f = E.add_form(d).set_index("id").form
    assert f[0] == 0 and f[1] == 0 and f[2] == 0          # fewer than 3 earlier games
    assert f[3] == pytest.approx(2.0)                     # games 0-2 only, not game 3's own result
    assert f[4] == pytest.approx((2 + 2 + 2 - 3) / 4)


def test_recalibration_rejects_noise_and_insufficient(tmp_path):
    site = str(tmp_path)
    E.ensure_baseline(site, "nhl")
    _seed(site, 30)
    r = E.recalibrate(site, "nhl", CalibConfig(), log=lambda *a: None)
    assert r["status"] == "insufficient"
    site2 = str(tmp_path / "b")
    E.ensure_baseline(site2, "nhl")
    _seed(site2, 500, seed=1)                            # an unbiased model: nothing to fix
    r = E.recalibrate(site2, "nhl", CalibConfig(), log=lambda *a: None)
    assert r["status"] == "rejected"
    assert db.active(site2, "nhl")["version"] == "1.0"  # unchanged
    assert [v["status"] for v in db.versions(site2, "nhl")] == ["baseline", "rejected"]


def test_recalibration_fixes_a_real_bias_conservatively(tmp_path):
    site = str(tmp_path)
    E.ensure_baseline(site, "nhl")
    _seed(site, 900, bias_road=-0.5, signal=0.25, seed=2)   # road teams under-projected; goaltending under-weighted
    r = E.recalibrate(site, "nhl", CalibConfig(), log=lambda *a: None)
    assert r["status"] == "applied", r["reason"]
    assert r["after"]["mae"] < r["before"]["mae"]
    assert db.active(site, "nhl")["version"] == "1.1"
    p = db.active(site, "nhl")["params"]
    assert "goalie_opp" in p["features"] and p["blend"] <= 0.5 and p["shrink"] <= 0.75
    assert any("goaltending" in c for c in r["changes"])
    assert any(b["segment"] == "road" for b in r["biases"])
    # the live correction is capped
    live = E.Live(site, "nhl")
    out = live(3.0, dict(off=1, def_opp=1, goalie_opp=50.0, pp_pk=1, pace=1, rest=1), "AAA", 0)
    assert abs(out - 3.0) <= 0.15 * 3.0 + 1e-9


def test_walk_forward_never_trains_on_the_future(tmp_path, monkeypatch):
    site = str(tmp_path)
    _seed(site, 300, seed=4)
    d, feats = E.prep(db.graded(site, "nhl", "team_goals"), E.SPECS["nhl"])
    seen = []
    real_fit = E.fit

    def spy(train, feats_, cfg, blend, asof=None):
        seen.append((train.game_date.max(), pd.Timestamp(asof)))
        return real_fit(train, feats_, cfg, blend, asof)
    monkeypatch.setattr(E, "fit", spy)
    E.walk_forward(d, feats, CalibConfig(), 0.5)
    assert seen and all(last < asof for last, asof in seen)
