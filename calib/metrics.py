"""Error metrics over windows and segments. error = projection - actual (positive = the model was too high)."""
from __future__ import annotations

import numpy as np
import pandas as pd

WINDOWS = [("last10", 10), ("last25", 25), ("last50", 50), ("last100", 100), ("season", None), ("all", None)]


def summary(err: pd.Series, actual: pd.Series | None = None) -> dict:
    e = pd.Series(err, dtype=float).dropna()
    if e.empty:
        return dict(n=0)
    out = dict(n=int(len(e)), mae=float(e.abs().mean()), rmse=float(np.sqrt((e ** 2).mean())), bias=float(e.mean()),
               mpe=float(e.mean()))   # mean prediction error = bias (same sign convention), kept for clarity
    if actual is not None:
        a = pd.Series(actual, dtype=float).loc[e.index]
        nz = a.abs() >= 1   # percentage error only where the actual isn't ~0
        if nz.sum() >= 5:
            out["mape"] = float((e[nz].abs() / a[nz].abs()).mean())
    if len(e) >= 3:
        out["se"] = float(e.std(ddof=1) / np.sqrt(len(e)))
    return out


def windows(d: pd.DataFrame, season: int | None = None) -> dict:
    """{last10, last25, last50, last100, season, all}: summary on the most recent n graded predictions."""
    out = {}
    for name, n in WINDOWS:
        if name == "season":
            x = d[d.season == season] if season is not None and "season" in d else d.iloc[0:0]
        elif n is None:
            x = d
        else:
            x = d.tail(n)
        out[name] = summary(x.error, x.actual)
    return out


def by(d: pd.DataFrame, col: str, min_n: int = 1) -> list[dict]:
    rows = []
    for k, x in d.groupby(col, dropna=True):
        s = summary(x.error, x.actual)
        if s["n"] >= min_n:
            rows.append(dict(key=str(k), **s))
    return sorted(rows, key=lambda r: -r["n"])


def prob_calibration(p: pd.Series, y: pd.Series, bins=(0.5, 0.55, 0.6, 0.65, 0.7, 0.8, 1.0)) -> dict:
    """Confidence vs reality for win probabilities: buckets of the favourite's probability, Brier score and
    expected calibration error. p and y are for the home side; buckets use the favourite (max(p, 1-p))."""
    p, y = pd.Series(p, dtype=float), pd.Series(y, dtype=float)
    ok = p.notna() & y.notna()
    p, y = p[ok], y[ok]
    if p.empty:
        return dict(n=0)
    fav = np.where(p >= 0.5, p, 1 - p)
    hit = np.where(p >= 0.5, y, 1 - y)
    cut = pd.cut(fav, list(bins), include_lowest=True)
    rows = []
    for b, idx in pd.Series(range(len(fav))).groupby(cut, observed=True):
        i = idx.to_numpy()
        rows.append(dict(bucket=f"{b.left:.2f}-{b.right:.2f}", n=int(len(i)), predicted=float(fav[i].mean()),
                         actual=float(hit[i].mean())))
    ece = sum(r["n"] * abs(r["predicted"] - r["actual"]) for r in rows) / max(len(fav), 1)
    return dict(n=int(len(p)), brier=float(((p - y) ** 2).mean()), ece=float(ece), buckets=rows)


def rolling(d: pd.DataFrame, n: int = 50, points: int = 60) -> list[dict]:
    """Rolling MAE and bias over the last n predictions, sampled to at most `points` for the chart."""
    if len(d) < 5:
        return []
    e = d.error.astype(float)
    r = pd.DataFrame(dict(date=d.game_date.dt.strftime("%Y-%m-%d"), mae=e.abs().rolling(n, min_periods=min(n, 10)).mean(),
                          bias=e.rolling(n, min_periods=min(n, 10)).mean())).dropna()
    if r.empty:
        return []
    idx = np.unique(np.linspace(0, len(r) - 1, min(points, len(r))).astype(int))
    return [dict(date=x.date, mae=round(float(x.mae), 3), bias=round(float(x.bias), 3)) for x in r.iloc[idx].itertuples()]


def pred_vs_actual(d: pd.DataFrame, bins: int = 8) -> list[dict]:
    """Binned predicted vs actual (mean actual in each band of projections)."""
    if len(d) < 20:
        return []
    q = pd.qcut(d.projection, bins, duplicates="drop")
    g = d.groupby(q, observed=True).agg(pred=("projection", "mean"), actual=("actual", "mean"), n=("actual", "size"))
    return [dict(pred=round(float(r.pred), 3), actual=round(float(r.actual), 3), n=int(r.n)) for r in g.itertuples()]
