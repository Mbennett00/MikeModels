"""Sections 2-7: player shrinkage, TOI, goals, shots, assists, points, consistency check."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from .config import ModelConfig
from .distributions import nb_sf
from .params import FittedParams
from .ratings import Snapshot, role_5v5, role_pp
from .team_model import GameProjection, TeamModel, shrink

STAT_COLS = ["toi_5v5", "toi_pp", "ixg_5v5", "ixg_pp", "sog_5v5", "sog_pp", "a1_5v5", "a2_5v5",
             "a1_pp", "a2_pp", "ixg_nonen", "g_nonen", "w"]


def _player_row(snap: Snapshot, pid) -> pd.Series:
    if pid in snap.player.index:
        return snap.player.loc[pid]
    return pd.Series({c: 0.0 for c in STAT_COLS})


def adjusted_rates(snap: Snapshot, pid, pos: str, line: str, pp_unit, cfg: ModelConfig) -> dict:
    """Shrink each per-60 rate toward the league average of the player's role today."""
    r = _player_row(snap, pid)
    r5, rp = role_5v5(pos, line), role_pp(pos, pp_unit)
    R5 = snap.role5.loc[r5] if r5 in snap.role5.index else snap.role5.mean()
    # PP rates shrink toward the PP role for the player's unit; non-PP players toward PP2 of position
    rp_key = rp if rp in snap.rolepp.index and not rp.endswith("PP0") else f"{pos}_PP2"
    RP = snap.rolepp.loc[rp_key] if rp_key in snap.rolepp.index else snap.rolepp.mean()
    out = dict(
        ixg60_5v5=shrink(60 * r.ixg_5v5, r.toi_5v5, R5.ixg60, cfg.k_ixg_5v5),
        ixg60_pp=shrink(60 * r.ixg_pp, r.toi_pp, RP.ixg60, cfg.k_ixg_pp),
        sog60_5v5=shrink(60 * r.sog_5v5, r.toi_5v5, R5.sog60, cfg.k_sog_5v5),
        sog60_pp=shrink(60 * r.sog_pp, r.toi_pp, RP.sog60, cfg.k_sog_pp),
        # (A1+A2) shrunk with one k equals the sum of A1 and A2 each shrunk with that k
        a60_5v5=shrink(60 * (r.a1_5v5 + r.a2_5v5), r.toi_5v5, R5.a60, cfg.k_ast_5v5),
        a60_pp=shrink(60 * (r.a1_pp + r.a2_pp), r.toi_pp, RP.a60, cfg.k_ast_pp),
        n_toi_5v5=float(r.toi_5v5), n_toi_pp=float(r.toi_pp),
    )
    rate = snap.league["g_per_xg"]
    lo, hi = cfg.finish_cap
    # m goals-equivalent of prior at the league goals-per-xG rate
    out["finish"] = float(np.clip((r.g_nonen + cfg.m_finish * rate) / (r.ixg_nonen + cfg.m_finish), lo, hi))
    return out


def project_toi(snap: Snapshot, pid, pos, line, pp_unit, cfg: ModelConfig) -> dict:
    rec = snap.recent(pid)
    r5, rp = role_5v5(pos, line), role_pp(pos, pp_unit)
    role_toi = float(snap.role5.toi_pg.get(r5, snap.role5.toi_pg.mean()))
    role_share = float(snap.rolepp.pp_share.get(rp, 0.0))
    notes = []
    if len(rec) < 3:
        notes.append(f"only {len(rec)} recent games: role-average TOI")
        return dict(toi_5v5=role_toi, pp_share=role_share, notes=notes)
    toi5 = float(rec.toi_5v5.mean())
    share = float(rec.pp_share.mean())
    modal_line = rec.line.mode().iat[0]
    modal_pp = int(rec.pp_unit.mode().iat[0])
    b = cfg.toi_role_blend_on_change
    if role_5v5(pos, modal_line) != r5 or str(modal_line) != str(line):
        toi5 = (1 - b) * toi5 + b * role_toi
        notes.append(f"line change {modal_line}->{line}")
    try:
        unit_now = int(pp_unit)
    except (TypeError, ValueError):
        unit_now = 0
    if modal_pp != unit_now:
        share = (1 - b) * share + b * role_share
        notes.append(f"PP unit change {modal_pp}->{unit_now}")
    return dict(toi_5v5=toi5, pp_share=share, notes=notes)


