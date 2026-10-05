"""NFL side of the calibration engine (calib/): what gets written to the prediction database and when.

    seed_backtest   walk-forward backtest games (each priced with earlier data only) -> predictions + results,
                    once (source='backtest'), so the engine has a meaningful sample from day one
    log_live        this week's projections each run (team points, game total, home win probability, player
                    props), with the components known at that moment; unchanged projections aren't re-stored
    record_results  finished games and box scores -> results (insert-only)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from calib import db

SPORT = "nfl"
PROPS = {"rec_yds": "player_rec_yds", "rush_yds": "player_rush_yds", "rec": "player_rec", "pass_yds": "player_pass_yds",
         "p_td": "player_td"}


def _team_rows(game_id, date, season, home, away, start, source, version, created, pts_h, pts_a, orig_h, orig_a,
               inp_h, inp_a, p_home, total, total_orig, neutral=False):
    conf = None if p_home is None or not np.isfinite(p_home) else max(p_home, 1 - p_home)
    base = dict(sport=SPORT, source=source, model_version=version, created_at=created, game_start=start,
                game_date=str(pd.Timestamp(date).date()), season=season, game_id=game_id, home=home, away=away,
                confidence=conf)
    out = []
    for team, opp, ish, v, o, inp in ((home, away, 0 if neutral else 1, pts_h, orig_h, inp_h),
                                      (away, home, 0, pts_a, orig_a, inp_a)):
        out.append(dict(base, pred_key=db.key(SPORT, game_id, "team_points", team), team=team, opponent=opp,
                        is_home=ish, subject_type="team", subject_id=team, subject_name=team,
                        projection_type="team_points", projection=v, original=o, inputs_json=inp))
    out.append(dict(base, pred_key=db.key(SPORT, game_id, "game_total_pts", "game"), subject_type="game",
                    subject_id="game", subject_name=f"{away} @ {home}", projection_type="game_total_pts",
                    projection=total, original=total_orig, inputs_json={}))
    if p_home is not None and np.isfinite(p_home):
        out.append(dict(base, pred_key=db.key(SPORT, game_id, "home_win_prob", "game"), subject_type="game",
                        subject_id="game", subject_name=f"{away} @ {home}", projection_type="home_win_prob",
                        projection=p_home, original=p_home, inputs_json={}))
    return out


def _inputs(off, dfn_opp, pas, qb, inj, inj_opp, wx, rest, rest_opp):
    rd = None if rest is None or rest_opp is None or pd.isna(rest) or pd.isna(rest_opp) else float(rest) - float(rest_opp)
    return dict(off=off, def_opp=dfn_opp, pass_off=pas, qb=qb, inj=inj, inj_opp=inj_opp, weather=wx, rest_diff=rd)


def seed_backtest(site: str, bt: pd.DataFrame, log=print) -> int:
    """bt: nflmodel.backtest.run rows (walk-forward: every game priced with data from before it)."""
    if bt is None or bt.empty or db.has_backtest(site, SPORT):
        return 0
    rows, res = [], []
    for x in bt.itertuples():
        ph, pa = (x.t_model + x.m_model) / 2, (x.t_model - x.m_model) / 2
        date = getattr(x, "gameday", None) or pd.Timestamp(f"{x.season}-09-01")
        created = (pd.Timestamp(date) - pd.Timedelta(days=1)).tz_localize("UTC").isoformat()
        ih = _inputs(x.off_h, x.dfn_a, x.pass_h, x.qb_h, x.inj_h_pts, x.inj_a_pts, x.wx_pts, x.rest_h, x.rest_a)
        ia = _inputs(x.off_a, x.dfn_h, x.pass_a, x.qb_a, x.inj_a_pts, x.inj_h_pts, x.wx_pts, x.rest_a, x.rest_h)
        rows += _team_rows(x.game_id, date, int(x.season), x.home, x.away, None, "backtest", "1.0", created, ph, pa, ph, pa,
                           ih, ia, x.p_home, x.t_model, x.t_model, bool(getattr(x, "neutral", False)))
        if not pd.isna(x.result):
            hs, as_ = (x.total + x.result) / 2, (x.total - x.result) / 2
            res += [dict(sport=SPORT, game_id=x.game_id, projection_type="team_points", subject_id=x.home, actual=hs),
                    dict(sport=SPORT, game_id=x.game_id, projection_type="team_points", subject_id=x.away, actual=as_),
                    dict(sport=SPORT, game_id=x.game_id, projection_type="game_total_pts", subject_id="game", actual=x.total),
                    dict(sport=SPORT, game_id=x.game_id, projection_type="home_win_prob", subject_id="game",
                         actual=1.0 if x.result > 0 else 0.0 if x.result < 0 else 0.5)]
    n = db.add_predictions(site, rows, dedupe_live=False)
    db.add_results(site, res)
    log(f"calib: seeded {n} NFL walk-forward predictions")
    return n


def log_live(site: str, entries: list, players: list, version: str, log=print) -> int:
    """entries: per pre-game game dicts prepared in daily.run (projections + components)."""
    created = db.now_iso()
    rows = []
    for e in entries:
        rows += _team_rows(e["game_id"], e["date"], e["season"], e["home"], e["away"], e["start"], "live", version,
                           created, e["pts_h"], e["pts_a"], e["orig_h"], e["orig_a"], e["inp_h"], e["inp_a"],
                           e["p_home"], e["pts_h"] + e["pts_a"], e["orig_h"] + e["orig_a"], e.get("neutral", False))
    starts = {e["game_id"]: (e["start"], e["date"], e["season"], e["home"], e["away"]) for e in entries}
    for p in players:
        if p["game_id"] not in starts:
            continue
        st, date, season, home, away = starts[p["game_id"]]
        for k, ptype in PROPS.items():
            v = p.get(k)
            if v is None:
                continue
            rows.append(dict(sport=SPORT, pred_key=db.key(SPORT, p["game_id"], ptype, p["id"]), source="live",
                             model_version=version, created_at=created, game_start=st, game_date=str(pd.Timestamp(date).date()),
                             season=season, game_id=p["game_id"], home=home, away=away, team=p["team"], opponent=p["opp"],
                             is_home=1 if p["team"] == home else 0, subject_type="player", subject_id=p["id"],
                             subject_name=p["name"], projection_type=ptype, projection=v, original=v, confidence=None,
                             inputs_json=dict(role=p.get("role"), tgt=p.get("tgt"), car=p.get("car"))))
    n = db.add_predictions(site, rows)
    if n:
        log(f"calib: stored {n} NFL projections")
    return n


def record_results(site: str, sched: pd.DataFrame, pg: pd.DataFrame) -> int:
    want = db.predicted_games(site, SPORT)
    done = sched[sched.result.notna() & sched.game_id.isin(want)]
    res = []
    for g in done.itertuples():
        res += [dict(sport=SPORT, game_id=g.game_id, projection_type="team_points", subject_id=g.home_team, actual=g.home_score),
                dict(sport=SPORT, game_id=g.game_id, projection_type="team_points", subject_id=g.away_team, actual=g.away_score),
                dict(sport=SPORT, game_id=g.game_id, projection_type="game_total_pts", subject_id="game", actual=g.total),
                dict(sport=SPORT, game_id=g.game_id, projection_type="home_win_prob", subject_id="game",
                     actual=1.0 if g.result > 0 else 0.0 if g.result < 0 else 0.5)]
    if pg is not None and len(pg):
        recent = pg[(pg.date >= pd.Timestamp.now() - pd.Timedelta(days=21)) & pg.game_id.isin(want)]
        for r in recent.itertuples():
            vals = dict(player_rec_yds=r.rec_yds, player_rush_yds=r.rush_yds, player_rec=r.rec,
                        player_td=float((r.rec_td + r.rush_td) > 0))
            if r.att > 0:
                vals["player_pass_yds"] = r.pass_yds
            for ptype, v in vals.items():
                res.append(dict(sport=SPORT, game_id=r.game_id, projection_type=ptype, subject_id=r.player_id, actual=v))
    return db.add_results(site, res)
