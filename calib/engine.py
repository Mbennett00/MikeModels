"""Recalibration engine.

What it adjusts: each projection is the original model's number plus a small, shrunk correction learned from
how the model has actually missed:

    residual = actual - original
    residual ~ a + sum_c b_c * x_c          (weighted ridge regression on standardised components)

The components x_c are the model's own inputs at prediction time (attack, opponent defence, goaltending / QB,
home edge, rest, injuries, weather ...) plus recent form (the team's average miss over its previous 10 graded
games, computed only from games before the one being predicted). A component whose b_c is significantly the
same sign as the model's own weight on it is under-weighted; the opposite sign means over-weighted. b_c is kept
only when |t| >= coef_t; the intercept is the overall bias and is also kept only when significant.

Protection against overfitting:
  * sample-size shrinkage: the fitted correction is multiplied by the tier for the sample (config.tiers),
    so < 25 graded predictions change nothing, 25-50 very little, 100+ more;
  * a blend with the original (never a full replacement), and a cap on how far a projection can move;
  * older predictions count less but a whole year still counts half (no chasing short streaks);
  * walk-forward backtest: the whole procedure is refit week by week using only predictions graded before each
    week, and judged on the weeks after. The new calibration is applied only if it beats the published model on
    the full walk-forward sample and isn't worse over the most recent 100 predictions; otherwise it is rejected.
Every attempt is stored as a model version (applied, rejected or insufficient); nothing is overwritten.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import db
from .config import CalibConfig
from .metrics import summary


@dataclass
class Spec:
    sport: str
    ptype: str                  # projection type that is recalibrated (team-level count / points)
    unit: str
    features: dict              # name -> (label, function(inputs dict, row) -> float)
    model_has: set              # features the original model uses (others are "added" adjustments)


def _log(v):
    try:
        v = float(v)
        return float(np.log(v)) if v > 0 else np.nan
    except (TypeError, ValueError):
        return np.nan


def _num(v):
    try:
        v = float(v)
        return v if np.isfinite(v) else np.nan
    except (TypeError, ValueError):
        return np.nan


SPECS = {
    "nhl": Spec("nhl", "team_goals", "goals", {
        "off": ("attack (season ratings)", lambda i, r: _log(i.get("off"))),
        "def_opp": ("opponent defence", lambda i, r: _log(i.get("def_opp"))),
        "goalie_opp": ("goaltending", lambda i, r: _log(i.get("goalie_opp"))),
        "pp_pk": ("special teams", lambda i, r: _log(i.get("pp_pk"))),
        "pace": ("pace", lambda i, r: _log(i.get("pace"))),
        "rest": ("rest / back-to-back", lambda i, r: _log(i.get("rest"))),
        "home": ("home-ice", lambda i, r: _num(r.get("is_home"))),
        "form": ("recent form", lambda i, r: _num(r.get("form"))),
    }, {"off", "def_opp", "goalie_opp", "pp_pk", "pace", "rest", "home"}),
    "nfl": Spec("nfl", "team_points", "points", {
        "off": ("offensive efficiency (EPA/play)", lambda i, r: _num(i.get("off"))),
        "def_opp": ("opponent defensive efficiency", lambda i, r: _num(i.get("def_opp"))),
        "pass_off": ("passing efficiency (EPA/dropback)", lambda i, r: _num(i.get("pass_off"))),
        "home": ("home-field", lambda i, r: _num(r.get("is_home"))),
        "qb": ("QB adjustment", lambda i, r: _num(i.get("qb"))),
        "inj": ("injuries (own team)", lambda i, r: _num(i.get("inj"))),
        "inj_opp": ("injuries (opponent)", lambda i, r: _num(i.get("inj_opp"))),
        "weather": ("weather", lambda i, r: _num(i.get("weather"))),
        "rest": ("rest days vs opponent", lambda i, r: _num(i.get("rest_diff"))),
        "form": ("recent form", lambda i, r: _num(r.get("form"))),
    }, {"off", "def_opp", "pass_off", "home", "qb", "inj", "inj_opp", "weather"}),
}


# ---------- data prep (only information available at prediction time) ----------

def add_form(d: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Recent form: the team's mean (actual - original) over its previous n graded games, strictly earlier dates."""
    d = d.sort_values(["game_date", "id"]).copy()
    d["resid"] = d.actual - d.original
    form = pd.Series(np.nan, index=d.index)
    for t, x in d.groupby("team"):
        # shift(1) on per-date means so same-day rows never see each other
        by_date = x.groupby("game_date").resid.mean()
        prev = by_date.shift(1).rolling(n, min_periods=3).mean()
        form.loc[x.index] = x.game_date.map(prev).to_numpy()
    d["form"] = form.fillna(0.0)
    sd = d.resid.std() or 1.0
    d["form_bucket"] = np.where(d.form > 0.5 * sd / np.sqrt(n) * 3, "hot", np.where(d.form < -0.5 * sd / np.sqrt(n) * 3, "cold", "neutral"))
    return d


