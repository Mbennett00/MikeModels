"""Model Health payload for the web pages: accuracy by window and segment, biggest biases, chart series,
the latest recalibration and the version history. Everything is computed from the prediction database."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import bias as B
from . import db, metrics as M
from .config import CalibConfig
from .engine import SPECS, prep

LABELS = {"team_goals": ("Team goals", "goals"), "game_total": ("Game total", "goals"),
          "player_sog": ("Player shots", "shots"), "player_goals": ("Player goals", "goals"),
          "team_points": ("Team points", "pts"), "game_total_pts": ("Game total", "pts"),
          "player_rec_yds": ("Receiving yards", "yds"), "player_rush_yds": ("Rushing yards", "yds"),
          "player_pass_yds": ("Passing yards", "yds"), "player_rec": ("Receptions", "rec"),
          "player_td": ("Anytime TD (prob)", "prob")}
WINPROB = "home_win_prob"


def _r(x, nd=3):
    try:
        x = float(x)
        return None if not np.isfinite(x) else round(x, nd)
    except (TypeError, ValueError):
        return None


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items() if k != "e"}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    if isinstance(o, (float, np.floating)):
        return _r(o, 4)
    if isinstance(o, (np.integer,)):
        return int(o)
    return o


def build(site: str, sport: str, season: int | None = None, cfg: CalibConfig | None = None) -> dict:
    cfg = cfg or CalibConfig.from_env()
    spec = SPECS[sport]
    out = dict(sport=sport, counts=db.counts(site).get(sport, {}), active=None, types=[], biases=[], charts={},
               versions=[], last=None, config=dict(tiers=cfg.tiers, blend=cfg.blend, min_obs=cfg.min_obs,
                                                 min_segment=cfg.min_segment, fdr=cfg.fdr))
    act = db.active(site, sport)
    out["active"] = dict(version=act.get("version", "1.0"), status=act.get("status"), created_at=act.get("created_at"))
    vs = db.versions(site, sport)
    out["versions"] = [dict(version=v["version"], status=v["status"], created_at=v["created_at"], n=v["n_obs"],
                            reason=v["reason"], before=v.get("metrics_before"), after=v.get("metrics_after"))
                       for v in vs][-12:][::-1]
    attempts = [v for v in vs if v["status"] in ("applied", "rejected", "insufficient")]
    out["last"] = attempts[-1]["summary"] if attempts else None
    every = db.graded(site, sport)
    if every.empty:
        return _clean(out)
    season = season or int(every.season.max())
    biases = []
    for ptype, d in every.groupby("projection_type"):
        if ptype == WINPROB:
            continue
        label, unit = LABELS.get(ptype, (ptype, ""))
        t = dict(ptype=ptype, label=label, unit=unit, windows=M.windows(d, season))
        if ptype == spec.ptype:
            dd, _ = prep(d, spec)
            t["home_away"] = M.by(dd.assign(ha=np.where(dd.is_home == 1, "home", "road")), "ha")
            t["teams"] = M.by(dd, "team", 5)
            t["form"] = M.by(dd, "form_bucket", 5)
            t["confidence"] = M.by(dd[dd.conf_bucket.notna()], "conf_bucket", 5) if dd.conf_bucket.notna().any() else []
            biases += B.detect(B.segments(dd, label.lower(), unit), cfg.min_segment, cfg.fdr)
            out["charts"]["pred_vs_actual"] = M.pred_vs_actual(dd)
            out["charts"]["rolling"] = M.rolling(dd)
            ts = dd.assign(month=dd.game_date.dt.strftime("%Y-%m")).groupby("month").error
            out["charts"]["error_by_month"] = [dict(month=k, bias=_r(v.mean()), mae=_r(v.abs().mean()), n=int(len(v)))
                                               for k, v in ts]
        elif d.subject_type.eq("player").any():
            t["players"] = [r for r in M.by(d.assign(who=d.subject_name), "who", 8)][:12]
            biases += B.detect(B.segments(d.assign(team=None, opponent=None), label.lower(), unit),
                               cfg.min_segment, cfg.fdr)[:3]
        else:
            biases += B.detect([dict(segment=f"{ptype}:all", what=label.lower() + " projections", e=d.error,
                                     label=label, unit=unit)], cfg.min_segment, cfg.fdr)
        out["types"].append(t)
    wp = every[every.projection_type == WINPROB]
    if len(wp):
        cal = M.prob_calibration(wp.projection, wp.actual)
        out["calibration"] = cal
        out["charts"]["confidence"] = cal.get("buckets", [])
        biases += B.confidence_check(cal, cfg.min_segment)
    seen, top = set(), []
    for b in sorted(biases, key=lambda r: -abs(r["bias"]) * min(abs(r.get("t", 3)), 6)):
        if b["segment"] in seen:
            continue
        seen.add(b["segment"])
        top.append(b)
    out["biases"] = top[:8]
    if out["last"] and out["last"].get("backtest"):
        out["charts"]["orig_vs_recal"] = [dict(window=w, original=_r(v["published"].get("mae")),
                                               recalibrated=_r(v["recalibrated"].get("mae")), n=v["n"])
                                          for w, v in out["last"]["backtest"].items()]
    return _clean(out)
