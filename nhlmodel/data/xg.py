"""Expected-goals model fit on NHL API play-by-play (unblocked, non-empty-net shots).

Logistic regression on distance, angle, shot type, rebound and strength. To avoid
leakage each season's shots are scored with a model fit on the *previous* season
(the earliest season in the data is scored with its own fit and flagged).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

SHOT_TYPES = ["wrist", "snap", "slap", "backhand", "tip-in", "deflected", "wrap-around"]


def features(s: pd.DataFrame) -> np.ndarray:
    x = s.x.abs().fillna(60).to_numpy(float)
    y = s.y.fillna(0).to_numpy(float)
    dx = 89.0 - x
    dist = np.hypot(dx, y)
    ang = np.degrees(np.arctan2(np.abs(y), dx))
    cols = [np.ones(len(s)), np.log1p(dist), dist / 10, ang / 45, (ang / 45) ** 2,
            s.rebound.astype(float).to_numpy(), (dx < 0).astype(float)]
    st = s.shot_type.fillna("").str.lower()
    cols += [(st == t).astype(float).to_numpy() for t in SHOT_TYPES]
    for k in ("pp", "pk", "other"):
        cols.append((s.strength == k).astype(float).to_numpy())
    return np.column_stack(cols)


class XGModel:
    def __init__(self, l2: float = 1.0):
        self.l2, self.w, self.en_rate = l2, None, 0.8

    def fit(self, shots: pd.DataFrame) -> "XGModel":
        d = shots[shots.unblocked & ~shots.en_target]
        X, yv = features(d), d.goal.to_numpy(float)

        def f(w):
            z = X @ w
            p = 1 / (1 + np.exp(-z))
            ll = -np.sum(yv * z - np.logaddexp(0, z)) + self.l2 * np.sum(w[1:] ** 2)
            g = X.T @ (p - yv) + 2 * self.l2 * np.r_[0, w[1:]]
            return ll, g

        w0 = np.zeros(X.shape[1]); w0[0] = np.log(yv.mean() / (1 - yv.mean()))
        self.w = minimize(f, w0, jac=True, method="L-BFGS-B").x
        en = shots[shots.unblocked & shots.en_target]
        if len(en) > 50:
            self.en_rate = float(en.goal.mean())
        return self

    def predict(self, shots: pd.DataFrame) -> np.ndarray:
        p = 1 / (1 + np.exp(-(features(shots) @ self.w)))
        p = np.where(shots.en_target, self.en_rate, p)
        return np.where(shots.unblocked, p, 0.0)


# ---------------------------------------------------------------- v2: shot context from the shot sequence
def derive(shots: pd.DataFrame, home_of: dict | None = None) -> pd.DataFrame:
    """Context columns from the order of shot attempts within each game (no extra data needed).

    dt_prev       seconds since the previous attempt by either team (capped at 60)
    reb_speed     for rebounds: change in shot angle per second since the previous attempt
                  (a quick cross-crease rebound beats a goalie much more often than a straight one)
    rush          first attempt within 10 s of an attempt by the other team (a transition chance)
    pressure      same-team attempt within 4-15 s that is not a rebound (sustained zone time)
    arena         home team of the game, for the rink scorer-distance correction
    """
    d = shots.copy()
    order = d.sort_values(["game_id", "t"]).index
    d = d.loc[order]
    x = d.x.abs().fillna(60).to_numpy(float)
    y = d.y.fillna(0).to_numpy(float)
    ang = np.degrees(np.arctan2(y, 89.0 - x))          # signed: side of the net matters for the change
    g = d.game_id.to_numpy()
    t = d.t.to_numpy(float)
    team = d.team.to_numpy()
    same_game = np.r_[False, g[1:] == g[:-1]]
    dt = np.where(same_game, t - np.r_[0, t[:-1]], 99.0)
    prev_same = same_game & np.r_[False, team[1:] == team[:-1]]
    d["dt_prev"] = np.clip(dt, 0, 60)
    dang = np.abs(ang - np.r_[0, ang[:-1]])
    d["reb_speed"] = np.where(d.rebound.to_numpy() & prev_same, dang / np.maximum(dt, 1), 0.0)
    d["rush"] = (same_game & ~prev_same & (dt <= 10)).astype(float)
    d["pressure"] = (prev_same & (dt > 4) & (dt <= 15) & ~d.rebound.to_numpy()).astype(float)
    if home_of is not None:
        d["arena"] = d.game_id.map(home_of)
    return d.loc[shots.index]


def arena_offsets(shots: pd.DataFrame, shrink: float = 400.0) -> dict:
    """Recorded-distance bias per rink: how much closer/farther road teams' shots are logged there
    than the same teams' shots in all their road games (shrunk toward 0 with `shrink` shots)."""
    d = shots[shots.unblocked & ~shots.en_target & (shots.is_home == 0) & shots.arena.notna()].copy()
    if d.empty:
        return {}
    d["dist"] = np.hypot(89.0 - d.x.abs().fillna(60), d.y.fillna(0))
    road_mean = d.groupby("team").dist.mean()
    d["resid"] = d.dist - d.team.map(road_mean)
    agg = d.groupby("arena").resid.agg(["sum", "count"])
    return {a: float(r["sum"] / (r["count"] + shrink)) for a, r in agg.iterrows()}


