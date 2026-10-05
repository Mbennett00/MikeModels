"""Turn raw book prices into per-selection no-vig probabilities (Section 8)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import ModelConfig
from .pricing import american_to_prob

PLAYER_MARKETS = {"goals", "sog", "assists", "points"}
THIN_MARKETS = {"assists", "team_total", "p1_total", "p1_3way"}

# selections that are the complement of each other within a (market, line) group
_GROUP_SELECTIONS = {
    "moneyline": ["home", "away"], "p1_3way": ["home", "draw", "away"],
    "total": ["over", "under"], "p1_total": ["over", "under"],
    "goals": ["over", "under"], "sog": ["over", "under"], "assists": ["over", "under"],
    "points": ["over", "under"],
}


def normalise_odds(odds: pd.DataFrame) -> pd.DataFrame:
    o = odds.copy()
    o["selection"] = o.selection.astype(str).str.lower().replace({"yes": "over", "no": "under"})
    o["player_id"] = pd.to_numeric(o.player_id, errors="coerce")
    o["line"] = pd.to_numeric(o.line, errors="coerce")
    o["implied"] = o.price.map(american_to_prob)
    # puckline: pair home -1.5 with away +1.5 by expressing both from home's perspective
    pl = o.market == "puckline"
    o["group_line"] = o.line
    o.loc[pl & (o.selection == "away"), "group_line"] = -o.loc[pl & (o.selection == "away"), "line"]
    # team totals: home_over / home_under share a group; the side is part of the group key
    o["group_key"] = o.market
    tt = o.market == "team_total"
    o.loc[tt, "group_key"] = "team_total_" + o.loc[tt, "selection"].str.split("_").str[0]
    return o


def novig_table(odds: pd.DataFrame, cfg: ModelConfig, snapshot: str) -> pd.DataFrame:
    """One row per (game, market, selection, line, player) with consensus no-vig prob and best price."""
    o = normalise_odds(odds)
    o = o[o.snapshot == snapshot]
    if o.empty:
        return pd.DataFrame()
    keys = ["game_id", "group_key", "group_line", "player_id", "book"]
    o["n_sides"] = o.groupby(keys, dropna=False).selection.transform("nunique")
    o["sum_implied"] = o.groupby(keys, dropna=False).implied.transform("sum")
    full = o.market.map(lambda m: len(_GROUP_SELECTIONS.get(m, ["a", "b"])))
    two_sided = o.n_sides >= full
    hold = np.where(o.market.isin(PLAYER_MARKETS), cfg.one_sided_hold["player"], cfg.one_sided_hold["game"])
    o["novig"] = np.where(two_sided, o.implied / o.sum_implied, o.implied / (1 + hold))
    o["one_sided"] = ~two_sided
    g = o.groupby(["game_id", "market", "selection", "line", "player_id"], dropna=False)
    out = g.agg(p_novig=("novig", "median"), best_price=("price", "max"), n_books=("book", "nunique"),
                one_sided=("one_sided", "all"), date=("date", "first")).reset_index()
    out["thin"] = out.market.isin(THIN_MARKETS) | (out.n_books < 2) | out.one_sided
    return main_lines(out)


ALT_SHARE = 0.6   # an alternate game line needs this share of the main line's books (and 3+) to count


def main_lines(out: pd.DataFrame) -> pd.DataFrame:
    """Drop stray game lines that only a book or two hang. 2026-10-04 UTA@NYR: the main total was 5.5 (9 books) but
    4 books' 'over 4.5 -126' and one book's 'over 5 +134' read as 16-21% edges; real alternates carry most books."""
    if out.empty:
        return out
    game = out.market.isin(["total", "puckline", "p1_total"]) & out.player_id.isna()
    if not game.any():
        return out
    g = out[game]
    top = g.groupby(["game_id", "market"]).n_books.transform("max")
    keep = (g.n_books >= top) | ((g.n_books >= 3) & (g.n_books >= ALT_SHARE * top))
    return pd.concat([out[~game], g[keep]]).sort_index()
