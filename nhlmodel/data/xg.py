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


def score_by_season(shots: pd.DataFrame) -> tuple[pd.Series, list[str]]:
    """xG for every shot, each season scored by the previous season's model."""
    notes, out = [], pd.Series(0.0, index=shots.index)
    seasons = sorted(shots.season.unique())
    models = {s: XGModel().fit(shots[shots.season == s]) for s in seasons}
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
