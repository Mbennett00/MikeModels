"""Parameters fitted from history (walk-forward: only games before the refit date)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FittedParams:
    lam3: float = 0.05                                 # bivariate Poisson covariance
    lam_scale: float = 1.0                             # league calibration: actual / predicted team goals
    ot_slope: float = 0.5                              # P(home wins OT/SO) = 0.5 + slope*(share-0.5)
    ot_home_edge: float = 0.0
    en_trans: dict = field(default_factory=lambda: {   # leader's lead d -> P(0,1,2 EN goals)
        1: [0.72, 0.25, 0.03], 2: [0.82, 0.16, 0.02], 3: [0.93, 0.07, 0.0]})
    p1_share: float = 0.30
    ot_goal_share: float = 0.60                        # share of OT/SO games decided by an OT goal
    rest: dict = field(default_factory=lambda: {"b2b_off": 1.0, "b2b_def": 1.0, "travel_off": 1.0})
    rest_notes: list = field(default_factory=list)
    nb_r: dict = field(default_factory=lambda: {"sog": {"F": 8.0, "D": 6.0}})
    count_r: dict = field(default_factory=lambda: {"assists": 1e6, "points": 1e6})  # 1e6 = Poisson
    en_uplift: float = 1.03                            # settlement includes EN goals; training excludes them
    notes: list = field(default_factory=list)
