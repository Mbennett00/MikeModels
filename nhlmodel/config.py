"""All tunable constants in one place.

Every value here is a *starting point*. The RULES require grid-searching the
shrinkage constants, the decay half-life and the edge thresholds on the
walk-forward backtest before any output is used; see ``nhlmodel.tuning``.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict, replace


@dataclass(frozen=True)
class ModelConfig:
    # ---- data window / recency ------------------------------------------------
    seasons_back: int = 2              # current season + previous season
    half_life_games: float = 25.0      # exponential decay half-life, in the entity's own games
    prior_season_weight: float = 0.6   # team data from earlier seasons (roster turnover); tuned

    # ---- team model shrinkage (minutes of TOI of league-average prior) --------
    k_team_5v5: float = 1500.0
    k_team_pp: float = 300.0
    k_team_pk: float = 300.0
    k_team_pen: float = 1500.0         # penalties drawn/taken per 60 (all-situation minutes)
    k_goalie_xga: float = 60.0         # xGA-equivalent prior for goalie GA/xGA ratio
    pace_exponent: float = 0.0         # 0 disables pace_factor; tuned on backtest
    use_rest_factor: bool = True       # kept only if fitted effect is significant (|z| >= rest_min_z)
    rest_min_z: float = 2.0

    # ---- player shrinkage -----------------------------------------------------
    k_ixg_5v5: float = 400.0
    k_ixg_pp: float = 150.0
    k_sog_5v5: float = 250.0
    k_sog_pp: float = 100.0
    k_ast_5v5: float = 600.0           # larger k: assists are noisier
    k_ast_pp: float = 250.0
    m_finish: float = 30.0             # goals-equivalent prior for finishing multiplier
    finish_cap: tuple = (0.85, 1.15)
    toi_window: int = 10               # rolling games for TOI projection
    lineup_beta: float = 0.0           # personnel adjustment strength (0 = off); set from the backtest
    lineup_clip: tuple = (0.9, 1.1)    # cap on the lineup factor
    toi_role_blend_on_change: float = 0.5   # weight on role-average TOI when line/PP unit changed
    linemate_exponent: float = 0.5     # damping of linemate quality factor (0 disables)
    linemate_clip: tuple = (0.8, 1.25)
    sog_script_gamma: float = 0.10     # SOG uplift per unit of (0.5 - P(team wins)); tuned

    # ---- consistency ------------------------------------------------------------
    consistency_tol: float = 0.05

    # ---- distributions (defaults used until enough out-of-sample data to fit) --
    nb_r_default: dict = field(default_factory=lambda: {"F": 8.0, "D": 6.0})
    nb_min_samples: int = 2000
    biv_cov_default: float = 0.05

    # ---- pricing ------------------------------------------------------------------
    one_sided_hold: dict = field(default_factory=lambda: {
        "game": 0.025,      # conservative (small) hold removed when only one side is posted
        "player": 0.05,
    })
    edge_threshold: dict = field(default_factory=lambda: {
        "goals": 0.03, "sog": 0.03, "assists": 0.03, "points": 0.03,
        "moneyline": 0.02, "puckline": 0.02, "total": 0.02,
        "team_total": 0.02, "p1_total": 0.02, "p1_3way": 0.02,
    })
    require_confirmed: bool = True     # unconfirmed lineup/goalie => never flagged, always reported

    # ---- validation -----------------------------------------------------------------
    calib_edges: tuple = (0.0, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50,
                          0.60, 0.70, 0.80, 0.90, 1.0)
    min_bucket_n: int = 200
    max_ece: float = 0.03              # expected calibration error above this => market downweighted
    refit_every_days: int = 14         # walk-forward refit cadence for fitted parameters

    def to_dict(self) -> dict:
        return asdict(self)

    def with_(self, **kw) -> "ModelConfig":
        return replace(self, **kw)


DEFAULT = ModelConfig()
