"""Section 9: walk-forward, out-of-sample backtest by date.

For each game date D (in order):
  1. build a snapshot from rows dated < D only,
  2. every ``refit_every_days`` refit FittedParams from games < D and from this
     backtest's own earlier out-of-sample predictions,
  3. project every game on D and record predictions with their settled outcomes.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from .config import ModelConfig
from .fitting import fit_params
from .params import FittedParams
from .player_model import project_team_players
from .ratings import build_snapshot
from .team_model import TeamModel, rest_flags

GAME_LINES = {"total": [5.5, 6.0, 6.5], "team_total": [2.5, 3.5], "p1_total": [1.5]}
PLAYER_LINES = {"goals": [0.5, 1.5], "sog": [1.5, 2.5, 3.5, 4.5], "assists": [0.5, 1.5], "points": [0.5, 1.5, 2.5]}


def game_market_probs(gp, lines=GAME_LINES) -> list[dict]:
    """Every priced selection for a game. Complementary sides are included for pricing."""
    out = []
    ml = gp.moneyline()
    out += [dict(market="moneyline", selection=s, line=np.nan, p=ml[s]) for s in ("home", "away")]
    for side in ("home", "away"):
        for ln in (-1.5, 1.5):
            out.append(dict(market="puckline", selection=side, line=ln, p=gp.puckline(ln, side)))
    for ln in lines["total"]:
        t = gp.total(ln)
        out += [dict(market="total", selection=s, line=ln, p=t[s], push=t["push"]) for s in ("over", "under")]
    for side in ("home", "away"):
        for ln in lines["team_total"]:
            t = gp.team_total(side, ln)
            out += [dict(market="team_total", selection=f"{side}_{s}", line=ln, p=t[s]) for s in ("over", "under")]
    for ln in lines["p1_total"]:
        t = gp.p1_total(ln)
        out += [dict(market="p1_total", selection=s, line=ln, p=t[s]) for s in ("over", "under")]
    p1 = gp.p1_3way()
    out += [dict(market="p1_3way", selection=s, line=np.nan, p=p1[s]) for s in ("home", "draw", "away")]
    return out


def settle_game(market, selection, line, g) -> float:
    hf, af = g.home_final, g.away_final
    if market == "moneyline":
        return float((hf > af) if selection == "home" else (af > hf))
    if market == "puckline":
        m = (hf - af) if selection == "home" else (af - hf)
        return float(m + line > 0)
    if market in ("total", "team_total", "p1_total"):
        if market == "total":
            x = hf + af
        elif market == "p1_total":
            x = g.home_p1 + g.away_p1
        else:
            x = hf if selection.startswith("home") else af
        if float(x) == float(line):
            return np.nan  # push
        over = x > line
        return float(over if selection.endswith("over") else not over)
    if market == "p1_3way":
        h, a = g.home_p1, g.away_p1
        return float({"home": h > a, "draw": h == a, "away": h < a}[selection])
    raise ValueError(market)


def _goalie(lu: pd.DataFrame, team: str):
    g = lu[(lu.team == team) & (lu.pos == "G")]
    if g.empty:
        return None, False
    g = g.sort_values("line").iloc[0]
    return g.player_id, bool(g.confirmed)


def walk_forward(tables: dict, cfg: ModelConfig, start, end, date_stride: int = 1,
                 snap_cache: dict | None = None, verbose: bool = False, fixed_params: FittedParams | None = None):
    from . import team_model as _tm
    _tm.CALIBRATION = None   # the backtest is the calibration engine's training data: never calibrated itself
    games = tables["games"].sort_values(["date", "game_id"])
    games = games[(games.date >= pd.Timestamp(start)) & (games.date <= pd.Timestamp(end))]
    dates = sorted(games.date.unique())[::date_stride]
    lu_all = tables["lineups"]
    lu_by_game = {k: v for k, v in lu_all.groupby("game_id")}
    outcomes = tables["player_games"].set_index(["game_id", "player_id"])[["goals", "assists", "sog", "points"]]

    game_rows, market_rows, player_rows, cons_rows = [], [], [], []
    params, last_fit, fit_log = None, None, []
    t0 = time.time()
    for i, date in enumerate(dates):
        date = pd.Timestamp(date)
        day = games[games.date == date]
        season = int(day.season.iloc[0])
        key = (date, cfg.half_life_games, cfg.seasons_back, cfg.toi_window, cfg.prior_season_weight)
        snap = snap_cache.get(key) if snap_cache is not None else None
        if snap is None:
            snap = build_snapshot(tables, date, season, cfg.half_life_games, cfg.seasons_back, cfg.toi_window,
                                  cfg.prior_season_weight)
            if snap_cache is not None:
                snap_cache[key] = snap
        if snap.n_team_games < 64:
            continue   # not enough history
        if fixed_params is not None:
            params = fixed_params
        elif params is None or (date - last_fit).days >= cfg.refit_every_days:
            gdf = pd.DataFrame(game_rows) if game_rows else None
            pdf = pd.DataFrame(player_rows) if player_rows else None
            params = fit_params(tables, date, season, cfg, gdf, pdf, snap.league)
            last_fit = date
            fit_log.append(dict(date=date, recal={k: tuple(round(x, 2) for x in v) for k, v in params.recal.items()},
                                lam_scale=params.lam_scale, lam3=params.lam3, ot_slope=params.ot_slope, p1_share=params.p1_share,
                                en_uplift=params.en_uplift, r_sog_F=params.nb_r["sog"]["F"],
                                r_sog_D=params.nb_r["sog"]["D"], r_ast=params.count_r["assists"],
                                r_pts=params.count_r["points"], rest=dict(params.rest),
                                notes="; ".join(params.notes + params.rest_notes)))
        tm = TeamModel(cfg, snap, params)
        for g in day.itertuples(index=False):
            lu = lu_by_game.get(g.game_id)
            if lu is None:
                continue
            hg, hconf = _goalie(lu, g.home)
            ag, aconf = _goalie(lu, g.away)
            sk = {t: lu[(lu.team == t) & lu.pos.isin(["F", "D"])] for t in (g.home, g.away)}
            gp = tm.project(g.home, g.away, hg, ag, date, (hconf, aconf), sk)
            rf = {s: rest_flags(snap, t, g.home, date) for s, t in (("home", g.home), ("away", g.away))}
            game_rows.append(dict(
                game_id=g.game_id, date=date, season=season, home=g.home, away=g.away,
                lam_home=gp.lam_home, lam_away=gp.lam_away,
                lam_home_norest=gp.lam_home / gp.factors["home"]["rest"],
                lam_away_norest=gp.lam_away / gp.factors["away"]["rest"],
                lam_home_unscaled=gp.lam_home / gp.factors["home"]["scale"],
                lineup_home=gp.factors["home"]["lineup"], lineup_away=gp.factors["away"]["lineup"],
                lam_away_unscaled=gp.lam_away / gp.factors["away"]["scale"],
                home_b2b=rf["home"]["b2b"], away_b2b=rf["away"]["b2b"],
                home_travel=rf["home"]["travel_km"] > 1500 and rf["home"]["b2b"],
                away_travel=rf["away"]["travel_km"] > 1500 and rf["away"]["b2b"],
                home_reg_nonen=g.home_reg_nonen, away_reg_nonen=g.away_reg_nonen,
                home_final=g.home_final, away_final=g.away_final, decision=g.decision,
                flags="; ".join(gp.flags),
                # each multiplicative component of the goal rate, for the calibration engine (calib/)
                **{f"{side}_{k}": float(gp.factors[side][k]) for side in ("home", "away")
                   for k in ("off", "def_opp", "goalie_opp", "pp_pk", "pace", "rest", "home", "lineup", "scale")
                   if k in gp.factors[side]},
                p_home_win=float(gp.moneyline()["home"]) if hasattr(gp, "moneyline") else np.nan))
            for m in game_market_probs(gp):
                y = settle_game(m["market"], m["selection"], m["line"], g)
                market_rows.append(dict(game_id=g.game_id, date=date, player_id=np.nan, pos=None,
                                        market=m["market"], selection=m["selection"], line=m["line"],
                                        p_model=m["p"], y=y, confirmed=hconf and aconf))
            for side, team in (("home", g.home), ("away", g.away)):
                df, rep = project_team_players(tm, gp, side, lu[lu.team == team], params, cfg)
                cons_rows.append(dict(game_id=g.game_id, date=date, **rep))
                if df.empty:
                    continue
                idx = list(zip([g.game_id] * len(df), df.player_id))
                oc = outcomes.reindex(idx)
                df = df.assign(game_id=g.game_id, date=date, goals=oc.goals.to_numpy(),
                               assists=oc.assists.to_numpy(), sog=oc.sog.to_numpy(), points=oc.points.to_numpy(),
                               r_sog=df.pos.map(params.nb_r["sog"]).to_numpy(),
                               r_ast=params.count_r["assists"], r_pts=params.count_r["points"])
                df = df[df.goals.notna()]   # dressed but no stat line (scratched late)
                player_rows.extend(df.to_dict("records"))
        if verbose and i % 20 == 0:
            print(f"  {date.date()}  {i+1}/{len(dates)} dates  {time.time()-t0:.0f}s", flush=True)
    players = pd.DataFrame(player_rows)
    player_markets = player_market_rows(players) if len(players) else pd.DataFrame()
    return dict(games=pd.DataFrame(game_rows), game_markets=pd.DataFrame(market_rows), players=players,
                player_markets=player_markets, consistency=pd.DataFrame(cons_rows), fit_log=pd.DataFrame(fit_log))


def player_market_rows(players: pd.DataFrame, lines=PLAYER_LINES) -> pd.DataFrame:
    """Vectorised P(over line) per player-game, using the dispersion fitted at that date."""
    from scipy import stats
    out = []
    for market, lns in lines.items():
        lam = players[{"goals": "lam_goals", "sog": "lam_sog", "assists": "lam_ast", "points": "lam_pts"}[market]]
        r = {"goals": pd.Series(1e6, index=players.index), "sog": players.r_sog,
             "assists": players.r_ast, "points": players.r_pts}[market].astype(float)
        for ln in lns:
            k = np.floor(ln)
            pois = stats.poisson.sf(k, lam)
            nb = stats.nbinom.sf(k, r, r / (r + lam))
            p = np.where(r >= 1e5, pois, nb)
            out.append(pd.DataFrame(dict(game_id=players.game_id, date=players.date, player_id=players.player_id,
                                         name=players.name, pos=players.pos, market=market,
                                         selection="over", line=ln, p_model=p, lam=lam,
                                         y=(players[market] > ln).astype(float), confirmed=players.confirmed)))
    return pd.concat(out, ignore_index=True)
