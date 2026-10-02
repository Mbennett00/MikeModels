"""Walk-forward test: each week is priced with ratings from earlier games only, and the stage-2 mapping
(ratings -> margin / total) is fit on earlier seasons only. Compared with the closing lines in the schedule."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import injuries as I
from . import model as M

FIRST_FEATURE_SEASON = 2019


def build_features(sched, tg, qb, cfg: M.Config, seasons=None, log=print, snaps=None, inj=None) -> pd.DataFrame:
    rows = M.team_rows(tg, sched)
    use_inj = cfg.injuries and snaps is not None and inj is not None and len(snaps)
    if use_inj:
        S = I.prep_snaps(snaps, sched)
        REP = I.history_reports(inj).groupby(["season", "week", "team"])
    g = sched[(sched.season >= FIRST_FEATURE_SEASON) & sched.game_type.notna()].copy()
    if seasons is not None:
        g = g[g.season.isin(seasons)]
    out = []
    for (season, week), wk in g.groupby(["season", "week"], sort=True):
        asof = wk.gameday.min()
        if rows[rows.date < asof].empty:
            continue
        R = M.fit_ratings(rows, asof, cfg)
        lv = M.qb_levels(qb, asof, cfg)
        for x in wk.itertuples():
            qh, _ = M.qb_adjust(qb, lv, x.home_team, getattr(x, "home_qb_name", None), asof, cfg)
            qa, _ = M.qb_adjust(qb, lv, x.away_team, getattr(x, "away_qb_name", None), asof, cfg)
            ih = ia = None
            if use_inj:
                vec = []
                for t in (x.home_team, x.away_team):
                    key = (season, week, t)
                    rep = REP.get_group(key) if key in REP.groups else None
                    vec.append(I.vector(I.missing(I.regulars(S, t, asof), rep)[0]))
                ih, ia = vec
            xm, xt = M.features(R, x.home_team, x.away_team, x.location == "Neutral", qh, qa, x.roof, x.wind, x.temp, ih, ia)
            out.append(dict(game_id=x.game_id, season=season, week=week, gameday=x.gameday, home=x.home_team,
                            away=x.away_team, result=x.result, total=x.total, spread_line=x.spread_line,
                            total_line=x.total_line, home_ml=x.home_moneyline, away_ml=x.away_moneyline,
                            qb_h=qh, qb_a=qa, xm=xm, xt=xt, inj_h=ih, inj_a=ia))
        log(f"  {season} wk {week}: {len(wk)} games") if week == 1 else None
    return pd.DataFrame(out)


def _novig(ml_h, ml_a):
    def imp(a):
        a = float(a)
        return np.nan if not np.isfinite(a) or abs(a) < 100 else (-a / (-a + 100) if a < 0 else 100 / (a + 100))
    ph, pa = imp(ml_h), imp(ml_a)
    return ph / (ph + pa)


def fit_mapping(F: pd.DataFrame, cfg: M.Config) -> M.Config:
    """Stage-2 coefficients, residual SDs and key-number factors from finished games in F."""
    done = F[F.result.notna()]
    Xm, Xt = np.vstack(done.xm), np.vstack(done.xt)
    cfg.coef_m = M.fit_stage2(Xm, done.result.to_numpy(float))
    cfg.coef_t = M.fit_stage2(Xt, done.total.to_numpy(float))
    cfg.sd_margin = float(np.std(done.result - Xm @ cfg.coef_m))
    cfg.sd_total = float(np.std(done.total - Xt @ cfg.coef_t))
    # key numbers measured around the market line (sharper centre than ours, cleaner factors)
    ok = done.spread_line.notna()
    cfg.key_m = M.key_factors(done.result[ok].to_numpy(), done.spread_line[ok].to_numpy(), 13.3)
    ok = done.total_line.notna()
    cfg.key_t = M.key_factors(done.total[ok].to_numpy(), done.total_line[ok].to_numpy(), 13.3, absolute=False)
    return cfg


def run(sched, tg, qb, cfg: M.Config, test_seasons=range(2021, 2027), F=None, log=print) -> tuple[pd.DataFrame, dict]:
    F = build_features(sched, tg, qb, cfg, log=log) if F is None else F
    res = []
    for s in test_seasons:
        train, test = F[F.season < s], F[(F.season == s) & F.result.notna()]
        if train.empty or test.empty:
            continue
        c = fit_mapping(train, M.Config(**{k: getattr(cfg, k) for k in ("half_life", "ridge", "qb_weight", "qb_shrink", "injuries")}))
        for x in test.itertuples():
            mm, tm = float(x.xm @ c.coef_m), float(x.xt @ c.coef_t)
            p = M.price_game(mm, tm, c, x.spread_line, x.total_line)
            res.append(dict(game_id=x.game_id, season=s, week=x.week, home=x.home, away=x.away, result=x.result,
                            total=x.total, spread_line=x.spread_line, total_line=x.total_line, m_model=mm, t_model=tm,
                            p_home=p["p_home"], p_cover=p.get("p_home_cover"), p_over=p.get("p_over"),
                            p_mkt=_novig(x.home_ml, x.away_ml) if not pd.isna(x.home_ml) else np.nan))
    R = pd.DataFrame(res)
    return R, summarize(R)


def summarize(R: pd.DataFrame) -> dict:
    if R.empty:
        return {}
    r = R[R.spread_line.notna()]
    cover = np.sign(r.result - r.spread_line)
    pick = np.sign(r.m_model - r.spread_line)
    out = dict(games=len(R),
               mae_model=float((R.result - R.m_model).abs().mean()), mae_line=float((r.result - r.spread_line).abs().mean()),
               tmae_model=float((R.total - R.t_model).abs().mean()),
               tmae_line=float((R.total - R.total_line).abs().mean()))
    for th in (0, 1.5, 3):
        sel = (np.abs(r.m_model - r.spread_line) > th) & (cover != 0)
        out[f"ats_{th}"] = (float((pick[sel] == cover[sel]).mean()), int(sel.sum()))
    t = R[R.total_line.notna()]
    ou = np.sign(t.total - t.total_line); tp = np.sign(t.t_model - t.total_line)
    for th in (0, 1.5, 3):
        sel = (np.abs(t.t_model - t.total_line) > th) & (ou != 0)
        out[f"ou_{th}"] = (float((tp[sel] == ou[sel]).mean()), int(sel.sum()))
    w = R[R.p_mkt.notna() & (R.result != 0)]
    y = (w.result > 0).astype(float)
    out["brier_model"] = float(((w.p_home - y) ** 2).mean())
    out["brier_mkt"] = float(((w.p_mkt - y) ** 2).mean())
    out["brier_blend"] = float(((0.5 * w.p_home + 0.5 * w.p_mkt - y) ** 2).mean())
    return out
