"""Opening prices for game lines: each slate run carries forward the first price it published for a market.

The page shows where a line opened and where it is now (DraftKings-style movement arrows). The previous
published file is the memory, so this costs no extra odds pulls.
"""
from __future__ import annotations


def _key(gid, x):
    return (str(gid), x.get("m"), x.get("s"))


def carry(new_games: list, old_games: list | None, field: str = "dk", line_key: str = "l") -> int:
    """Set op (opening price) and ol (opening line) on every priced entry of new_games[*][field].

    An entry matches last run's entry for the same game, market and side (and the same line when a game
    lists several). A market seen for the first time opens at its current price. Returns how many moved."""
    old: dict = {}
    for g in old_games or []:
        for x in g.get(field) or []:
            old.setdefault(_key(g.get("game_id"), x), []).append(x)
    moved = 0
    for g in new_games or []:
        for x in g.get(field) or []:
            if x.get("price") is None:
                continue
            cands = [c for c in old.get(_key(g.get("game_id"), x), []) if c.get("price") is not None]
            o = next((c for c in cands if c.get(line_key) == x.get(line_key)), None) or (cands[0] if len(cands) == 1 else None)
            if o is None:
                x["op"], x["ol"] = x["price"], x.get(line_key)
            else:
                x["op"] = o.get("op", o["price"])
                x["ol"] = o.get("ol", o.get(line_key))
            if x["op"] != x["price"] or x["ol"] != x.get(line_key):
                moved += 1
    return moved