def _linemate_factor(snap, pid, team, line, today_mates, rates_by_pid, cfg):
    """(expected xG/60 of today's linemates / of this player's recent linemates) ** exponent."""
    if cfg.linemate_exponent == 0 or not today_mates:
        return 1.0
    q_today = sum(rates_by_pid[m] for m in today_mates if m in rates_by_pid)
    games = [g for g in snap.lines_of(pid) if g[1] == team]
    if not games:
        return 1.0
    prior = snap.role5.ixg60.mean()

    def q(p):
        if p in rates_by_pid:
            return rates_by_pid[p]
        if p in snap.player.index:
            r = snap.player.loc[p]
            return shrink(60 * r.ixg_5v5, r.toi_5v5, prior, cfg.k_ixg_5v5)
        return prior

    per_game = [sum(q(p) for p in snap.mates_in(*g) if p != pid) for g in games]
    q_hist = float(np.mean(per_game))
    if q_hist <= 0 or q_today <= 0:
        return 1.0
    lo, hi = cfg.linemate_clip
    return float(np.clip((q_today / q_hist) ** cfg.linemate_exponent, lo, hi))


def project_team_players(tm: TeamModel, gp: GameProjection, side: str, lineup: pd.DataFrame,
                         params: FittedParams, cfg: ModelConfig) -> tuple[pd.DataFrame, dict]:
    """lineup: skaters for one team (player_id, name, pos, line, pp_unit, confirmed)."""
    snap = tm.snap
    L = snap.league
    f = gp.factors[side]
    team = gp.home if side == "home" else gp.away
    team_pp_min = L["pp_toi_pg"] * f["pp_time"]
    opp_5v5, opp_pp = f["def_opp"], tm.rating(gp.away if side == "home" else gp.home).pk_def
    goalie, home = f["goalie_opp"], f["home"]
    p_win = gp.p_team_wins(side)
    script = 1.0 + cfg.sog_script_gamma * (0.5 - p_win)
    tsf = f["lam"] / f["baseline"] if f["baseline"] > 0 else 1.0

    sk = lineup[lineup.pos.isin(["F", "D"])]
    rates = {r.player_id: adjusted_rates(snap, r.player_id, r.pos, r.line, r.pp_unit, cfg)
             for r in sk.itertuples()}
    ixg_by = {p: v["ixg60_5v5"] for p, v in rates.items()}
    rows = []
    for r in sk.itertuples():
        a = rates[r.player_id]
        t = project_toi(snap, r.player_id, r.pos, r.line, r.pp_unit, cfg)
        toi5 = t["toi_5v5"]; toipp = t["pp_share"] * team_pp_min
        mates = [m for m in sk[(sk.line == r.line)].player_id if m != r.player_id]
        lm = _linemate_factor(snap, r.player_id, team, r.line, mates, ixg_by, cfg)
        lam_g = a["finish"] * (a["ixg60_5v5"] * toi5 / 60 * opp_5v5 + a["ixg60_pp"] * toipp / 60 * opp_pp) \
            * goalie * home
        lam_sog = (a["sog60_5v5"] * toi5 / 60 + a["sog60_pp"] * toipp / 60) * f["opp_shots_against"] \
            * home * script
        lam_a = (a["a60_5v5"] * toi5 / 60 * lm + a["a60_pp"] * toipp / 60) * tsf
        # the same player against a league-average opponent at a neutral rink: the ratio is tonight's matchup effect
        toipp_n = t["pp_share"] * L["pp_toi_pg"]
        g_n = a["finish"] * (a["ixg60_5v5"] * toi5 + a["ixg60_pp"] * toipp_n) / 60
        a_n = (a["a60_5v5"] * toi5 * lm + a["a60_pp"] * toipp_n) / 60
        sog_n = (a["sog60_5v5"] * toi5 + a["sog60_pp"] * toipp_n) / 60
        mx_pts = (lam_g + lam_a) / (g_n + a_n) if g_n + a_n > 0 else 1.0
        mx_sog = lam_sog / sog_n if sog_n > 0 else 1.0
        flags = list(t["notes"])
        if not bool(r.confirmed):
            flags.append("LINEUP UNCONFIRMED")
        if a["n_toi_5v5"] < 100:
            flags.append(f"small sample ({a['n_toi_5v5']:.0f} weighted 5v5 min)")
        rows.append(dict(player_id=r.player_id, name=r.name, team=team, pos=r.pos, line=r.line,
                         pp_unit=r.pp_unit, confirmed=bool(r.confirmed), toi_5v5=toi5, toi_pp=toipp,
                         finish=a["finish"], ixg60_5v5=a["ixg60_5v5"], ixg60_pp=a["ixg60_pp"],
                         sog60_5v5=a["sog60_5v5"], a60_5v5=a["a60_5v5"], linemate=lm,
                         lam_goals_nonen=lam_g, lam_sog=lam_sog, lam_ast_raw=lam_a, mx_pts=mx_pts, mx_sog=mx_sog,
                         flags="; ".join(flags)))
    df = pd.DataFrame(rows)
    # ---- recalibration (level + spread), fitted walk-forward on earlier predictions
    if len(df):
        for mkt, col in (("goals", "lam_goals_nonen"), ("sog", "lam_sog"), ("assists", "lam_ast_raw")):
            a, b, ref = getattr(params, "recal", {}).get(mkt, (1.0, 1.0, 1.0))
            df[f"{col}_pre"] = df[col]
            df[col] = a * ref * (df[col].clip(lower=1e-6) / ref) ** b
    # ---- Section 7: consistency check against the team model
    hw, tie, aw = gp.reg_probs()
    p_ot_win = gp.p_ot_home if side == "home" else 1 - gp.p_ot_home
    ot_goals = tie * params.ot_goal_share * p_ot_win
    target_g = f["lam"] * L["skater_goal_share"] + ot_goals
    sum_g = float(df.lam_goals_nonen.sum()) if len(df) else 0.0
    gap_g = sum_g / target_g - 1 if target_g > 0 else 0.0
    target_a = target_g * L["assists_per_goal"]
    sum_a = float(df.lam_ast_raw.sum()) if len(df) else 0.0
    gap_a = sum_a / target_a - 1 if target_a > 0 else 0.0
    sg = target_g / sum_g if abs(gap_g) > cfg.consistency_tol and sum_g > 0 else 1.0
    sa = target_a / sum_a if abs(gap_a) > cfg.consistency_tol and sum_a > 0 else 1.0
    if len(df):
        df["lam_goals_nonen"] *= sg
        df["lam_ast_raw"] *= sa
        # settlement counts empty-net goals; training excluded them -> fitted uplift
        df["lam_goals"] = df.lam_goals_nonen * params.en_uplift
        df["lam_ast"] = df.lam_ast_raw * params.en_uplift
        df["lam_pts"] = df.lam_goals + df.lam_ast
    report = dict(team=team, lam_team=f["lam"], target_goals=target_g, sum_player_goals=sum_g,
                  gap_goals=gap_g, rescaled_goals=sg != 1.0, target_ast=target_a, sum_player_ast=sum_a,
                  gap_ast=gap_a, rescaled_ast=sa != 1.0)
    return df, report


