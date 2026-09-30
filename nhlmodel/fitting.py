"""Fit FittedParams using only information dated before the refit date.

Game-level quantities (EN transitions, P1 share, OT-goal share) come straight from
past results. Quantities that need model predictions (bivariate covariance lam3,
OT strength slope, rest effects, NB dispersion) are fitted on the walk-forward's
own *out-of-sample* predictions for earlier dates, so nothing leaks.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import ModelConfig
from .distributions import bivariate_poisson_logpmf, fit_nb_r
from .params import FittedParams

MIN_GAMES_LAM3 = 300
MIN_OT_GAMES = 150
PRIOR_EN_GAMES = 50.0


def fit_params(tables: dict, date, season: int, cfg: ModelConfig, game_preds: pd.DataFrame | None,
               player_preds: pd.DataFrame | None, league: dict | None = None) -> FittedParams:
    P = FittedParams()
    date = pd.Timestamp(date)
    g = tables["games"]
    g = g[(g.date < date) & (g.season > season - cfg.seasons_back)]
    notes = []

    # ---- empty-net transitions: leader's lead d -> P(0,1,2+ EN goals), smoothed to defaults
    if len(g):
        margin = g.home_reg_nonen - g.away_reg_nonen
        lead_en = np.where(margin > 0, g.home_en_reg, g.away_en_reg).clip(0, 2)
        for d in (1, 2, 3):
            sel = margin.abs().to_numpy() == d
            counts = np.bincount(lead_en[sel].astype(int), minlength=3)[:3].astype(float)
            prior = np.array(P.en_trans[d]) * PRIOR_EN_GAMES
            P.en_trans[d] = list((counts + prior) / (counts.sum() + PRIOR_EN_GAMES))
        reg = (g.home_reg_nonen + g.away_reg_nonen).sum()
        if reg > 0:
            P.p1_share = float((g.home_p1 + g.away_p1).sum() / reg)
        ot = g[g.decision.isin(["OT", "SO"])]
        if len(ot):
            P.ot_goal_share = float((ot.decision == "OT").mean())
    if league is not None and league.get("en_share", 0) < 0.5:
        P.en_uplift = 1.0 / (1.0 - league["en_share"])

    # ---- prediction-dependent parameters
    if game_preds is not None and len(game_preds):
        gp = game_preds[game_preds.date < date]
        if len(gp) >= MIN_GAMES_LAM3 and "lam_home_unscaled" in gp:
            # recency-weighted (half-life ~ 300 games) ratio of actual to unscaled predicted goals
            w = 0.5 ** (np.arange(len(gp))[::-1] / 300.0)
            act = (w * (gp.home_reg_nonen + gp.away_reg_nonen)).sum()
            pred = (w * (gp.lam_home_unscaled + gp.lam_away_unscaled)).sum()
            P.lam_scale = float(np.clip(act / pred, 0.9, 1.1))
            gp = gp.assign(lam_home=gp.lam_home_unscaled * P.lam_scale, lam_away=gp.lam_away_unscaled * P.lam_scale)
        if len(gp) >= MIN_GAMES_LAM3:
            grid = np.linspace(0.0, 0.30, 31)
            ll = [bivariate_poisson_logpmf(gp.home_reg_nonen, gp.away_reg_nonen, gp.lam_home, gp.lam_away, l).sum()
                  for l in grid]
            P.lam3 = float(grid[int(np.argmax(ll))])
        else:
            P.lam3 = cfg.biv_cov_default
            notes.append(f"lam3 default ({len(gp)} < {MIN_GAMES_LAM3} predicted games)")
        ot = gp[gp.decision.isin(["OT", "SO"])]
        if len(ot) >= MIN_OT_GAMES:
            share = (ot.lam_home / (ot.lam_home + ot.lam_away)).to_numpy() - 0.5
            y = (ot.home_final > ot.away_final).to_numpy()
            best = (0.0, -np.inf)
            for s in np.linspace(0, 2.0, 41):
                p = np.clip(0.5 + s * share, 0.3, 0.7)
                l = np.sum(np.where(y, np.log(p), np.log(1 - p)))
                if l > best[1]:
                    best = (float(s), l)
            P.ot_slope = best[0]
        else:
            notes.append(f"OT slope default ({len(ot)} OT/SO games)")
        P.rest, rn = _fit_rest(gp, cfg)
        P.rest_notes = rn
    if player_preds is not None and len(player_preds):
        pp = player_preds[player_preds.date < date]
        for pos in ("F", "D"):
            s = pp[pp.pos == pos]
            if len(s) >= cfg.nb_min_samples:
                r, _ = fit_nb_r(s.sog.to_numpy(), s.lam_sog.to_numpy())
                P.nb_r["sog"][pos] = r
            else:
                P.nb_r["sog"][pos] = cfg.nb_r_default[pos]
        if len(pp) >= cfg.nb_min_samples and "lam_sog_pre" in pp:
            P.recal, rn = fit_recal(pp, P)
            notes += rn
        if len(pp) >= cfg.nb_min_samples:
            for mkt, lam in (("assists", "lam_ast"), ("points", "lam_pts")):
                r, ll = fit_nb_r(pp[mkt].to_numpy(), pp[lam].to_numpy())
                _, llp = fit_nb_r(pp[mkt].to_numpy(), pp[lam].to_numpy(), grid=[1e6])
                # keep Poisson unless the NB improves log-lik by > 2 per 1000 obs (one extra parameter)
                P.count_r[mkt] = r if (ll - llp) > 2 * len(pp) / 1000 else 1e6
    P.notes = notes
    return P


def fit_recal(pp: pd.DataFrame, P: FittedParams) -> tuple[dict, list]:
    """Fit lam' = a * ref * (lam_pre / ref) ** b per prop market by maximum likelihood.

    lam_pre is the model's rate before recalibration. For goals and assists the level (a) is left to the
    team consistency check and the EN uplift, so only the spread b is used; shots get both.
    """
    from scipy import stats
    out, notes = dict(P.recal), []
    specs = (("goals", "lam_goals_nonen_pre", "goals", P.en_uplift),
             ("sog", "lam_sog_pre", "sog", 1.0),
             ("assists", "lam_ast_raw_pre", "assists", P.en_uplift))
    recent = pp.tail(60000)
    for mkt, col, y, mult in specs:
        if col not in recent:
            continue
        d = recent[[col, y, "pos"]].dropna()
        lam, k = np.clip(d[col].to_numpy(float) * mult, 1e-6, None), d[y].to_numpy(float)
        ref = float(lam.mean())
        best = (1.0, 1.0, -np.inf)
        for b in np.arange(0.8, 1.81, 0.05):
            shape = ref * (lam / ref) ** b
            a_grid = np.arange(0.8, 1.31, 0.01) if mkt == "sog" else [k.sum() / shape.sum()]
            for a in a_grid:
                m = a * shape
                if mkt == "sog":
                    r = d.pos.map(P.nb_r["sog"]).fillna(8.0).to_numpy()
                    ll = stats.nbinom.logpmf(k, r, r / (r + m)).sum()
                else:
                    ll = stats.poisson.logpmf(k, m).sum()
                if ll > best[2]:
                    best = (float(a), float(b), ll)
        a, b = (best[0] if mkt == "sog" else 1.0), best[1]
        out[mkt] = (a, b, ref / mult)
        notes.append(f"recal {mkt}: a={a:.2f} b={b:.2f}")
    return out, notes


def _fit_rest(gp: pd.DataFrame, cfg: ModelConfig):
    """Residual-ratio estimates of back-to-back / travel effects, kept only if |z| >= rest_min_z."""
    out = {"b2b_off": 1.0, "b2b_def": 1.0, "travel_off": 1.0}
    notes = []
    if not cfg.use_rest_factor or "home_b2b" not in gp:
        return out, ["rest factor disabled"]
    rows = []
    for side, opp in (("home", "away"), ("away", "home")):
        rows.append(pd.DataFrame({
            "goals": gp[f"{side}_reg_nonen"].to_numpy(), "lam": gp[f"lam_{side}_norest"].to_numpy(),
            "b2b": gp[f"{side}_b2b"].to_numpy(), "opp_b2b": gp[f"{opp}_b2b"].to_numpy(),
            "travel": gp[f"{side}_travel"].to_numpy()}))
    d = pd.concat(rows)
    if len(d) < 400:
        return out, ["rest factor: too few games, set to 1.0"]
    for key, mask in (("b2b_off", d.b2b), ("b2b_def", d.opp_b2b), ("travel_off", d.travel)):
        mask = mask.astype(bool)
        a, b = d[mask], d[~mask]
        if a.goals.sum() < 50:
            notes.append(f"{key}: insufficient sample")
            continue
        ra, rb = a.goals.sum() / a.lam.sum(), b.goals.sum() / b.lam.sum()
        eff = ra / rb
        se = np.sqrt(1 / a.goals.sum() + 1 / b.goals.sum())
        z = np.log(eff) / se
        if abs(z) >= cfg.rest_min_z:
            out[key] = float(eff)
            notes.append(f"{key}: kept {eff:.3f} (z={z:.1f})")
        else:
            notes.append(f"{key}: dropped {eff:.3f} (z={z:.1f} < {cfg.rest_min_z})")
    return out, notes
