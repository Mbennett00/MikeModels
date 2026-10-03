"""Systematic-bias detection.

A bias is reported only when it is statistically meaningful:
  - the segment has at least `min_segment` graded predictions,
  - the mean error is significant (two-sided t-test on the errors), and
  - it survives Benjamini-Hochberg false-discovery control across every segment tested at once
    (so testing 60 segments doesn't produce 3 "biases" by chance).
A single bad game can't trigger anything: it moves a 25+ game mean by a few percent at most.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def _test(e: pd.Series) -> tuple[float, float]:
    e = e.dropna().astype(float)
    if len(e) < 3 or e.std(ddof=1) == 0:
        return 0.0, 1.0
    t = e.mean() / (e.std(ddof=1) / np.sqrt(len(e)))
    return float(t), float(2 * stats.t.sf(abs(t), len(e) - 1))


def segments(d: pd.DataFrame, label: str, unit: str, extra: dict | None = None) -> list[dict]:
    """Candidate segments for one projection type: overall, home / road, each team (as the team projected and
    as the opponent faced), recent-form buckets, confidence buckets, early season, player (if any)."""
    out = []

    def add(name, mask, what):
        x = d[mask]
        if len(x):
            out.append(dict(segment=name, what=what, e=x.error, label=label, unit=unit))
    add("all", d.index == d.index, f"{label}")
    if "is_home" in d and d.is_home.notna().any():
        add("home", d.is_home == 1, f"{label}, home teams")
        add("road", d.is_home == 0, f"{label}, road teams")
    if "team" in d and d.team.notna().any():
        for t in d.team.dropna().unique():
            add(f"team:{t}", d.team == t, f"{label} for {t}")
        for t in d.opponent.dropna().unique():
            add(f"opp:{t}", d.opponent == t, f"{label} against {t}")
    if "form_bucket" in d:
        for b in d.form_bucket.dropna().unique():
            add(f"form:{b}", d.form_bucket == b, f"{label} when recent form is {b}")
    if "conf_bucket" in d:
        for b in d.conf_bucket.dropna().unique():
            add(f"conf:{b}", d.conf_bucket == b, f"{label} at {b} confidence")
    if "early" in d:
        add("early", d.early == 1, f"{label} early in the season (small samples)")
    if "subject_type" in d and (d.subject_type == "player").any():
        for pid, x in d.groupby("subject_id"):
            if len(x) >= 25:
                add(f"player:{pid}", d.subject_id == pid, f"{label} for {x.subject_name.iloc[-1]}")
    for k, v in (extra or {}).items():
        add(k, v[0], v[1])
    return out


def detect(cands: list[dict], min_segment: int = 25, fdr: float = 0.05) -> list[dict]:
    rows = []
    for c in cands:
        e = c["e"].dropna()
        if len(e) < min_segment:
            continue
        t, p = _test(e)
        rows.append(dict(segment=c["segment"], what=c["what"], unit=c["unit"], n=int(len(e)), bias=float(e.mean()),
                         t=t, p=p, mae=float(e.abs().mean())))
    if not rows:
        return []
    # Benjamini-Hochberg
    rows.sort(key=lambda r: r["p"])
    m = len(rows)
    cutoff = 0
    for i, r in enumerate(rows, 1):
        if r["p"] <= fdr * i / m:
            cutoff = i
    sig = rows[:cutoff]
    for r in sig:
        r["text"] = describe(r)
    return sorted(sig, key=lambda r: -abs(r["bias"]) * min(abs(r["t"]), 6))


def describe(r: dict) -> str:
    verb = "overestimating" if r["bias"] > 0 else "underestimating"
    return f"Model is {verb} {r['what']} by {abs(r['bias']):.2f} {r['unit']} ({r['n']} predictions, p={r['p']:.3f})"


def confidence_check(cal: dict, min_n: int = 25) -> list[dict]:
    """Overconfidence: favourites priced at X% winning significantly less often (binomial test per bucket)."""
    out = []
    for b in cal.get("buckets", []):
        if b["n"] < min_n:
            continue
        k = round(b["actual"] * b["n"])
        p = stats.binomtest(k, b["n"], b["predicted"]).pvalue
        if p < 0.05:
            gap = b["predicted"] - b["actual"]
            out.append(dict(segment=f"calib:{b['bucket']}", n=b["n"], bias=gap, p=float(p), unit="win-prob pts",
                            text=f"Model confidence is too {'aggressive' if gap > 0 else 'cautious'} at "
                                 f"{b['bucket']} win probability: favourites won {100 * b['actual']:.0f}% vs "
                                 f"{100 * b['predicted']:.0f}% priced ({b['n']} games, p={p:.3f})"))
    return out
