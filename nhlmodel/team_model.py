"""Section 1: team model for sides and totals.

lambda_team = base * off * def_opp * goalie_opp * PP_PK * pace * rest * home

PP_PK is written so the 5v5 factors do not also scale power-play scoring:
  PP_PK = [(1-s)*off*def + s*pp_off*pk_def_opp*pp_time] / (off*def)
where s = league share of xG generated on the PP. Multiplying through gives the
spec's product form exactly.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .arenas import distance_km
from .config import ModelConfig
from .distributions import bivariate_poisson_matrix
from .params import FittedParams
from .ratings import Snapshot


def shrink(num60: float, toi: float, prior_rate: float, k: float) -> float:
    """(n*rate + k*prior)/(n+k) with n = TOI minutes; num60 = 60*count so n*rate = num60."""
    return (num60 + k * prior_rate) / (toi + k)


@dataclass
class TeamRating:
    team: str
    off: float
    dfn: float           # xGA/60 relative (>1 = leakier)
    pp_off: float
    pk_def: float
    drawn: float         # penalties drawn / league
    taken: float
    pace: float          # (CF60 + CA60) / (2 * league CF60)
    shots_against: float
    sample_toi: float


def team_rating(snap: Snapshot, team: str, cfg: ModelConfig) -> TeamRating:
    L = snap.league
    if team not in snap.team.index:
        return TeamRating(team, 1, 1, 1, 1, 1, 1, 1, 1, 0.0)
    r = snap.team.loc[team]
    lg5, lgpp = L["xg60_5v5"], L["xg60_pp"]
    pen60 = L["pen_pg"] / L["toi_all_pg"] * 60
    off = shrink(60 * r.xgf_5v5_adj, r.toi_5v5, lg5, cfg.k_team_5v5) / lg5
    dfn = shrink(60 * r.xga_5v5_adj, r.toi_5v5, lg5, cfg.k_team_5v5) / lg5
    ppo = shrink(60 * r.xgf_pp, r.toi_pp, lgpp, cfg.k_team_pp) / lgpp
    pkd = shrink(60 * r.xga_pk, r.toi_pk, lgpp, cfg.k_team_pk) / lgpp
    drawn = shrink(60 * r.pen_drawn, r.toi_all, pen60, cfg.k_team_pen) / pen60
    taken = shrink(60 * r.pen_taken, r.toi_all, pen60, cfg.k_team_pen) / pen60
    lgcf = L["cf60_5v5"]
    pace = shrink(30 * (r.cf_5v5 + r.ca_5v5), r.toi_5v5, lgcf, cfg.k_team_5v5) / lgcf
    sog_pg = L["sog_pg"]
    sa = (r.sog_against + 20 * sog_pg) / (r.w + 20) / sog_pg   # ~20-game prior
    return TeamRating(team, off, dfn, ppo, pkd, drawn, taken, pace, sa, float(r.toi_5v5))


def goalie_factor(snap: Snapshot, goalie_id, team: str, cfg: ModelConfig) -> tuple[float, str]:
    """GA/xGA of the goalie, shrunk to league, relative to league. <1 = better than average."""
    lg = snap.league["ga_per_xga"]
    k = cfg.k_goalie_xga
    if goalie_id is not None and not pd.isna(goalie_id) and goalie_id in snap.goalie.index:
        g = snap.goalie.loc[goalie_id]
        return ((g.ga + k * lg) / (g.xga + k)) / lg, "goalie"
    if team in snap.goalie_team_avg.index:   # unknown starter: team's weighted blend, flagged by caller
        g = snap.goalie_team_avg.loc[team]
        return ((g.ga + k * lg) / (g.xga + k)) / lg, "team_avg_goalie"
    return 1.0, "league_avg_goalie"


def rest_flags(snap: Snapshot, team: str, venue: str, date) -> dict:
    lg = snap.last_game.get(team)
    if lg is None:
        return {"b2b": False, "travel_km": 0.0}
    days = (pd.Timestamp(date) - lg[0]).days
    km = distance_km(lg[1], venue) if days <= 1 else 0.0
    return {"b2b": days == 1, "travel_km": km}


@dataclass
class GameProjection:
    home: str
    away: str
    lam_home: float
    lam_away: float
    base_home: float      # team baseline goals vs league-average opp, neutral site
    base_away: float
    matrix: np.ndarray    # regulation score incl. EN transitions
    matrix_nonen: np.ndarray
    p_ot_home: float
    p1_matrix: np.ndarray
    factors: dict = field(default_factory=dict)
    flags: list = field(default_factory=list)

    # ---- markets -------------------------------------------------------------
    def _hh_aa(self, m):
        n = m.shape[0]
        return np.meshgrid(np.arange(n), np.arange(n), indexing="ij")

    def reg_probs(self):
        h, a = self._hh_aa(self.matrix)
        return (float(self.matrix[h > a].sum()), float(self.matrix[h == a].sum()),
                float(self.matrix[h < a].sum()))

    def moneyline(self):
        hw, tie, aw = self.reg_probs()
        ph = hw + tie * self.p_ot_home
        return {"home": ph, "away": 1 - ph}

    def puckline(self, line: float = -1.5, side: str = "home"):
        """P(side covers `line`). Margin >= 2 only happens in regulation (OT/SO adds 1)."""
        h, a = self._hh_aa(self.matrix)
        margin = (h - a) if side == "home" else (a - h)
        # final margin: regulation margin, or +/-1 when regulation tied (OT/SO)
        pw_ot = self.p_ot_home if side == "home" else 1 - self.p_ot_home
        mask_tie = margin == 0
        p = float(self.matrix[(~mask_tie) & (margin + line > 0)].sum())
        tie = float(self.matrix[mask_tie].sum())
        if 1 + line > 0:
            p += tie * pw_ot
        if -1 + line > 0:
            p += tie * (1 - pw_ot)
        return p

    def total_dist(self):
        """Distribution of the official final total (OT/SO winner credited one goal)."""
        h, a = self._hh_aa(self.matrix)
        t = h + a + (h == a)
        out = np.bincount(t.ravel(), weights=self.matrix.ravel())
        return out

    def team_total_dist(self, side: str):
        h, a = self._hh_aa(self.matrix)
        own = h if side == "home" else a
        pw = self.p_ot_home if side == "home" else 1 - self.p_ot_home
        tie = h == a
        dist = np.bincount(own[~tie].ravel(), weights=self.matrix[~tie].ravel(), minlength=own.max() + 2)
        tie_d = np.bincount(own[tie].ravel(), weights=self.matrix[tie].ravel(), minlength=own.max() + 2)
        dist = dist.astype(float)
        dist[: len(tie_d)] += tie_d * (1 - pw)
        dist[1: len(tie_d)] += tie_d[:-1] * pw
        return dist

    @staticmethod
    def over_under(dist: np.ndarray, line: float):
        """(P over, P under, P push). Whole-number lines: push removed and renormalised."""
        k = np.arange(len(dist))
        over, under = float(dist[k > line].sum()), float(dist[k < line].sum())
        push = float(dist[k == line].sum()) if float(line).is_integer() else 0.0
        if push > 0:
            return over / (1 - push), under / (1 - push), push
        return over, under, 0.0

    def total(self, line: float):
        o, u, p = self.over_under(self.total_dist(), line)
        return {"over": o, "under": u, "push": p}

    def team_total(self, side: str, line: float):
        o, u, p = self.over_under(self.team_total_dist(side), line)
        return {"over": o, "under": u, "push": p}

    def p1_3way(self):
        h, a = self._hh_aa(self.p1_matrix)
        m = self.p1_matrix
        return {"home": float(m[h > a].sum()), "draw": float(m[h == a].sum()), "away": float(m[h < a].sum())}

    def p1_total(self, line: float):
        h, a = self._hh_aa(self.p1_matrix)
        dist = np.bincount((h + a).ravel(), weights=self.p1_matrix.ravel())
        o, u, p = self.over_under(dist, line)
        return {"over": o, "under": u, "push": p}

    def p_team_wins(self, side: str):
        ml = self.moneyline()
        return ml[side]


def apply_en(m: np.ndarray, en_trans: dict) -> np.ndarray:
    """Move regulation mass for leads of 1-3 to (lead + k) with fitted EN-goal probabilities."""
    n = m.shape[0]
    out = np.zeros((n + 2, n + 2))
    for h in range(n):
        for a in range(n):
            p = m[h, a]
            if p == 0:
                continue
            d = h - a
            tr = en_trans.get(abs(d)) if d != 0 else None
            if tr is None:
                out[h, a] += p
                continue
            for k, pk in enumerate(tr):
                if d > 0:
                    out[h + k, a] += p * pk
                else:
                    out[h, a + k] += p * pk
    return out


CALIBRATION = None   # calib.engine.Live for live slates only (set by nhlmodel.calib_hook.use_live; None in backtests)


class TeamModel:
    def __init__(self, cfg: ModelConfig, snap: Snapshot, params: FittedParams):
        self.cfg, self.snap, self.params = cfg, snap, params
        self._ratings: dict = {}

    def rating(self, team):
        if team not in self._ratings:
            self._ratings[team] = team_rating(self.snap, team, self.cfg)
        return self._ratings[team]

    def lambdas(self, home, away, home_goalie=None, away_goalie=None, date=None,
                goalie_confirmed=(True, True), lineups=None):
        cfg, L, P = self.cfg, self.snap.league, self.params
        rh, ra = self.rating(home), self.rating(away)
        base = L["goals_pg"]
        s = L["pp_xg_share"]
        h = L["home_ratio"]
        flags = []
        gf_h, src_h = goalie_factor(self.snap, home_goalie, home, cfg)
        gf_a, src_a = goalie_factor(self.snap, away_goalie, away, cfg)
        for team, src, conf in ((home, src_h, goalie_confirmed[0]), (away, src_a, goalie_confirmed[1])):
            if src != "goalie":
                flags.append(f"{team}: starting goalie unknown to model ({src})")
            if not conf:
                flags.append(f"{team}: starting goalie UNCONFIRMED")
        pace = ((rh.pace + ra.pace) / 2) ** cfg.pace_exponent
        rest = {home: 1.0, away: 1.0}
        rest_def = {home: 1.0, away: 1.0}
        if cfg.use_rest_factor and date is not None:
            for team in (home, away):
                rf = rest_flags(self.snap, team, home, date)
                if rf["b2b"]:
                    rest[team] *= P.rest.get("b2b_off", 1.0)
                    rest_def[team] *= P.rest.get("b2b_def", 1.0)
                if rf["travel_km"] > 1500:
                    rest[team] *= P.rest.get("travel_off", 1.0)
        # tonight's personnel vs the players the team usually dresses (1.0 when off or no lineup)
        lf, lf_info = {home: 1.0, away: 1.0}, {}
        if lineups is not None and getattr(cfg, "lineup_beta", 0) > 0:
            from .lineup import lineup_factor
            for team in (home, away):
                sk = lineups.get(team)
                lf[team], lf_info[team] = lineup_factor(self.snap, team, sk, cfg)
        out = {}
        for side, a, d, gf, hf in (("home", rh, ra, gf_a, h), ("away", ra, rh, gf_h, 1 / h)):
            pp_time = a.drawn * d.taken
            mix5 = (1 - s) * a.off * d.dfn
            mixpp = s * a.pp_off * d.pk_def * pp_time
            pppk = (mix5 + mixpp) / (a.off * d.dfn)
            opp = d.team
            lam = base * a.off * d.dfn * gf * pppk * pace * rest[a.team] * rest_def[opp] * hf * P.lam_scale * lf[a.team]
            baseline = base * ((1 - s) * a.off + s * a.pp_off * a.drawn)
            out[side] = dict(lam=lam, off=a.off, def_opp=d.dfn, goalie_opp=gf, pp_pk=pppk, pace=pace,
                             rest=rest[a.team] * rest_def[opp], home=hf, baseline=baseline * P.lam_scale,
                             lineup=lf[a.team], lineup_info=lf_info.get(a.team, {}),
                             scale=P.lam_scale,
                             pp_time=pp_time, opp_shots_against=d.shots_against)
        if CALIBRATION is not None:   # self-calibration layer (calib/): small, shrunk, capped correction
            for side, team in (("home", home), ("away", away)):
                o = out[side]
                o["lam_orig"] = o["lam"]
                o["lam"] = CALIBRATION(o["lam"], {k: o[k] for k in ("off", "def_opp", "goalie_opp", "pp_pk", "pace", "rest")},
                                       team, 1 if side == "home" else 0)
        return out, flags

    def project(self, home, away, home_goalie=None, away_goalie=None, date=None,
                goalie_confirmed=(True, True), lineups=None) -> GameProjection:
        """lineups: optional {team: skaters DataFrame (player_id, pos, line, pp_unit)} for the personnel factor."""
        f, flags = self.lambdas(home, away, home_goalie, away_goalie, date, goalie_confirmed, lineups)
        P = self.params
        lh, la = f["home"]["lam"], f["away"]["lam"]
        m0 = bivariate_poisson_matrix(lh, la, P.lam3)
        m = apply_en(m0, P.en_trans)
        share = lh / (lh + la)
        p_ot = float(np.clip(0.5 + P.ot_home_edge + P.ot_slope * (share - 0.5), 0.3, 0.7))
        p1 = bivariate_poisson_matrix(lh * P.p1_share, la * P.p1_share, P.lam3 * P.p1_share, n=10)
        return GameProjection(home, away, lh, la, f["home"]["baseline"], f["away"]["baseline"],
                              m, m0, p_ot, p1, factors=f, flags=flags)
