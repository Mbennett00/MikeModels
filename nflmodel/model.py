"""Team ratings and game prices.

Ratings (as of a date, from games before it):
    each team-game gives three offensive numbers: EPA per play, EPA per dropback, points scored.
    For each, a weighted ridge regression  y = mu + home + O[offense] + D[defence]
    (weights halve every `half_life` days, so last season still counts but this season counts more;
    the ridge pulls every team toward average, which matters most in September).

Game expectation (stage 2, linear on the ratings, refit on past seasons only):
    margin = a + b . (home side - away side)     total = c + d . (home side + away side) + roof / wind
    side   = expected EPA/play, EPA/dropback and points for that offense against that defence.

Distribution: final margins pile up on 3, 7, 10, 6, 4, 14 ... so the margin pmf is a discretised normal
reweighted by key-number factors measured on past games (then re-centred to keep its mean). Totals use
the same idea with their own (weaker) factors. Moneyline, spread and total prices all come from these.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.stats import norm

METRICS = ("epa_play", "epa_db", "points")
KMAX = 70


@dataclass
class Config:
    half_life: float = 140.0     # days
    ridge: float = 6.0           # in "games" of evidence per team rating
    sd_margin: float = 13.6
    sd_total: float = 13.4
    qb_weight: float = 1.0       # 0 = ignore starting-QB changes
    qb_shrink: float = 250.0     # dropbacks of prior toward the team's QB-neutral passing level
    injuries: bool = True        # missing-starter features from the injury report
    coef_m: np.ndarray | None = None
    coef_t: np.ndarray | None = None
    key_m: dict = field(default_factory=dict)
    key_t: dict = field(default_factory=dict)


def team_rows(tg: pd.DataFrame, sched: pd.DataFrame) -> pd.DataFrame:
    """Team-game rows with the three offensive measures and points (from the schedule)."""
    s = sched[sched.result.notna()][["game_id", "home_score", "away_score", "location"]]
    d = tg.merge(s, on="game_id", how="inner")
    d["home"] = ((d.team == d.home_team) & (d.location != "Neutral")).astype(float)
    d["points"] = np.where(d.home == 1, d.home_score, d.away_score)
    n = (d.n_pass + d.n_rush).clip(lower=1)
    d["epa_play"] = (d.epa_pass + d.epa_rush) / n
    d["epa_db"] = d.epa_pass / d.n_pass.clip(lower=1)
    d["plays"] = n
    return d


def _ridge(rows: pd.DataFrame, y: str, w: np.ndarray, teams: list, lam: float) -> tuple[float, float, dict, dict]:
    T = len(teams)
    ix = {t: i for i, t in enumerate(teams)}
    n = len(rows)
    X = np.zeros((n, 2 + 2 * T))
    X[:, 0] = 1.0
    X[:, 1] = rows.home.to_numpy()
    r = np.arange(n)
    X[r, 2 + rows.team.map(ix).to_numpy()] = 1.0
    X[r, 2 + T + rows.opp.map(ix).to_numpy()] = 1.0
    yv = rows[y].to_numpy(float)
    P = np.full(2 + 2 * T, lam)
    P[:2] = 1e-6
    A = X.T @ (X * w[:, None]) + np.diag(P)
    b = X.T @ (w * yv)
    beta = np.linalg.solve(A, b)
    return beta[0], beta[1], dict(zip(teams, beta[2:2 + T])), dict(zip(teams, beta[2 + T:]))


@dataclass
class Ratings:
    asof: pd.Timestamp
    mu: dict
    home: dict
    off: dict      # metric -> team -> rating
    dfn: dict
    qb: dict = field(default_factory=dict)      # team -> (usual-QB passing level, name)


def fit_ratings(rows: pd.DataFrame, asof, cfg: Config) -> Ratings:
    asof = pd.Timestamp(asof)
    r = rows[rows.date < asof]
    age = (asof - r.date).dt.days.to_numpy(float)
    w = 0.5 ** (age / cfg.half_life)
    keep = w > 0.02
    r, w = r[keep], w[keep]
    teams = sorted(set(r.team) | set(r.opp))
    mu, home, off, dfn = {}, {}, {}, {}
    for m in METRICS:
        # per-play measures: weight by plays relative to a typical game, so a 40-play game counts less
        wm = w * (r.plays.to_numpy() / 60.0 if m == "epa_play" else r.n_pass.to_numpy() / 36.0 if m == "epa_db" else 1.0)
        a, h, o, d = _ridge(r, m, wm, teams, cfg.ridge * (1.0 if m == "points" else 1.0))
        mu[m], home[m], off[m], dfn[m] = a, h, o, d
    return Ratings(asof, mu, home, off, dfn)


def qb_levels(qb: pd.DataFrame, asof, cfg: Config) -> pd.DataFrame:
    """Each QB's EPA per dropback, recency weighted and shrunk toward replacement (-0.10)."""
    asof = pd.Timestamp(asof)
    q = qb[qb.date < asof]
    w = 0.5 ** ((asof - q.date).dt.days.to_numpy(float) / (2 * cfg.half_life))
    q = q.assign(w_db=w * q.dropbacks, w_epa=w * q.epa)
    g = q.groupby("qb_id").agg(name=("name", "last"), db=("w_db", "sum"), epa=("w_epa", "sum"),
                               raw_db=("dropbacks", "sum"), last=("date", "max"), team=("team", "last"))
    prior = -0.10
    g["level"] = (g.epa + prior * cfg.qb_shrink) / (g.db + cfg.qb_shrink)
    return g