def prep(d: pd.DataFrame, spec: Spec) -> tuple[pd.DataFrame, list]:
    d = d.copy()
    d["original"] = d.original.fillna(d.projection)
    d = add_form(d)
    for f, (_, fn) in spec.features.items():
        d[f"x_{f}"] = [fn(i or {}, r) for i, r in zip(d.inputs, d.to_dict("records"))]
    usable = [f for f in spec.features if d[f"x_{f}"].notna().mean() >= 0.8 and d[f"x_{f}"].std() > 1e-9]
    for f in usable:
        d[f"x_{f}"] = d[f"x_{f}"].fillna(d[f"x_{f}"].median())
    if "confidence" in d:
        c = d.confidence
        d["conf_bucket"] = np.where(c >= 0.65, "high (65%+)", np.where(c >= 0.55, "medium (55-65%)", "low (<55%)"))
        d.loc[c.isna(), "conf_bucket"] = None
    start = d.groupby("season").game_date.transform("min") if "season" in d else d.game_date.min()
    d["early"] = ((d.game_date - start).dt.days < 21).astype(int)
    return d, usable


# ---------- fit / apply ----------

def fit(d: pd.DataFrame, feats: list, cfg: CalibConfig, blend: float, asof=None) -> dict:
    """Shrunk residual model on graded rows d (all strictly before `asof` when used in the backtest)."""
    n = len(d)
    k = cfg.shrink(n)
    params = dict(features=[], coef=[], mean=[], sd=[], intercept=0.0, shrink=k, blend=blend, n=n,
                  cap=cfg.max_rel_change)
    if n < 25 or k == 0:
        return params
    asof = pd.Timestamp(asof) if asof is not None else d.game_date.max() + pd.Timedelta(days=1)
    w = 0.5 ** ((asof - d.game_date).dt.days.clip(lower=0) / cfg.half_life_days)
    r = (d.actual - d.original).to_numpy(float)
    keep = list(feats)
    for _ in range(3):   # drop components that aren't significant, refit
        X = d[[f"x_{f}" for f in keep]].to_numpy(float) if keep else np.zeros((n, 0))
        mu, sd = X.mean(0) if keep else np.array([]), X.std(0) if keep else np.array([])
        sd = np.where(sd > 0, sd, 1.0)
        Z = np.c_[np.ones(n), (X - mu) / sd] if keep else np.ones((n, 1))
        W = w.to_numpy()
        P = np.eye(Z.shape[1]) * cfg.ridge
        P[0, 0] = 0
        A = Z.T @ (Z * W[:, None]) + P
        beta = np.linalg.solve(A, Z.T @ (W * r))
        res = r - Z @ beta
        Ai = np.linalg.inv(A)
        cov = Ai @ (Z.T @ (Z * (W ** 2 * res ** 2)[:, None])) @ Ai      # heteroskedasticity-robust (sandwich)
        neff = W.sum() ** 2 / (W ** 2).sum()
        cov *= neff / max(neff - Z.shape[1], 1)
        se = np.sqrt(np.clip(np.diag(cov), 1e-12, None))
        t = beta / se
        sig = [f for f, tv in zip(keep, t[1:]) if abs(tv) >= cfg.coef_t]
        if sig == keep:
            break
        keep = sig
    a = beta[0] if abs(t[0]) >= cfg.coef_t else 0.0
    if keep:
        b_raw = beta[1:] / sd                       # back to raw units
        a_raw = a - float((beta[1:] * mu / sd).sum())
    else:
        b_raw, a_raw = np.array([]), a
    params.update(features=keep, coef=[float(x) for x in b_raw], mean=[float(x) for x in mu] if keep else [],
                  sd=[float(x) for x in sd] if keep else [], intercept=float(a_raw),
                  t={f: float(tv) for f, tv in zip(["intercept"] + keep, t)})
    return params


