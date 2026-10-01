"""MoneyPuck shot-level data (https://moneypuck.com/data.htm): their expected goals for every shot.

MoneyPuck's xG model sees every event (passes, carries, faceoffs, line changes), so it measures
rush chances, pre-shot movement and shooter handedness that our shot-only model can only proxy.
Files are season zips, refreshed by MoneyPuck overnight; we keep only the columns needed to attach
their xG to our shots. Data courtesy of MoneyPuck.com: credit them, and check their terms before any
commercial use.
"""
from __future__ import annotations

import io
import os
import time
import zipfile

import numpy as np
import pandas as pd
import requests

URL = "https://peter-tanner.com/moneypuck/downloads/shots_{season}.zip"
COLS = ["season", "game_id", "period", "time", "shooterPlayerId", "xGoal", "event", "isPlayoffGame"]
FILE = "mp_shots.csv.gz"


def fetch(seasons, path: str, refresh_current: bool = True, log=print) -> pd.DataFrame:
    """Download the given seasons (start years) into path/mp_shots.csv.gz, keeping stored past seasons."""
    f = os.path.join(path, FILE)
    old = pd.read_csv(f) if os.path.exists(f) else pd.DataFrame(columns=COLS)
    have = set(old.season.unique()) if len(old) else set()
    newest = max(seasons)
    parts = [old]
    for s in sorted(seasons):
        if s in have and not (refresh_current and s == newest):
            continue
        try:
            r = requests.get(URL.format(season=s), timeout=120, headers={"User-Agent": "Mozilla/5.0 (nhlmodel)"})
            r.raise_for_status()
            z = zipfile.ZipFile(io.BytesIO(r.content))
            d = pd.read_csv(z.open(z.namelist()[0]), usecols=lambda c: c in COLS)
            d = d[d.isPlayoffGame == 0] if "isPlayoffGame" in d else d
            parts = [p[p.season != s] for p in parts] + [d[COLS]]
            log(f"moneypuck shots {s}: {len(d)} rows")
            time.sleep(1)
        except Exception as e:   # optional source: keep what we have
            log(f"moneypuck shots {s}: {e}")
    parts = [p for p in parts if len(p)]
    out = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=COLS)
    for c in ("season", "game_id", "period", "time", "shooterPlayerId", "xGoal", "isPlayoffGame"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    os.makedirs(path, exist_ok=True)
    out.to_csv(f, index=False, compression="gzip")
    return out


def attach(shots: pd.DataFrame, mp: pd.DataFrame, tol: int = 2) -> pd.Series:
    """MoneyPuck xG for each of our unblocked shots (NaN when there is no match).

    Match on game, shooter and game second (within `tol` s). MoneyPuck game ids are the short form
    (20001); ours are season * 1e6 + that. MoneyPuck `time` is seconds since the start of the game.
    """
    out = pd.Series(np.nan, index=shots.index, dtype=float)
    if mp is None or mp.empty:
        return out
    m = mp.copy()
    for c in ("season", "game_id", "time", "shooterPlayerId", "xGoal"):
        m[c] = pd.to_numeric(m[c], errors="coerce")
    m = m.dropna(subset=["season", "game_id", "time", "shooterPlayerId", "xGoal"])
    m["gid"] = (m.season.astype(int) * 1_000_000 + m.game_id.astype(int)).astype("int64")
    m = m.rename(columns={"shooterPlayerId": "shooter"})[["gid", "shooter", "time", "xGoal"]].dropna()
    m["shooter"] = m.shooter.astype("int64")
    m["time"] = m.time.astype("int64")
    s = shots[shots.unblocked].reset_index()[["index", "game_id", "shooter", "t"]].dropna()
    s["gid"] = s.game_id.astype("int64"); s["shooter"] = s.shooter.astype("int64"); s["t"] = s.t.astype("int64")
    s, m = s.sort_values("t"), m.sort_values("time")
    j = pd.merge_asof(s, m, left_on="t", right_on="time", by=["gid", "shooter"], tolerance=tol, direction="nearest")
    out.loc[j["index"].to_numpy()] = j.xGoal.to_numpy(dtype=float)
    return out
