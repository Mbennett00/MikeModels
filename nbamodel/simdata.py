"""What the NBA game simulator plays from: full box scores from ESPN's game summaries, cached in the state.

The model's own box scores keep minutes, points, rebounds, assists and threes; the sim also needs how those points are
made. So the most recent completed games (regular season and playoffs, plus this season's preseason at a lower
weight) get their full box score once, and from it, every rate shrunk toward the league:

  league   possessions per 48, and per possession: turnovers (and the share that are steals), field-goal tries, the
           share from three, free throws per try, shooting on twos, threes and free throws, offensive rebound rate,
           assisted share of makes, blocks per missed two, personal fouls
  teams    pace, three-point share, free-throw rate, turnover rate, offensive / defensive rebound rates, shooting on
           twos and threes, and what they allow: opponents' shooting, turnovers forced, steals and blocks
  players  minutes and starts, and per 36 minutes: twos and threes tried and made, free throws tried and made,
           offensive and defensive rebounds, assists, turnovers, steals, blocks, fouls

python -m nbamodel.simdata [--state state]   ->  state/site/nba_sim.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
UA = {"User-Agent": "Mozilla/5.0 (Pikt sim)"}
N_GAMES = 520          # the most recent completed games kept (about 35 per team)
NEW_PER_RUN = 260      # box scores fetched in one run at most (the cache fills over a few runs)
PRE_W = 0.35           # a preseason game counts this much
COLS = ("min", "pts", "fgm", "fga", "tpm", "tpa", "ftm", "fta", "oreb", "dreb", "ast", "tov", "stl", "blk", "pf")


def _split(v):
    try:
        a, b = str(v).split("-")[:2]
        return float(a), float(b)
    except ValueError:
        return float("nan"), float("nan")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def parse_full(js: dict) -> list[dict]:
    """Game summary -> one row per player who played, with the full box line."""
    out = []
    for team in (js.get("boxscore") or {}).get("players", []):
        ab = (team.get("team") or {}).get("abbreviation", "")
        for grp in team.get("statistics", []):
            lab = [str(x).upper() for x in grp.get("labels", [])]
            if "MIN" not in lab or "FG" not in lab:
                continue
            ix = {k: lab.index(k) for k in lab}
            for a in grp.get("athletes", []):
                st, ath = a.get("stats") or [], a.get("athlete") or {}
                if not st or a.get("didNotPlay"):
                    continue
                g = lambda k: st[ix[k]] if k in ix and ix[k] < len(st) else None
                mins = _num(g("MIN"))
                if not mins or mins != mins or mins <= 0:
                    continue
                fgm, fga = _split(g("FG")); tpm, tpa = _split(g("3PT")); ftm, fta = _split(g("FT"))
                out.append(dict(team=ab, id=str(ath.get("id", "")), name=ath.get("displayName", ""), starter=bool(a.get("starter")),
                                min=mins, pts=_num(g("PTS")), fgm=fgm, fga=fga, tpm=tpm, tpa=tpa, ftm=ftm, fta=fta,
                                oreb=_num(g("OREB")), dreb=_num(g("DREB")), ast=_num(g("AST")), tov=_num(g("TO")),
                                stl=_num(g("STL")), blk=_num(g("BLK")), pf=_num(g("PF"))))
    return out


def fetch_boxes(games: pd.DataFrame, cache: dict, log=print) -> dict:
    todo = [str(g) for g in games.game_id if str(g) not in cache][:NEW_PER_RUN]
    def one(gid):
        try:
            r = requests.get(f"{SITE}/summary", params={"event": gid}, headers=UA, timeout=25)
            return gid, parse_full(r.json()) if r.ok else None
        except Exception:
            return gid, None
    got = 0
    with ThreadPoolExecutor(8) as ex:
        for gid, rows in ex.map(one, todo):
            if rows:
                cache[gid] = rows; got += 1
    if todo:
        log(f"nba sim: fetched {got} of {len(todo)} new box scores")
    return cache


def _shrink(num, den, prior, k):
    return float((num + prior * k) / (den + k)) if den + k > 0 else float(prior)


def build(games: pd.DataFrame, cache: dict, season: int) -> dict:
    rows = []
    for g in games.itertuples():
        for r in cache.get(str(g.game_id)) or []:
            side = "home" if r["team"] == g.home else "away" if r["team"] == g.away else None
            if side:
                rows.append(dict(r, game_id=str(g.game_id), side=side, w=PRE_W if str(g.season_type) == "1" else 1.0,
                                 opp=g.away if side == "home" else g.home, date=g.date))
    P = pd.DataFrame(rows)
    if P.empty:
        return {}
    for c in COLS:
        P[c] = pd.to_numeric(P[c], errors="coerce").fillna(0.0)
    # team-games: totals, and the opponent's in the same game
    T = P.groupby(["game_id", "team", "opp", "w"], as_index=False)[list(COLS)].sum()
    T = T.merge(T[["game_id", "team"] + list(COLS)].rename(columns={"team": "opp", **{c: "o_" + c for c in COLS}}), on=["game_id", "opp"])
    T["poss"] = T.fga + 0.44 * T.fta - T.oreb + T.tov
    T["o_poss"] = T.o_fga + 0.44 * T.o_fta - T.o_oreb + T.o_tov
    T["pace"] = 0.5 * (T.poss + T.o_poss) * 240 / T["min"].clip(lower=200)
    w = T.w
    S = lambda c: float((T[c] * w).sum())
    poss, fga, fta, tpa = S("poss"), S("fga"), S("fta"), S("tpa")
    fg2a, fg2m = fga - tpa, S("fgm") - S("tpm")
    lg = dict(pace=float((T.pace * w).sum() / w.sum()), tov=S("tov") / poss, stl_share=S("stl") / max(1, S("o_tov")),
              fga=fga / poss, three=tpa / fga, ftr=fta / fga, fg2=fg2m / fg2a, fg3=S("tpm") / tpa, ft=S("ftm") / fta,
              orb=S("oreb") / (S("oreb") + S("o_dreb")), ast=S("ast") / S("fgm"), blk=S("o_blk") / max(1, fg2a - fg2m),
              pf=S("pf") / poss, pts=S("pts") / w.sum())
    teams = {}
    for ab, d in T.groupby("team"):
        d = d.sort_values("game_id").tail(40); w = d.w; s = lambda c: float((d[c] * w).sum())
        po, opo = s("poss"), s("o_poss")
        f2a, f2m, of2a, of2m = s("fga") - s("tpa"), s("fgm") - s("tpm"), s("o_fga") - s("o_tpa"), s("o_fgm") - s("o_tpm")
        teams[ab] = dict(
            n=round(float(w.sum()), 1),
            pace=_shrink(float((d.pace * w).sum()), float(w.sum()), lg["pace"], 8) / lg["pace"],
            three=_shrink(s("tpa"), s("fga"), lg["three"], 400) / lg["three"],
            ftr=_shrink(s("fta"), s("fga"), lg["ftr"], 500) / lg["ftr"],
            tov=_shrink(s("tov"), po, lg["tov"], 600) / lg["tov"],
            orb=_shrink(s("oreb"), s("oreb") + s("o_dreb"), lg["orb"], 300) / lg["orb"],
            drb=_shrink(s("dreb"), s("dreb") + s("o_oreb"), 1 - lg["orb"], 300) / (1 - lg["orb"]),
            fg2=_shrink(f2m, f2a, lg["fg2"], 600) / lg["fg2"], fg3=_shrink(s("tpm"), s("tpa"), lg["fg3"], 500) / lg["fg3"],
            ast=_shrink(s("ast"), s("fgm"), lg["ast"], 300) / lg["ast"],
            # defence: what opponents do against them
            d_fg2=_shrink(of2m, of2a, lg["fg2"], 600) / lg["fg2"], d_fg3=_shrink(s("o_tpm"), s("o_tpa"), lg["fg3"], 500) / lg["fg3"],
            d_tov=_shrink(s("o_tov"), opo, lg["tov"], 600) / lg["tov"], d_three=_shrink(s("o_tpa"), s("o_fga"), lg["three"], 400) / lg["three"],
            d_ftr=_shrink(s("o_fta"), s("o_fga"), lg["ftr"], 500) / lg["ftr"],
            stl=_shrink(s("stl"), s("o_tov"), lg["stl_share"], 200) / lg["stl_share"],
            blk=_shrink(s("blk"), max(1.0, of2a - of2m), lg["blk"], 300) / lg["blk"])
    players = {}
    for pid, d in P.groupby("id"):
        d = d.sort_values("date").tail(60); w = d.w; s = lambda c: float((d[c] * w).sum())
        mins = s("min")
        if mins < 30:
            continue
        per = lambda c: round(36 * s(c) / mins, 2)
        f2a, f2m = s("fga") - s("tpa"), s("fgm") - s("tpm")
        players[str(pid)] = dict(
            name=str(d.name.iloc[-1]), team=str(d.team.iloc[-1]), g=round(float(w.sum()), 1), min=round(mins / float(w.sum()), 1),
            start=round(float((d.starter.astype(float) * w).sum() / w.sum()), 2),
            f2a=round(36 * f2a / mins, 2), f3a=per("tpa"), fta=per("fta"),
            fg2=round(_shrink(f2m, f2a, lg["fg2"], 60), 3), fg3=round(_shrink(s("tpm"), s("tpa"), lg["fg3"], 80), 3),
            ft=round(_shrink(s("ftm"), s("fta"), lg["ft"], 30), 3),
            oreb=per("oreb"), dreb=per("dreb"), ast=per("ast"), tov=per("tov"), stl=per("stl"), blk=per("blk"), pf=per("pf"))
    return dict(built=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), season=season, games=int(T.game_id.nunique()),
                league={k: round(v, 4) for k, v in lg.items()}, teams={k: {a: round(b, 3) for a, b in v.items()} for k, v in teams.items()},
                players=players)


def run(state: str = "state", log=print) -> dict | None:
    site = os.path.join(state, "site")
    gp = os.path.join(site, "nba_games.csv.gz")
    if not os.path.exists(gp):
        log("nba sim: no games yet"); return None
    G = pd.read_csv(gp, dtype={"game_id": str})
    G = G[G.state == "post"].copy()
    season = int(G.season.max())
    G = G[(G.season_type.astype(str).isin(["2", "3"])) | ((G.season_type.astype(str) == "1") & (G.season == season))]
    G = G.sort_values("start_utc").tail(N_GAMES)
    cp = os.path.join(site, "nba_sim_box.json")
    try:
        cache = json.load(open(cp))
    except (OSError, ValueError):
        cache = {}
    cache = fetch_boxes(G.iloc[::-1], cache, log)          # newest first
    cache = {k: v for k, v in cache.items() if k in set(G.game_id.astype(str))}
    with open(cp, "w") as f:
        json.dump(cache, f, separators=(",", ":"))
    out = build(G, cache, season)
    if not out:
        log("nba sim: no box scores yet"); return None
    for d in (site, os.path.join(site, "web")):
        if os.path.isdir(d):
            with open(os.path.join(d, "nba_sim.json"), "w") as f:
                json.dump(out, f, separators=(",", ":"))
    log(f"nba sim: {len(out['teams'])} teams, {len(out['players'])} players from {out['games']} games · pace {out['league']['pace']:.1f}")
    return out


if __name__ == "__main__":
    a = argparse.ArgumentParser(prog="nbamodel.simdata")
    a.add_argument("--state", default="state")
    run(a.parse_args().state, log=print)
