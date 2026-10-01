"""Static web page (GitHub Pages): data.json + index.html, rebuilt by every slate run.

No server: the page is plain HTML/CSS/JS. Everything the Check calculator needs is exported —
each game's final-score probability matrix and each player's projected rates — so any line can
be priced in the browser.
"""
from __future__ import annotations

import json
import math
import os
import shutil

import numpy as np
import pandas as pd

from .data.teams import DISPLAY
from .player_model import project_team_players
from .team_model import TeamModel

HERE = os.path.dirname(__file__)
ESPN_ABBR = {"LAK": "la", "NJD": "nj", "SJS": "sj", "TBL": "tb", "UTA": "utah"}
MARKET_LAM = {"goals": "goals", "sog": "sog", "assists": "assists", "points": "points"}


def _num(x, nd=4):
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else round(f, nd)


def _mat(m, cut=1e-7):
    m = np.asarray(m, float)
    keep = np.where(m.sum(0) + m.sum(1) > cut)[0]
    n = int(keep.max()) + 1 if len(keep) else 1
    return [[round(float(v), 7) for v in row[:n]] for row in m[:n]]


def build(state, plays: pd.DataFrame, meta: dict, news: dict | None, images: dict | None,
          market_summary: pd.DataFrame | None, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    news, images = news or {}, images or {}
    if state is None:   # no games scheduled: still publish a page that says so
        _write(out_dir, dict(meta=dict(date=meta.get("date"), upcoming=bool(meta.get("upcoming")),
                                       generated_at=meta.get("generated_at"), games=0, goalies_confirmed=0, teams=0),
                             params={}, games=[], players=[], lines=[], trust=_trust(market_summary)))
        return out_dir
    lu = state.lineups
    tm = TeamModel(state.cfg, state.snap, state.params)
    inj = news.get("injuries", [])
    logos = images.get("logos", {})
    faces = images.get("headshots", {})
    games, gp_by = [], {}
    for g in state.schedule.itertuples():
        side = {}
        for team in (g.away, g.home):
            gl = lu[(lu.team == team) & (lu.pos == "G")]
            status = ""
            if len(gl):
                status = gl.status.iloc[0] if "status" in gl and isinstance(gl.status.iloc[0], str) and gl.status.iloc[0] \
                    else ("Confirmed" if bool(gl.confirmed.iloc[0]) else "Projected")
            side[team] = dict(
                abbr=team, name=DISPLAY.get(team, (team, "#888"))[0], color=DISPLAY.get(team, (team, "#888"))[1],
                logo=logos.get(team) or f"https://a.espncdn.com/i/teamlogos/nhl/500/{ESPN_ABBR.get(team, team.lower())}.png",
                goalie=str(gl.name.iloc[0]) if len(gl) else "", goalie_status=status,
                goalie_id=int(gl.player_id.iloc[0]) if len(gl) else None,
                goalie_confirmed=bool(gl.confirmed.iloc[0]) if len(gl) else False,
                injuries=[dict(name=i["name"], status=i["status"]) for i in inj if i["team"] == team])
        a, h = side[g.away], side[g.home]
        gp = tm.project(g.home, g.away, h["goalie_id"], a["goalie_id"], state.date,
                        (h["goalie_confirmed"], a["goalie_confirmed"]))
        gp_by[int(g.game_id)] = gp
        games.append(dict(game_id=int(g.game_id), start_utc=getattr(g, "start_utc", None), away=a, home=h,
                          mx=_matchup(tm, gp, g.home, g.away),
                          lam_home=_num(gp.lam_home), lam_away=_num(gp.lam_away), p_ot_home=_num(gp.p_ot_home),
                          reg=_mat(gp.matrix), p1=_mat(gp.p1_matrix)))
    players = []
    pp = plays[(plays.player.fillna("") != "") & (plays.selection == "over")] if len(plays) else plays
    for pid, d in (pp.groupby("player_id") if len(pp) else []):
        r0 = d.iloc[0]
        lam = {m: _num(pd.to_numeric(d[d.market == m].projection, errors="coerce").iloc[0])
               for m in MARKET_LAM if (d.market == m).any()}
        players.append(dict(id=int(pid), name=r0.player, team=r0.team, pos=r0.get("pos", "F"),
                            game_id=int(r0.game_id), confirmed=bool(r0.confirmed),
                            headshot=faces.get(str(int(pid))) or (r0.headshot if isinstance(r0.get("headshot"), str) else ""),
                            lam=lam))
    # per-player matchup effect (tonight vs an average opponent at a neutral rink) for the rink view
    mxp = {}
    for g in state.schedule.itertuples():
        gp = gp_by[int(g.game_id)]
        for side, team in (("home", g.home), ("away", g.away)):
            try:
                df, _ = project_team_players(tm, gp, side, lu[lu.team == team], state.params, state.cfg)
            except Exception:
                continue
            for r in df.itertuples():
                mxp[int(r.player_id)] = (_num(r.mx_pts - 1), _num(r.mx_sog - 1))
    lines = []
    for r in lu[lu.pos != "G"].itertuples():
        pid = int(r.player_id) if pd.notna(r.player_id) else None
        mp, ms = mxp.get(pid, (None, None))
        lines.append(dict(team=r.team, name=r.name, pos=r.pos, line=r.line, pp=int(r.pp_unit or 0), id=pid,
                          mx_pts=mp, mx_sog=ms))
    P = state.params
    data = dict(
        meta=dict(date=meta.get("date"), upcoming=bool(meta.get("upcoming")), generated_at=meta.get("generated_at"),
                  games=len(games), goalies_confirmed=int(sum(g[s]["goalie_confirmed"] for g in games
                                                              for s in ("home", "away"))),
                  teams=2 * len(games), constants=meta.get("constants", "")),
        params=dict(r_sog=P.nb_r.get("sog", {}), r_ast=P.count_r.get("assists", 1e6),
                    r_pts=P.count_r.get("points", 1e6), thresholds=state.cfg.edge_threshold),
        games=games, players=players, lines=lines, trust=_trust(market_summary))
    _write(out_dir, data)
    return out_dir


def _matchup(tm, gp, home, away) -> dict:
    """Per-team strengths behind the projection, as multipliers vs league average (1 = average).

    Defence, goalie and penalty kill are 'goals allowed' multipliers (lower is better); the page flips
    them so every row reads 'higher = better for that team'."""
    f = gp.factors
    out = {}
    for side, team, opp_side in (("home", home, "away"), ("away", away, "home")):
        r = tm.rating(team)
        out[side] = dict(off=_num(r.off), dfn=_num(r.dfn), pp=_num(r.pp_off), pk=_num(r.pk_def),
                         gk=_num(f[opp_side]["goalie_opp"]),      # this team's goalie, faced by the opponent
                         ppc=_num(f[side]["pp_time"]),            # this team's expected power-play chances
                         rest=_num(f[side]["rest"]), home=_num(f[side]["home"]), lam=_num(f[side]["lam"]))
    out["pace"] = _num(f["home"]["pace"])
    out["league_gpg"] = _num(tm.snap.league["goals_pg"])
    return out


def _trust(market_summary) -> list:
    if market_summary is None or not len(market_summary):
        return []
    ms = market_summary[market_summary.line.astype(str) == "all"]
    return [dict(market=r.market, n=int(r.n), status=str(r.status)) for r in ms.itertuples()]


def _write(out_dir: str, data: dict):
    data.setdefault("colors", {k: v[1] for k, v in DISPLAY.items()})
    with open(os.path.join(out_dir, "data.json"), "w") as f:
        json.dump(data, f, separators=(",", ":"), default=str, allow_nan=False)
    shutil.copy(os.path.join(HERE, "web_template.html"), os.path.join(out_dir, "index.html"))
    for name in os.listdir(os.path.join(HERE, "web_assets")):   # home-screen icons
        shutil.copy(os.path.join(HERE, "web_assets", name), os.path.join(out_dir, name))
    with open(os.path.join(out_dir, "manifest.webmanifest"), "w") as f:
        json.dump(dict(name="NHL Model", short_name="NHL Model", start_url=".", display="standalone",
                       background_color="#bfe0f2", theme_color="#bfe0f2",
                       icons=[dict(src="icon-192.png", sizes="192x192", type="image/png"),
                              dict(src="icon-512.png", sizes="512x512", type="image/png")]), f)
    open(os.path.join(out_dir, ".nojekyll"), "w").close()