def qb_adjust(qb: pd.DataFrame, levels: pd.DataFrame, team: str, starter: str | None, asof, cfg: Config) -> tuple[float, str | None]:
    """EPA/dropback change when `starter` (a name as nflverse writes it in the schedule) is not the team's usual QB mix."""
    if cfg.qb_weight <= 0 or not starter or not isinstance(starter, str):
        return 0.0, None
    asof = pd.Timestamp(asof)
    q = qb[(qb.team == team) & (qb.date < asof) & (qb.date >= asof - pd.Timedelta(days=cfg.half_life * 2))]
    if q.empty:
        return 0.0, None
    w = 0.5 ** ((asof - q.date).dt.days.to_numpy(float) / cfg.half_life) * q.dropbacks.to_numpy()
    lv = q.qb_id.map(levels.level).fillna(-0.10).to_numpy()
    usual = float((w * lv).sum() / w.sum())
    sid = _match_qb(levels, starter, team)
    lev = float(levels.level.get(sid, -0.12)) if sid else -0.12   # unknown starter: about replacement level
    return cfg.qb_weight * (lev - usual), sid


def _match_qb(levels: pd.DataFrame, full: str, team: str) -> str | None:
    """'Patrick Mahomes' -> the id whose pbp name is 'P.Mahomes' (prefer the same team, then most recent)."""
    parts = full.replace(".", "").split()
    if len(parts) < 2:
        return None
    last = " ".join(p for p in parts[1:] if p not in ("Jr", "Sr", "II", "III", "IV"))
    cand = levels[levels.name.fillna("").str.replace(".", " ", regex=False).str.split().str[-1].str.lower()
                  == last.split()[-1].lower()]
    if cand.empty:
        return None
    ini = cand[cand.name.fillna("").str[0].str.upper() == parts[0][0].upper()]
    cand = ini if len(ini) else cand
    same = cand[cand.team == team]
    cand = same if len(same) else cand
    return cand.sort_values("last").index[-1]


def side(R: Ratings, off: str, dfn: str, home: float) -> np.ndarray:
    """Expected (EPA/play, EPA/dropback, points) for `off` against `dfn`."""
    return np.array([R.mu[m] + R.home[m] * home + R.off[m].get(off, 0.0) + R.dfn[m].get(dfn, 0.0) for m in METRICS])


N_INJ = 6   # injury groups (see nflmodel.injuries.GROUPS)


def features(R: Ratings, home: str, away: str, neutral: bool = False, qb_h: float = 0.0, qb_a: float = 0.0,
             roof: str | None = None, wind=None, temp=None, inj_h=None, inj_a=None) -> tuple[np.ndarray, np.ndarray]:
    """inj_h / inj_a: missing starter-equivalents per injury group for each side (zeros = full strength)."""
    h = 0.0 if neutral else 1.0
    sh, sa = side(R, home, away, h), side(R, away, home, 0.0)
    # a QB change moves passing EPA; about 55% of plays are dropbacks
    sh = sh + np.array([0.55 * qb_h, qb_h, 0.0]); sa = sa + np.array([0.55 * qb_a, qb_a, 0.0])
    dome = 1.0 if str(roof) in ("dome", "closed") else 0.0
    wd = 0.0 if dome or wind is None or pd.isna(wind) else max(float(wind) - 10.0, 0.0)
    cold = 0.0 if dome or temp is None or pd.isna(temp) else max(40.0 - float(temp), 0.0)
    # injuries: one number per side, missing non-QB starters (backtest: splitting by position group overfit,
    # and injuries did not improve totals, so they only move the margin)
    ih = 0.0 if inj_h is None else float(np.sum(inj_h))
    ia = 0.0 if inj_a is None else float(np.sum(inj_a))
    xm = np.r_[1.0, h, sh - sa, ih - ia]
    xt = np.r_[1.0, sh + sa, dome, wd, cold]
    return xm, xt