# ---- probabilities for each market -----------------------------------------------

def prob_goals(lam, line=0.5):
    return float(stats.poisson.sf(np.floor(line), lam))


def prob_count(lam, line, r):
    """P(X > line) for X.5 lines, NB when r is finite, else Poisson."""
    if r is None or r >= 1e5:
        return float(stats.poisson.sf(np.floor(line), lam))
    return float(nb_sf(line, lam, r))


def player_market_prob(row, market: str, line: float, params: FittedParams) -> float:
    if market == "goals":
        return prob_goals(row["lam_goals"], line)
    if market == "sog":
        r = params.nb_r["sog"].get(row["pos"], 8.0)
        return prob_count(row["lam_sog"], line, r)
    if market == "assists":
        return prob_count(row["lam_ast"], line, params.count_r.get("assists"))
    if market == "points":
        if line == 0.5 and params.count_r.get("points", 1e6) >= 1e5:
            return float(1 - np.exp(-row["lam_pts"]))
        return prob_count(row["lam_pts"], line, params.count_r.get("points"))
    raise ValueError(market)


PLAYER_MARKETS = {"goals": "lam_goals", "sog": "lam_sog", "assists": "lam_ast", "points": "lam_pts"}
OUTCOME_COL = {"goals": "goals", "sog": "sog", "assists": "assists", "points": "points"}
