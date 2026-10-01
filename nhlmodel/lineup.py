"""Missing regulars: lower a team's expected goals when its usual top players are not dressing.

Team ratings come from team-level results over recent games, so they describe the players who
usually played. When a regular is out (injury, rest, healthy scratch), a replacement-level player
takes his minutes and the team's attack should drop.

    regulars  = this season's top-6 forwards and top-4 defence by ice time over the team's last
                `toi_window` games, who played at least half of them
    missing   = regulars not in tonight's lineup
    drop      = sum over missing of (his goal creation - replacement creation) x his usual minutes,
                divided by the team's usual goal creation per game
    factor    = clip(1 - beta * drop, lineup_clip[0], 1)

Goal creation per 60 is the average of two estimates of a skater's share of team goals:
finishing-adjusted individual xG, and assists / league assists-per-goal (5-on-5 and PP rates,
shrunk toward his usual role). Replacement = the bottom-six forward / bottom-pair defence role
average. Only this season's games count, so off-season departures are not treated as injuries.
The factor only lowers a team: a full lineup is what the ratings already assume.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import ModelConfig


def _creation(snap, pid, pos, line, pp_unit, cfg: ModelConfig) -> tuple[float, float]:
    from .player_model import adjusted_rates
    a = adjusted_rates(snap, pid, pos, line, pp_unit, cfg)
    apg = snap.league.get("assists_per_goal", 1.7) or 1.7
    return (0.5 * (a["finish"] * a["ixg60_5v5"] + a["a60_5v5"] / apg),
            0.5 * (a["finish"] * a["ixg60_pp"] + a["a60_pp"] / apg))


def _replacement(snap, pos, cfg: ModelConfig) -> tuple[float, float]:
    """Role-average creation for a bottom-six forward / bottom-pair defenceman with no PP time."""
    apg = snap.league.get("assists_per_goal", 1.7) or 1.7
    R5 = snap.role5.loc["D_bot" if pos == "D" else "F_bot"]
    RP = snap.rolepp.loc[f"{pos}_PP2"] if f"{pos}_PP2" in snap.rolepp.index else snap.rolepp.mean()
    g = snap.league.get("g_per_xg", 1.0)
    return 0.5 * (g * R5.ixg60 + R5.a60 / apg), 0.5 * (g * RP.ixg60 + RP.a60 / apg)


def lineup_factor(snap, team: str, skaters: pd.DataFrame, cfg: ModelConfig) -> tuple[float, dict]:
    """skaters: tonight's F and D for `team` (player_id, pos, line, pp_unit). Returns (factor, info)."""
    beta = getattr(cfg, "lineup_beta", 0.0)
    info = dict(drop=0.0, missing=[], impact={})
    if beta <= 0 or skaters is None or len(skaters) < 10:
        return 1.0, info
    rec = snap.player_recent[snap.player_recent.team == team]
    season_start = pd.Timestamp(f"{snap.season}-09-01")
    rec = rec[rec.date >= season_start]
    games = rec.drop_duplicates("game_id").sort_values("date").game_id.tail(cfg.toi_window)
    k = len(games)
    if k < 3:
        return 1.0, info   # too early in the season to know who the regulars are
    rec = rec[rec.game_id.isin(games)]
    per = rec.groupby("player_id").agg(gp=("game_id", "nunique"), toi5=("toi_5v5", "mean"), toipp=("toi_pp", "mean"),
                                       pos=("pos", "first"), line=("line", lambda s: s.mode().iat[0]),
                                       pp=("pp_unit", lambda s: int(s.mode().iat[0])))
    per = per[per.gp >= max(2, k / 2)]
    top = pd.concat([per[per.pos == "F"].nlargest(6, "toi5"), per[per.pos == "D"].nlargest(4, "toi5")])
    # the team's usual goal creation per game (everyone who played)
    total = 0.0
    rates = {}
    for r in rec.itertuples():
        if r.player_id not in rates:
            rates[r.player_id] = _creation(snap, r.player_id, r.pos, r.line, r.pp_unit, cfg)
        c5, cpp = rates[r.player_id]
        total += c5 * r.toi_5v5 + cpp * r.toi_pp
    total /= k
    if total <= 0:
        return 1.0, info
    dressed = set(skaters.player_id)
    drop, impact = 0.0, {}
    for pid, r in top.iterrows():
        if pid in dressed:
            continue
        c5, cpp = rates.get(pid) or _creation(snap, pid, r.pos, r.line, r.pp, cfg)
        rep5, reppp = _replacement(snap, r.pos, cfg)
        d = max(0.0, (c5 - rep5) * r.toi5 + (cpp - reppp) * r.toipp) / total
        drop += d
        impact[pid] = d
    lo, _ = getattr(cfg, "lineup_clip", (0.9, 1.1))
    factor = float(np.clip(1 - beta * drop, lo, 1.0))
    missing = sorted(impact, key=impact.get, reverse=True)
    info = dict(drop=drop, missing=missing[:4], impact={p: beta * impact[p] for p in missing})
    return factor, info