def apply(params: dict, x: dict, original: float) -> float:
    """Calibrated projection for one row: original + blend x shrink x correction, capped."""
    if not params or not params.get("shrink") or original is None or not np.isfinite(original):
        return original
    corr = params.get("intercept", 0.0) + sum(c * float(x.get(f, m)) for f, c, m in
                                               zip(params["features"], params["coef"], params.get("mean", [0] * 99)))
    corr *= params["shrink"] * params["blend"]
    cap = params.get("cap", 0.15) * abs(original)
    return float(original + np.clip(corr, -cap, cap))


def apply_frame(params: dict, d: pd.DataFrame) -> np.ndarray:
    feats = params.get("features", [])
    xs = d[[f"x_{f}" for f in feats]].to_dict("records") if feats else [{}] * len(d)
    xs = [{k[2:]: v for k, v in x.items()} for x in xs]
    return np.array([apply(params, x, o) for x, o in zip(xs, d.original)])


# ---------- walk-forward backtest ----------

def walk_forward(d: pd.DataFrame, feats: list, cfg: CalibConfig, blend: float) -> pd.Series:
    """Calibrated projection for each row using only rows graded before its week (NaN in the burn-in)."""
    out = pd.Series(np.nan, index=d.index)
    dates = d.game_date
    start = dates.iloc[min(cfg.wf_min_train, len(d) - 1)] if len(d) > cfg.wf_min_train else None
    if start is None:
        return out
    t = start
    end = dates.max()
    while t <= end:
        nxt = t + pd.Timedelta(days=cfg.wf_chunk_days)
        test = d[(dates >= t) & (dates < nxt)]
        train = d[dates < t]
        if len(test) and len(train) >= cfg.wf_min_train:
            p = fit(train, feats, cfg, blend, asof=t)
            out.loc[test.index] = apply_frame(p, test)
        t = nxt
    return out


def compare(d: pd.DataFrame, cal: pd.Series) -> dict:
    """Published / original vs recalibrated on the walk-forward holdout: last 25, 50, 100 and all."""
    h = d[cal.notna()].copy()
    h["cal"] = cal[cal.notna()]
    out = {}
    for name, n in (("last25", 25), ("last50", 50), ("last100", 100), ("all", None)):
        x = h if n is None else h.tail(n)
        out[name] = dict(n=int(len(x)),
                         original=summary(x.original - x.actual, x.actual),
                         published=summary(x.projection - x.actual, x.actual),
                         recalibrated=summary(x.cal - x.actual, x.actual))
    return out


# ---------- the recalibration run ----------

def implied_weights(d: pd.DataFrame, feats: list) -> dict:
    """The original model's own effect per unit of each component (simple slope of the projection on it; stable
    even when components move together, unlike a joint regression)."""
    out = {}
    for f in feats:
        x = d[f"x_{f}"].to_numpy(float)
        v = x.var()
        out[f] = float(np.cov(x, d.original.to_numpy(float))[0, 1] / v) if v > 0 else 0.0
    return out


