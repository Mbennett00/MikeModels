"""Market odds for the Pikt pages: DraftKings + FanDuel game lines and player props from SharpAPI's free tier.

python -m calib.odds [--state state]

calib.sharp pulls both books (SHARP_API_KEY). Game lines: the line both books hang, at their median price; between pulls
the last good lines stay, minus games that have started. Props: each rung at DraftKings' price (FanDuel's where
DraftKings has none), with a no-vig fair chance from the two books; misfiled period markets and rungs that break their
ladder are dropped (see calib.sharp). SharpAPI is the only odds source: ESPN is used for injuries and scores only.
Writes state/site/odds.json (kept with the state) and state/site/web/odds.json. Never raises: a failed pull keeps
the last good prices (props for KEEP_H hours), and the pages fall back to their own when a game has none.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import unicodedata

from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

PAGE = {"NHL": "data.json", "NBA": "nba.json", "NFL": "nfl.json"}


def nm(s: str) -> str:
    """Same key the pages use (book.js bkNm): accents off, suffixes off, letters only."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s)
    return re.sub(r"[^a-z]", "", s)


def upcoming(web: str, league: str) -> int:
    """Games on the league's page that haven't started."""
    try:
        d = json.load(open(os.path.join(web, PAGE[league])))
    except (OSError, ValueError):
        return 0
    now = dt.datetime.now(dt.timezone.utc)
    n = 0
    for g in d.get("games") or []:
        t = g.get("start_utc")
        if t and dt.datetime.fromisoformat(str(t).replace("Z", "+00:00")) > now and g.get("state") not in ("post", "in"):
            n += 1
    return n


LEAGUES = ("NHL", "NBA", "NFL")
KEEP_H = 12   # a league whose SharpAPI pull fails keeps its last props this long


def attach_gids(lines: dict, web: str, log=print):
    """Tie each consensus game to the page's game id (team names + start time), and say how many matched."""
    for lg, blob in (lines or {}).items():
        try:
            G = json.load(open(os.path.join(web, PAGE[lg]))).get("games") or []
        except (OSError, ValueError):
            continue
        def keys(t):
            return {nm(t.get("name")), nm(f"{t.get('city') or ''} {t.get('name') or ''}"), nm(t.get("abbr"))} - {""}
        hit = 0
        for x in blob.get("games") or []:
            fh, fa = nm(x.get("home")), nm(x.get("away"))
            tx = dt.datetime.fromisoformat(str(x.get("t")).replace("Z", "+00:00")) if x.get("t") else None
            for g in G:
                kh, ka = keys(g.get("home") or {}), keys(g.get("away") or {})
                if any(fh.endswith(k) for k in kh) and any(fa.endswith(k) for k in ka):
                    tg = g.get("start_utc")
                    if tx and tg and abs(dt.datetime.fromisoformat(str(tg).replace("Z", "+00:00")) - tx) > dt.timedelta(hours=18):
                        continue
                    x["gid"] = str(g.get("game_id")); hit += 1; break
        open_games = sum(1 for g in G if g.get("state") not in ("post", "in"))
        log(f"odds: {lg} market lines matched to {hit} page games ({open_games} on the page)")


def merge_sharp(out: dict, sh: dict, log=print):
    """SharpAPI's DraftKings + FanDuel pull -> the page's odds: each rung at DraftKings' price (FanDuel's where DraftKings
    has none, tagged in "bk"), "fair" the two-book no-vig chance, game lines the two books' consensus."""
    for lg, v in sh.items():
        if v["props"]:
            out["props"][lg] = {"book": "DraftKings" + (" + FanDuel" if v["bk"] else ""), "fetched_at": v["fetched_at"],
                                "players": v["props"], "bk": v["bk"], "fair": v["fair"]}
        if v["games"]:
            out["lines"][lg] = {"fetched_at": v["fetched_at"], "books": "DraftKings + FanDuel", "games": v["games"]}


def run(state: str = "state", log=print):
    site = os.path.join(state, "site"); web = os.path.join(site, "web")
    os.makedirs(web, exist_ok=True)
    p = os.path.join(site, "odds.json")
    try:
        prev = json.load(open(p))
    except (OSError, ValueError):
        prev = {}
    now = dt.datetime.now(dt.timezone.utc)
    out = {"lines": {}}
    for lg, L in (prev.get("lines") or {}).items():      # last good lines, minus games that have started
        keep = [g for g in L.get("games") or [] if g.get("t") and dt.datetime.fromisoformat(str(g["t"]).replace("Z", "+00:00")) > now]
        if keep:
            out["lines"][lg] = dict(L, games=keep)
    out["props"] = {}
    for lg, P in (prev.get("props") or {}).items():      # last good props, while recent (a failed pull doesn't blank the page)
        t = P.get("fetched_at")
        if t and P.get("fair") is not None and now - dt.datetime.fromisoformat(t) < dt.timedelta(hours=KEEP_H):
            out["props"][lg] = P
    from calib import sharp
    sh = sharp.pull(list(LEAGUES), os.environ.get("SHARP_API_KEY", ""), log)   # every league: the API only returns games to come
    out["sharp"] = {lg: {"fetched_at": v["fetched_at"], "complete": v["complete"], "games": len(v["games"]), "players": len(v["props"])} for lg, v in sh.items()}
    merge_sharp(out, sh, log)
    attach_gids(out.get("lines"), web, log)
    out["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    txt = json.dumps(out, separators=(",", ":"))
    for d in (site, web):
        with open(os.path.join(d, "odds.json"), "w") as f:
            f.write(txt)
    n = {lg: len(v.get("games") or []) for lg, v in (out.get("lines") or {}).items()}
    log(f"odds: lines {n} · props {[k for k in out['props']]}")


if __name__ == "__main__":
    a = argparse.ArgumentParser(prog="calib.odds")
    a.add_argument("--state", default="state")
    run(a.parse_args().state)