def features2(s: pd.DataFrame, offsets: dict | None = None) -> np.ndarray:
    x = s.x.abs().fillna(60).to_numpy(float)
    y = s.y.fillna(0).to_numpy(float)
    dx = 89.0 - x
    dist = np.hypot(dx, y)
    if offsets and "arena" in s:
        dist = np.clip(dist - s.arena.map(offsets).fillna(0).to_numpy(float), 1.0, None)
    ang = np.degrees(np.arctan2(np.abs(y), dx))
    st = s.shot_type.fillna("").str.lower()
    tipish = st.isin(["tip-in", "deflected"]).to_numpy(float)
    reb = s.rebound.astype(float).to_numpy()
    cols = [np.ones(len(s)), np.log1p(dist), dist / 10, (dist / 10) ** 2 / 10, ang / 45, (ang / 45) ** 2,
            (dist / 30) * (ang / 45), reb, (dx < 0).astype(float),
            np.log1p(s.reb_speed.to_numpy(float)), s.rush.to_numpy(float), s.pressure.to_numpy(float),
            np.log1p(s.dt_prev.to_numpy(float)) / 4, tipish * dist / 30]
    cols += [(st == t).astype(float).to_numpy() for t in SHOT_TYPES]
    for k in ("pp", "pk", "other"):
        cols.append((s.strength == k).astype(float).to_numpy())
    lead = s.lead.fillna(0).to_numpy(float)
    cols += [(lead > 0).astype(float), (lead < 0).astype(float)]
    return np.column_stack(cols)


class XGModel2(XGModel):
    """v2: v1 plus shot-sequence context (rebound angle speed, rush, pressure, time since last
    attempt), a finer distance/angle shape and a per-rink recorded-distance correction."""

    def fit(self, shots: pd.DataFrame) -> "XGModel2":
        self.offsets = arena_offsets(shots) if "arena" in shots else {}
        d = shots[shots.unblocked & ~shots.en_target]
        X, yv = features2(d, self.offsets), d.goal.to_numpy(float)

        def f(w):
            z = X @ w
            p = 1 / (1 + np.exp(-z))
            ll = -np.sum(yv * z - np.logaddexp(0, z)) + self.l2 * np.sum(w[1:] ** 2)
            g = X.T @ (p - yv) + 2 * self.l2 * np.r_[0, w[1:]]
            return ll, g

        w0 = np.zeros(X.shape[1]); w0[0] = np.log(yv.mean() / (1 - yv.mean()))
        self.w = minimize(f, w0, jac=True, method="L-BFGS-B").x
        en = shots[shots.unblocked & shots.en_target]
        if len(en) > 50:
            self.en_rate = float(en.goal.mean())
        return self

    def predict(self, shots: pd.DataFrame) -> np.ndarray:
        p = 1 / (1 + np.exp(-(features2(shots, self.offsets) @ self.w)))
        p = np.where(shots.en_target, self.en_rate, p)
        return np.where(shots.unblocked, p, 0.0)


XG_VERSION = 1   # 2 = shot-context model; switched on after the walk-forward comparison


def score_by_season(shots: pd.DataFrame, home_of: dict | None = None,
                    version: int | None = None) -> tuple[pd.Series, list[str]]:
    """xG for every shot, each season scored by the previous season's model."""
    version = XG_VERSION if version is None else version
    notes, out = [], pd.Series(0.0, index=shots.index)
    if version >= 2:
        shots = derive(shots, home_of)
    cls = XGModel2 if version >= 2 else XGModel
    seasons = sorted(shots.season.unique())
    models = {s: cls().fit(shots[shots.season == s]) for s in seasons}
    for i, s in enumerate(seasons):
        m = models[seasons[i - 1]] if i > 0 else models[s]
        if i == 0:
            notes.append(f"xG for season {s} uses its own fit (no prior season loaded): in-sample")
        sel = shots.season == s
        out[sel] = m.predict(shots[sel])
    return out, notes


def score_venue_coefs(shots: pd.DataFrame) -> pd.DataFrame:
    """Score/venue adjustment coefficients for 5v5 xG: 0.5 / (xG share in that state), clipped."""
    d = shots[(shots.strength == "5v5") & shots.unblocked]
    f = d.groupby(["lead", "is_home"]).xg.sum()
    rows = []
    for (lead, home), xf in f.items():
        xa = f.get((-lead, 1 - home), np.nan)
        share = xf / (xf + xa) if xa == xa and xf + xa > 0 else 0.5
        rows.append(dict(lead=lead, is_home=home, coef=float(np.clip(0.5 / share, 0.8, 1.25))))
    return pd.DataFrame(rows)
