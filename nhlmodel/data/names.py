"""Matching player names from outside feeds (Daily Faceoff, sportsbooks) to NHL ids."""
from __future__ import annotations

import pandas as pd

from .teams import norm_name


def player_index(roster: pd.DataFrame) -> dict:
    """Name -> NHL id. Adds 'first-initial + last name' keys when unique, so 'Christopher Tanev'
    finds 'Chris Tanev' and 'Alex Romanov' finds 'Alexander Romanov'."""
    idx = {norm_name(n): p for n, p in zip(roster.name, roster.player_id)}
    alt: dict = {}
    for n, p in zip(roster.name, roster.player_id):
        parts = norm_name(n).split()
        if len(parts) >= 2:
            alt.setdefault(f"{parts[0][0]} {parts[-1]}", set()).add(p)
    for k, v in alt.items():
        if len(v) == 1:
            idx.setdefault(k, next(iter(v)))
    return idx


# common transliteration / short-name variants between sportsbooks and the NHL
FIRST_ALIASES = {"yegor": "egor", "egor": "yegor", "evgeny": "evgeni", "evgeni": "evgeny", "yevgeni": "evgeni",
                 "alexander": "alexandre", "alexandre": "alexander", "alex": "alexander", "nikolai": "nikolay",
                 "nikolay": "nikolai", "mitch": "mitchell", "mitchell": "mitch", "matt": "matthew", "matthew": "matt",
                 "zach": "zachary", "zachary": "zach", "josh": "joshua", "joshua": "josh", "jake": "jacob",
                 "jacob": "jake", "nick": "nicholas", "nicholas": "nick", "mike": "michael", "michael": "mike"}


def lookup(idx: dict, name: str):
    n = norm_name(name)
    if n in idx:
        return idx[n]
    parts = n.split()
    if len(parts) < 2:
        return None
    alt = FIRST_ALIASES.get(parts[0])
    if alt and f"{alt} {' '.join(parts[1:])}" in idx:
        return idx[f"{alt} {' '.join(parts[1:])}"]
    return idx.get(f"{parts[0][0]} {parts[-1]}")
