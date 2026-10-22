"""Market odds for the Pikt pages: DraftKings + FanDuel game lines and player props from SharpAPI's free tier.

python -m calib.odds [--state state]

calib.sharp pulls both books (SHARP_API_KEY). Game lines: the line both books hang, at their median price; between pulls
the last good lines stay, minus games that have started. Props: each rung at DraftKings' price (FanDuel's where
DraftKings has none), with a no-vig fair chance from the two books; misfiled period markets and rungs that break their
ladder are dropped (see calib.sharp). SharpAPI is the only odds source: ESPN is used for injuries and scores only.
Writes state/site/odds.json (kept with the state) and state/site/web/odds.json. Never raises: a failed pull keeps
the last good prices (props for KEEP_H hours), and the pages fall back to their own when a game has none.

Line history (odds_hist.json): every run snapshots each game's consensus line, so the pages can show the opener, the
current line and how it got there. A snapshot is kept only when something moved. --lines-only pulls the game lines
alone (a few calls) for the hourly snapshots between the full runs, leaving the props as they were.
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
HIST_DAYS = 2     # a game's line history is kept this long after it starts
HIST_MAX = 160    # snapshots per game at most (the opener always stays)


def hist_key(g: dict) -> str:
    """One game across runs: the two teams and the day (ET) it starts."""
    t = str(g.get("t") or "")
    day = dt.datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(ET).date().isoformat() if t else ""
    return f"{nm(g.get('away'))}@{nm(g.get('home'))}|{day}"


def snap(g: dict) -> list:
    """[spread home, home price, away price, total, over, under, ml home, ml away] (None where a market is missing)."""
    sp, to, ml = g.get("spread") or {}, g.get("total") or {}, g.get("ml") or {}
    return [sp.get("home"), sp.get("home_price"), sp.get("away_price"), to.get("line"), to.get("over"), to.get("under"),
            ml.get("home"), ml.get("away")]


def update_hist(hist: dict, lines: dict, now: dt.datetime) -> dict:
    """Add this pull's lines to the history: {league: {key: {away, home, t, gid, s: [[unix minute, *snap]]}}}."""
    tm = int(now.timestamp() // 60)
    cut = now - dt.timedelta(days=HIST_DAYS)
    out = {}
    for lg, G in (hist or {}).items():          # games that started more than HIST_DAYS ago drop off
        keep = {k: v for k, v in G.items() if v.get("t") and dt.datetime.fromisoformat(str(v["t"]).replace("Z", "+00:00")) > cut}
        if keep:
            out[lg] = keep
    for lg, L in (lines or {}).items():
        for g in L.get("games") or []:
            if not g.get("t") or dt.datetime.fromisoformat(str(g["t"]).replace("Z", "+00:00")) <= now:
                continue                         # lines close at the start
            v = snap(g)
            if all(x is None for x in v):
                continue
            e = out.setdefault(lg, {}).setdefault(hist_key(g), {"away": g.get("away"), "home": g.get("home"), "s": []})
            e["t"] = g["t"]
            if g.get("gid"):
                e["gid"] = g["gid"]
            if not e["s"] or e["s"][-1][1:] != v:
                e["s"].append([tm] + v)
                if len(e["s"]) > HIST_MAX:
                    e["s"] = e["s"][:1] + e["s"][-(HIST_MAX - 1):]
            e["seen"] = tm                       # last pull that saw the game (the chart runs to here)
    return out


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


def run(state: str = "state", log=print, lines_only: bool = False):
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
        if t and P.get("fair") is not None and (lines_only or now - dt.datetime.fromisoformat(t) < dt.timedelta(hours=KEEP_H)):
            out["props"][lg] = P
    from calib import sharp
    sh = sharp.pull(list(LEAGUES), os.environ.get("SHARP_API_KEY", ""), log, props=not lines_only)   # every league: the API only returns games to come
    if lines_only:
        out["sharp"] = prev.get("sharp") or {}
        for v in sh.values():
            v["props"] = {}                      # merge_sharp keeps the props already there
    else:
        out["sharp"] = {lg: {"fetched_at": v["fetched_at"], "complete": v["complete"], "games": len(v["games"]), "players": len(v["props"])} for lg, v in sh.items()}
    merge_sharp(out, sh, log)
    attach_gids(out.get("lines"), web, log)
    out["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    txt = json.dumps(out, separators=(",", ":"))
    for d in (site, web):
        with open(os.path.join(d, "odds.json"), "w") as f:
            f.write(txt)
    hp = os.path.join(site, "odds_hist.json")
    try:
        hist = json.load(open(hp))
    except (OSError, ValueError):
        hist = {}
    fresh = {lg: out["lines"][lg] for lg in sh if lg in out.get("lines", {})}   # only what this pull saw: kept lines aren't news
    hist = update_hist(hist, fresh, now)
    txt = json.dumps(hist, separators=(",", ":"))
    for d in (site, web):
        with open(os.path.join(d, "odds_hist.json"), "w") as f:
            f.write(txt)
    n = {lg: len(v.get("games") or []) for lg, v in (out.get("lines") or {}).items()}
    nh = sum(len(G) for G in hist.values()); ns = sum(len(e["s"]) for G in hist.values() for e in G.values())
    log(f"odds: lines {n} · props {[k for k in out['props']]} · history {nh} games, {ns} snapshots{' (lines only)' if lines_only else ''}")


if __name__ == "__main__":
    a = argparse.ArgumentParser(prog="calib.odds")
    a.add_argument("--state", default="state")
    a.add_argument("--lines-only", action="store_true", help="game lines only (hourly snapshots); props stay as they were")
    x = a.parse_args()
    run(x.state, lines_only=x.lines_only)