def fit_stage2(X: np.ndarray, y: np.ndarray, ridge: float = 1.0) -> np.ndarray:
    P = np.full(X.shape[1], ridge); P[0] = 1e-6
    return np.linalg.solve(X.T @ X + np.diag(P), X.T @ y)


# ---------- distributions ----------

def key_factors(values: np.ndarray, centers: np.ndarray, sd: float, smooth: float = 30.0, absolute: bool = True) -> dict:
    """Observed / normal-expected frequency for each integer (|margin| or total), shrunk toward 1."""
    ks = np.arange(0, KMAX + 1) if absolute else np.arange(0, 120)
    obs = np.array([(np.abs(values) == k).sum() if absolute else (values == k).sum() for k in ks], float)
    exp = np.zeros(len(ks))
    for c in centers:
        if absolute:
            p = norm.cdf((ks + 0.5 - c) / sd) - norm.cdf((ks - 0.5 - c) / sd)
            p += np.where(ks > 0, norm.cdf((-ks + 0.5 - c) / sd) - norm.cdf((-ks - 0.5 - c) / sd), 0.0)
        else:
            p = norm.cdf((ks + 0.5 - c) / sd) - norm.cdf((ks - 0.5 - c) / sd)
        exp += p
    f = (obs + smooth) / (exp + smooth)
    return {int(k): round(float(v), 4) for k, v in zip(ks, f)}


def pmf(mean: float, sd: float, key: dict, absolute: bool, lo: int, hi: int) -> tuple[np.ndarray, np.ndarray]:
    ks = np.arange(lo, hi + 1)
    fk = np.array([key.get(int(abs(k) if absolute else k), 1.0) for k in ks])

    def make(c):
        p = (norm.cdf((ks + 0.5 - c) / sd) - norm.cdf((ks - 0.5 - c) / sd)) * fk
        return p / p.sum()
    c = mean
    for _ in range(6):          # re-centre so the reweighted pmf keeps the model's mean
        p = make(c)
        c += mean - float((ks * p).sum())
    return ks, make(c)


def margin_pmf(mean, cfg: Config):
    return pmf(mean, cfg.sd_margin, cfg.key_m, True, -KMAX, KMAX)


def total_pmf(mean, cfg: Config):
    return pmf(mean, cfg.sd_total, cfg.key_t, False, 0, 110)


def probs(ks: np.ndarray, p: np.ndarray, line: float) -> tuple[float, float, float]:
    """(P over, P push, P under) of value vs line."""
    return float(p[ks > line].sum()), float(p[ks == line].sum()), float(p[ks < line].sum())


def price_game(m_mean: float, t_mean: float, cfg: Config, spread: float | None = None, total: float | None = None) -> dict:
    """Win, spread (home side, nflverse sign: spread_line = expected home margin) and total probabilities."""
    km, pm = margin_pmf(m_mean, cfg)
    kt, pt = total_pmf(t_mean, cfg)
    win_h, tie, win_a = probs(km, pm, 0)
    out = dict(margin=m_mean, total=t_mean, p_home=win_h / (1 - tie), p_away=win_a / (1 - tie), p_tie=tie,
               margin_pmf=(km, pm), total_pmf=(kt, pt))
    if spread is not None and not pd.isna(spread):
        o, pu, u = probs(km, pm, spread)        # home covers when margin > spread_line
        out.update(spread=spread, p_home_cover=o / (1 - pu) if pu < 1 else 0.5, p_spread_push=pu)
    if total is not None and not pd.isna(total):
        o, pu, u = probs(kt, pt, total)
        out.update(total_line=total, p_over=o / (1 - pu) if pu < 1 else 0.5, p_total_push=pu)
    return out
