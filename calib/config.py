"""Every threshold the calibration engine uses, in one place (override with CALIB_* environment variables or
by passing a CalibConfig)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


@dataclass
class CalibConfig:
    # sample-size shrinkage: (minimum observations, share of the fitted correction kept)
    tiers: list = field(default_factory=lambda: [(0, 0.0), (25, 0.10), (50, 0.25), (100, 0.50), (250, 0.75)])
    blend: float = 0.5               # final = original + blend x (recalibrated - original): never a full replacement
    min_obs: int = 100               # graded predictions needed before a recalibration is even attempted
    min_segment: int = 25            # smallest segment in which a bias can be reported
    fdr: float = 0.05                # Benjamini-Hochberg false-discovery rate for bias reports
    coef_t: float = 2.0              # a component's correction is kept only when |t| >= this
    ridge: float = 1.0               # ridge penalty (standardised features) on the residual model
    half_life_days: float = 365.0    # older predictions count less, but a full year still counts half
    min_improvement: float = 0.002   # walk-forward MAE must improve by at least 0.2% to apply
    recent_tolerance: float = 0.01   # and may not be more than 1% worse over the last 100 predictions
    max_rel_change: float = 0.15     # a correction can move a projection by at most 15%
    wf_min_train: int = 100          # walk-forward: first training window
    wf_chunk_days: int = 7           # walk-forward: refit every week of predictions
    candidates: list = field(default_factory=lambda: [0.25, 0.5])   # blends tried in the backtest

    def shrink(self, n: int) -> float:
        k = 0.0
        for lo, v in self.tiers:
            if n >= lo:
                k = v
        return k

    @classmethod
    def from_env(cls) -> "CalibConfig":
        c = cls()
        for f in c.__dataclass_fields__:
            v = os.environ.get(f"CALIB_{f.upper()}")
            if v is not None:
                setattr(c, f, json.loads(v))
        return c