def describe_changes(params: dict, spec: Spec, implied: dict, unit: str, d: pd.DataFrame | None = None) -> list[str]:
    """Plain-language changes. Each component: the correction per typical (1 SD) swing, and versus the model's own
    effect for the same swing when the model already uses it."""
    out = []
    eff = params.get("shrink", 0) * params.get("blend", 0)
    for f, c, sd in zip(params["features"], params["coef"], params.get("sd", [1.0] * len(params["features"]))):
        label = spec.features[f][0]
        per_sd = eff * c * sd
        if f in spec.model_has and abs(implied.get(f, 0)) * sd > 1e-6:
            rel = eff * c / implied[f]
            rel = float(np.clip(rel, -0.5, 0.5))
            out.append(f"{'Increased' if rel > 0 else 'Reduced'} {label} weighting ({100 * rel:+.0f}%, "
                       f"{per_sd:+.2f} {unit} per typical swing)")
        else:
            out.append(f"Added a {label} adjustment ({per_sd:+.2f} {unit} per typical swing)")
    if params.get("intercept") is not None and (params["features"] or params["intercept"]):
        avg = eff * (params["intercept"] + sum(c * m for c, m in zip(params["coef"], params.get("mean", []))))
        if abs(avg) >= 0.005:
            out.append(f"Average level shifted {avg:+.2f} {unit}")
    return out or ["No component met the significance bar: projections unchanged"]


def weight_changes(params: dict | None, sport: str, version: str) -> dict | None:
    """The calibration layer's live corrections for the ⚙️ sheet: per component, the shift per typical swing."""
    if not params or not params.get("features"):
        return None
    spec = SPECS[sport]
    eff = params.get("shrink", 0) * params.get("blend", 0)
    items = []
    for f, c, sd in zip(params["features"], params["coef"], params.get("sd", [1.0] * len(params["features"]))):
        lab = spec.features[f][0] if f in spec.features else f
        items.append(dict(name=lab[:1].upper() + lab[1:], signed=round(eff * c * sd, 3),
                          swing=round(abs(eff * c * sd), 3)))
    return dict(version=version, items=sorted(items, key=lambda r: -r["swing"]))


