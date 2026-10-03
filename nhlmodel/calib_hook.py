"""NHL side of the calibration engine (calib/): what gets written to the prediction database and when.

    seed_backtest   walk-forward backtest games and players (each priced with earlier data only) -> predictions
                    + results, once (source='backtest'), so the engine has a meaningful sample from day one
    log_live        each slate run: team goal rates (with every multiplicative component), home win probability,
                    game total, player shots and goals; unchanged projections aren't re-stored
    record_results  finished games and box scores -> results (insert-only)
    use_live        turns the active calibration on for live pricing (never on in the walk-forward backtest)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from calib import db
from calib import engine as CE

SPORT = "nhl"
COMP = ("off", "def_opp", "goalie_opp", "pp_pk", "pace", "rest", "home", "lineup", "scale")


def _rows(game_id, date, season, home, away, start, source, version, created, lam, orig, comps, p_home):
    gid = str(int(game_id))
    conf = None if p_home is None or not np.isfinite(p_home) else max(p_home, 1 - p_home)
    base = dict(sport=SPORT, source=source, model_version=version, created_at=created, game_start=start,
                game_date=str(pd.Timestamp(date).date()), season=int(season) if season else None, game_id=gid,
                home=home, away=away, confidence=conf)
    out = []
    for side, team, opp, ish in (("home", home, away, 1), ("away", away, home, 0)):
        out.append(dict(base, pred_key=db.key(SPORT, gid, "team_goals", team), team=team, opponent=opp, is_home=ish,
                        subject_type="team", subject_id=team, subject_name=team, projection_type="team_goals",
                        projection=lam[side], original=orig[side], inputs_json=comps[side]))
    out.append(dict(base, pred_key=db.key(SPORT, gid, "game_total", "game"), subject_type="game", subject_id="game",
                    subject_name=f"{away} @ {home}", projection_type="game_total", projection=lam["home"] + lam["away"],
                    original=orig["home"] + orig["away"], inputs_json={}))
    if p_home is not None and np.isfinite(p_home):
        out.append(dict(base, pred_key=db.key(SPORT, gid, "home_win_prob", "game"), subject_type="game",
                        subject_id="game", subject_name=f"{away} @ {home}", projection_type="home_win_prob",
                        projection=p_home, original=p_home, inputs_json={}))
    return out


def seed_backtest(site: str, games: pd.DataFrame, players: pd.DataFrame | None, names: dict | None = None,
                  log=print) -> int:
    """games / players: nhlmodel.backtest.walk_forward output (bt_games / bt_players)."""
    if games is None or games.empty or db.has_backtest(site, SPORT):
        return 0
    rows, res = [], []
    for g in games.itertuples():
        d = g._asdict()
        created = (pd.Timestamp(g.date) - pd.Timedelta(days=1)).tz_localize("UTC").isoformat()
        comps = {s: {k: d.get(f"{s}_{k}") for k in COMP if d.get(f"{s}_{k}") is not None} for s in ("home", "away")}
        for s in ("home", "away"):
            comps[s]["b2b"] = bool(d.get(f"{s}_b2b"))
        lam = dict(home=g.lam_home, away=g.lam_away)
        rows += _rows(g.game_id, g.date, d.get("season"), g.home, g.away, None, "backtest", "1.0", created, lam, lam,
                      comps, d.get("p_home_win"))
        gid = str(int(g.game_id))
        res += [dict(sport=SPORT, game_id=gid, projection_type="team_goals", subject_id=g.home, actual=g.home_reg_nonen),
                dict(sport=SPORT, game_id=gid, projection_type="team_goals", subject_id=g.away, actual=g.away_reg_nonen),
                dict(sport=SPORT, game_id=gid, projection_type="game_total", subject_id="game",
                     actual=g.home_reg_nonen + g.away_reg_nonen),
                dict(sport=SPORT, game_id=gid, projection_type="home_win_prob", subject_id="game",
                     actual=float(g.home_final > g.away_final))]
    if players is not None and len(players):
        dates = pd.to_datetime(players.date)
        players = players[dates >= dates.max() - pd.Timedelta(days=90)]   # keep the database small; live rows accrue
        for p in players.itertuples():
            gid, pid = str(int(p.game_id)), str(int(p.player_id))
            created = (pd.Timestamp(p.date) - pd.Timedelta(days=1)).tz_localize("UTC").isoformat()
            nm = (names or {}).get(int(p.player_id), pid)
            for ptype, lam, act in (("player_sog", p.lam_sog, p.sog), ("player_goals", p.lam_goals, p.goals)):
                if pd.isna(lam):
                    continue
                rows.append(dict(sport=SPORT, pred_key=db.key(SPORT, gid, ptype, pid), source="backtest", model_version="1.0",
                                 created_at=created, game_start=None, game_date=str(pd.Timestamp(p.date).date()),
                                 season=None, game_id=gid, subject_type="player", subject_id=pid, subject_name=nm,
                                 projection_type=ptype, projection=lam, original=lam, inputs_json=dict(pos=p.pos)))
                if not pd.isna(act):
                    res.append(dict(sport=SPORT, game_id=gid, projection_type=ptype, subject_id=pid, actual=act))
    n = db.add_predictions(site, rows, dedupe_live=False)
    db.add_results(site, res)
    log(f"calib: seeded {n} NHL walk-forward predictions")
    return n


def log_live(site: str, state, plays: pd.DataFrame, version: str, log=print) -> int:
    """state.projections is filled by slate.price_state: (game row, GameProjection) per game."""
    created = db.now_iso()
    rows = []
    for g, gp in getattr(state, "projections", []) or []:
        f = gp.factors
        comps = {s: {k: float(f[s][k]) for k in COMP if k in f[s]} for s in ("home", "away")}
        lam = dict(home=gp.lam_home, away=gp.lam_away)
        orig = dict(home=f["home"].get("lam_orig", gp.lam_home), away=f["away"].get("lam_orig", gp.lam_away))
        start = getattr(g, "start_utc", None)
        rows += _rows(g.game_id, state.date, getattr(state.snap, "season", None), g.home, g.away,
                      str(pd.Timestamp(start).isoformat()) if start else None, "live", version, created, lam, orig,
                      comps, float(gp.moneyline()["home"]))
    if plays is not None and len(plays):
        pp = plays[(plays.player.fillna("") != "") & (plays.selection == "over") & plays.market.isin(["sog", "goals"])]
        starts = {int(g.game_id): getattr(g, "start_utc", None) for g, _ in getattr(state, "projections", []) or []}
        for (gid, pid, mkt), d in pp.groupby(["game_id", "player_id", "market"]):
            v = pd.to_numeric(d.projection, errors="coerce").iloc[0]
            if pd.isna(v):
                continue
            r0 = d.iloc[0]
            ptype = "player_sog" if mkt == "sog" else "player_goals"
            st = starts.get(int(gid))
            rows.append(dict(sport=SPORT, pred_key=db.key(SPORT, int(gid), ptype, int(pid)), source="live",
                             model_version=version, created_at=created, game_start=str(pd.Timestamp(st).isoformat()) if st else None,
                             game_date=str(pd.Timestamp(state.date).date()), season=None, game_id=str(int(gid)),
                             team=r0.get("team"), subject_type="player", subject_id=str(int(pid)), subject_name=r0.player,
                             projection_type=ptype, projection=float(v), original=float(v), confidence=None,
                             inputs_json=dict(pos=r0.get("pos"))))
    n = db.add_predictions(site, rows)
    if n:
        log(f"calib: stored {n} NHL projections")
    return n


def record_results(site: str, tables: dict) -> int:
    want = db.predicted_games(site, SPORT)
    games = tables["games"]
    games = games[games.game_id.astype(int).astype(str).isin(want)]
    res = []
    for g in games.itertuples():
        gid = str(int(g.game_id))
        res += [dict(sport=SPORT, game_id=gid, projection_type="team_goals", subject_id=g.home, actual=g.home_reg_nonen),
                dict(sport=SPORT, game_id=gid, projection_type="team_goals", subject_id=g.away, actual=g.away_reg_nonen),
                dict(sport=SPORT, game_id=gid, projection_type="game_total", subject_id="game",
                     actual=g.home_reg_nonen + g.away_reg_nonen),
                dict(sport=SPORT, game_id=gid, projection_type="home_win_prob", subject_id="game",
                     actual=float(g.home_final > g.away_final))]
    pg = tables.get("player_games")
    if pg is not None and len(pg):
        pg = pg[pg.game_id.astype(int).astype(str).isin(want)]
        for r in pg.itertuples():
            gid, pid = str(int(r.game_id)), str(int(r.player_id))
            res += [dict(sport=SPORT, game_id=gid, projection_type="player_sog", subject_id=pid, actual=r.sog),
                    dict(sport=SPORT, game_id=gid, projection_type="player_goals", subject_id=pid, actual=r.goals)]
    return db.add_results(site, res)


def use_live(site: str):
    """Turn on the active calibration for live pricing (TeamModel reads team_model.CALIBRATION)."""
    from . import team_model
    CE.ensure_baseline(site, SPORT)
    cal = CE.Live(site, SPORT)
    team_model.CALIBRATION = cal if cal.params else None
    return cal
