"""Grid search of shrinkage constants (k, m), decay half-life and a few team knobs.

Objective: out-of-sample log loss from the walk-forward on the *tuning window*
(earlier dates). Edge thresholds are tuned afterwards on the same window from
CLV, and everything is reported on a later *holdout window* that tuning never saw.

A full Cartesian grid is too expensive (every point is a full walk-forward), so
this does coordinate descent: each parameter is swept over its grid with the
others held at their current best, for ``passes`` passes. Snapshots are cached
per (date, half-life) so only half-life changes rebuild them.
"""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd

from .backtest import walk_forward
from .config import ModelConfig
from .validation import CANONICAL, logloss

GRID = {
    "half_life_games": [15.0, 25.0, 40.0],
    "k_ixg_5v5": [200.0, 400.0, 800.0],
    "k_ixg_pp": [75.0, 150.0, 300.0],
    "m_finish": [15.0, 30.0, 60.0],
    "k_sog_5v5": [125.0, 250.0, 500.0],
    "k_sog_pp": [50.0, 100.0, 200.0],
    "k_ast_5v5": [300.0, 600.0, 1200.0],
    "k_ast_pp": [125.0, 250.0, 500.0],
    "sog_script_gamma": [0.0, 0.1, 0.2],
    "k_team_5v5": [750.0, 1500.0, 3000.0],
    "k_goalie_xga": [30.0, 60.0, 120.0],
    "pace_exponent": [0.0, 0.5],
}

# which markets' log loss each parameter is judged on
TARGET = {
    "k_ixg_5v5": ["goals"], "k_ixg_pp": ["goals"], "m_finish": ["goals"],
    "k_sog_5v5": ["sog"], "k_sog_pp": ["sog"], "sog_script_gamma": ["sog"],
    "k_ast_5v5": ["assists", "points"], "k_ast_pp": ["assists", "points"],
    "k_team_5v5": ["moneyline", "total", "puckline"], "k_goalie_xga": ["moneyline", "total", "puckline"],
    "pace_exponent": ["total"],
    "half_life_games": ["goals", "sog", "assists", "points", "moneyline", "total"],
}


def objective(bt: dict, markets: list[str]) -> float:
    parts = []
    for df in (bt["game_markets"], bt["player_markets"]):
        if df is None or df.empty:
            continue
        for m in markets:
            d = df[(df.market == m) & df.selection.isin(CANONICAL[m]) & df.y.notna()]
            if len(d):
                parts.append(logloss(d.p_model, d.y))
    return float(np.mean(parts)) if parts else float("inf")


def coordinate_search(tables, cfg: ModelConfig, start, end, grid=GRID, passes: int = 1,
                      date_stride: int = 2, verbose: bool = True):
    cache: dict = {}
    log = []
    best = cfg
    evals: dict = {}

    def run(c: ModelConfig, params):
        key = tuple(sorted((p, getattr(c, p)) for p in grid))
        if key not in evals:
            t = time.time()
            evals[key] = walk_forward(tables, c, start, end, date_stride=date_stride, snap_cache=cache)
            if verbose:
                print(f"    eval {len(evals)} ({time.time()-t:.0f}s)", flush=True)
        return evals[key]

    for p in range(passes):
        for name, values in grid.items():
            scores = {}
            for v in values:
                c = best.with_(**{name: v})
                scores[v] = objective(run(c, None), TARGET[name])
                log.append(dict(pass_=p, param=name, value=v, objective=scores[v], markets=",".join(TARGET[name])))
            v_best = min(scores, key=scores.get)
            if verbose:
                print(f"  {name}: " + ", ".join(f"{k}={s:.5f}" for k, s in scores.items()) + f"  -> {v_best}")
            best = best.with_(**{name: v_best})
            # drop cached snapshots for half-lives no longer in use to bound memory
            for k in [k for k in cache if k[1] != best.half_life_games]:
                cache.pop(k)
    return best, pd.DataFrame(log)


def save_config(cfg: ModelConfig, path: str, extra: dict | None = None) -> None:
    d = cfg.to_dict()
    d = {k: (list(v) if isinstance(v, tuple) else v) for k, v in d.items()}
    if extra:
        d.update(extra)
    with open(path, "w") as f:
        json.dump(d, f, indent=2, default=float)


def load_config(path: str) -> ModelConfig:
    with open(path) as f:
        d = json.load(f)
    fields = ModelConfig.__dataclass_fields__
    kw = {k: (tuple(v) if isinstance(v, list) else v) for k, v in d.items() if k in fields}
    return ModelConfig(**kw)