def recalibrate(site: str, sport: str, cfg: CalibConfig | None = None, log=print) -> dict:
    """Pull graded predictions, find meaningful biases, test adjustments walk-forward, and apply only if better.
    Always records the attempt as a model version. Returns a summary for the page."""
    from . import bias as B
    cfg = cfg or CalibConfig.from_env()
    spec = SPECS[sport]
    cur = db.active(site, sport)
    ver = db.next_version(site, sport)
    raw = db.graded(site, sport, spec.ptype)
    n = len(raw)
    base = dict(sport=sport, from_version=cur.get("version", "1.0"), version=ver, n=n,
                created_at=db.now_iso(), ptype=spec.ptype, unit=spec.unit)
    if n < cfg.min_obs:
        reason = f"only {n} graded {spec.ptype.replace('_', ' ')} predictions (need {cfg.min_obs})"
        db.add_version(site, sport, ver, "insufficient", cur.get("params") or {}, cur.get("params") or {}, reason, n,
                       None, None, dict(base, status="insufficient", reason=reason), cur.get("version"))
        log(f"{sport}: recalibration skipped: {reason}")
        return dict(base, status="insufficient", reason=reason)
    d, feats = prep(raw, spec)
    biases = B.detect(B.segments(d, spec.ptype.replace("_", " "), spec.unit), cfg.min_segment, cfg.fdr)
    # candidates: each blend; the best on the full walk-forward holdout is the proposal
    trials = []
    for bl in cfg.candidates:
        cal = walk_forward(d, feats, cfg, bl)
        cmpr = compare(d, cal)
        trials.append((cmpr["all"]["recalibrated"].get("mae", 9e9), bl, cal, cmpr))
    trials.sort(key=lambda t: t[0])
    _, blend, cal, cmpr = trials[0]
    pub_all = cmpr["all"]["published"].get("mae")
    new_all = cmpr["all"]["recalibrated"].get("mae")
    pub_100 = cmpr["last100"]["published"].get("mae")
    new_100 = cmpr["last100"]["recalibrated"].get("mae")
    params = fit(d, feats, cfg, blend)
    implied = implied_weights(d, feats)
    changes = describe_changes(params, spec, implied, spec.unit, d)
    ok = (pub_all is not None and new_all is not None and cmpr["all"]["n"] >= 25
          and new_all <= pub_all * (1 - cfg.min_improvement)
          and (new_100 is None or pub_100 is None or new_100 <= pub_100 * (1 + cfg.recent_tolerance))
          and (params["features"] or params["intercept"]))
    before = cmpr["all"]["published"]
    after = cmpr["all"]["recalibrated"]
    if ok:
        status, reason = "applied", (f"walk-forward MAE {pub_all:.3f} -> {new_all:.3f} on {cmpr['all']['n']} held-out "
                                     f"predictions; last 100: {pub_100:.3f} -> {new_100:.3f}")
    else:
        status = "rejected"
        if not (params["features"] or params["intercept"]):
            reason = "no statistically meaningful adjustment found"
        elif new_all is not None and pub_all is not None and new_all > pub_all * (1 - cfg.min_improvement):
            reason = f"did not improve the walk-forward backtest (MAE {pub_all:.3f} -> {new_all:.3f})"
        else:
            reason = f"worse over the last 100 predictions (MAE {pub_100:.3f} -> {new_100:.3f})"
    summ = dict(base, status=status, reason=reason, blend=blend, changes=changes, biases=biases[:8],
                backtest=cmpr, trials=[dict(blend=b, mae=m) for m, b, _, _ in trials],
                before=before, after=after,
                to_version=ver if status == "applied" else cur.get("version", "1.0"))
    db.add_version(site, sport, ver, status, params if status == "applied" else (cur.get("params") or {}),
                   cur.get("params") or {}, reason, n, before, after, summ, cur.get("version"))
    log(f"{sport}: recalibration v{ver} {status}: {reason}")
    return summ


def ensure_baseline(site: str, sport: str):
    if not db.versions(site, sport):
        db.add_version(site, sport, "1.0", "baseline", {}, {}, "original model (no calibration)", 0, None, None,
                       dict(sport=sport, version="1.0", status="baseline"), None)


# ---------- live use ----------

def team_form(site: str, sport: str, n: int = 10) -> dict:
    """Each team's recent form (mean actual - original over its last n graded games), for live projections."""
    spec = SPECS[sport]
    d = db.graded(site, sport, spec.ptype)
    if d.empty:
        return {}
    d["original"] = d.original.fillna(d.projection)
    d["resid"] = d.actual - d.original
    out = {}
    for t, x in d.groupby("team"):
        x = x.groupby("game_date").resid.mean().tail(n)
        if len(x) >= 3:
            out[t] = float(x.mean())
    return out


def live_features(sport: str, inputs: dict, is_home, form: float) -> dict:
    spec = SPECS[sport]
    row = dict(is_home=is_home, form=form)
    return {f: fn(inputs or {}, row) for f, (_, fn) in spec.features.items()}


class Live:
    """The active calibration for a sport, ready to apply to new projections."""
    def __init__(self, site: str, sport: str):
        self.sport = sport
        v = db.active(site, sport)
        self.version = v.get("version", "1.0")
        self.params = v.get("params") or {}
        self.form = team_form(site, sport) if self.params.get("features") and "form" in self.params["features"] else {}

    def __call__(self, original: float, inputs: dict, team: str, is_home) -> float:
        if not self.params:
            return original
        x = live_features(self.sport, inputs, is_home, self.form.get(team, 0.0))
        x = {k: v for k, v in x.items() if v is not None and np.isfinite(v)}   # missing -> training average
        return apply(self.params, x, original)
