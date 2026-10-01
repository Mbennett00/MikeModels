"""Personnel adjustment: does tonight's lineup create more or less than the team usually dresses?

Team ratings come from team-level results over recent games, so they describe the players who
usually played. When a star is out and a depth player fills in, the team's attack should drop.

For each skater, goal creation per 60 = average of two estimates of his share of team goals:
finishing-adjusted individual xG, and assists / league assists-per-goal (5-on-5 and PP rates,
shrunk toward the league average of his usual role). Quality per minute is the TOI-weighted
average of that over the skaters on the ice:

    usual   = over the team's last `toi_window` games, using the minutes actually played
    tonight = over tonight's skaters, using projected minutes

    lineup factor = clip((tonight / usual) ** beta, clip range)

beta < 1 because individual creation rates only partly carry over to team goals (teammates and
system matter too); beta is chosen by the walk-forward backtest. Players with no history count at
replacement level (bottom-six / bottom-pair role average), not at the role they are slotted into.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import ModelConfig


def _creation(snap, pid, pos, line, pp_unit, cfg: ModelConfig) -> tuple[float, float]:
    from .player_model import adjusted_rates
    if pid in snap.player.index:
        r = snap.player.loc[pid]
        line, pp_unit = r.line, r.pp_unit          # shrink toward his usual role, not tonight's slot
    else:
        line, pp_unit = ("D3" if pos == "D" else "F4"), 0   # no history: replacement level
    a = adjusted_rates(snap, pid, pos, line, pp_unit, cfg)
    apg = snap.league.get("assists_per_goal", 1.7) or 1.7
    c5 = 0.5 * (a["finish"] * a["ixg60_5v5"] + a["a60_5v5"] / apg)
    cpp = 0.5 * (a["finish"] * a["ixg60_pp"] + a["a60_pp"] / apg)
    return c5, cpp


def lineup_factor(snap, team: str, skaters: pd.DataFrame, cfg: ModelConfig) -> tuple[float, dict]:
    """skaters: tonight's F and D for `team` (player_id, pos, line, pp_unit). Returns (factor, info)."""
    from .player_model import project_toi
    beta = getattr(cfg, "lineup_beta", 0.0)
    info = dict(usual=np.nan, tonight=np.nan, ratio=1.0, missing=[])
    if beta <= 0 or skaters is None or len(skaters) < 10:
        return 1.0, info
    rec = snap.player_recent[snap.player_recent.team == team]
    if rec.empty:
        return 1.0, info
    games = rec.drop_duplicates("game_id").sort_values("date").game_id.tail(cfg.toi_window)
    rec = rec[rec.game_id.isin(games)]
    cache = {}

    def rate(pid, pos, line, pp):
        if pid not in cache:
            cache[pid] = _creation(snap, pid, pos, line, pp, cfg)
        return cache[pid]

    num = den = 0.0
    for r in rec.itertuples():
        c5, cpp = rate(r.player_id, r.pos, r.line, r.pp_unit)
        num += c5 * r.toi_5v5 + cpp * r.toi_pp
        den += r.toi_5v5 + r.toi_pp
    usual = num / den if den > 0 else np.nan
    pp_min = snap.league["pp_toi_pg"]
    num = den = 0.0
    for r in skaters.itertuples():
        c5, cpp = rate(r.player_id, r.pos, r.line, r.pp_unit)
        t = project_toi(snap, r.player_id, r.pos, r.line, r.pp_unit, cfg)
        toi5, toipp = t["toi_5v5"], t["pp_share"] * pp_min
        num += c5 * toi5 + cpp * toipp
        den += toi5 + toipp
    tonight = num / den if den > 0 else np.nan
    if not (usual > 0 and tonight > 0):
        return 1.0, info
    ratio = tonight / usual
    lo, hi = getattr(cfg, "lineup_clip", (0.9, 1.1))
    # regulars from the recent games who are not dressing tonight, biggest minutes first
    mins = rec.groupby("player_id").toi_5v5.sum()
    out = [p for p in mins.sort_values(ascending=False).index[:12] if p not in set(skaters.player_id)]
    info = dict(usual=usual, tonight=tonight, ratio=ratio, missing=out[:4])
    return float(np.clip(ratio ** beta, lo, hi)), info
