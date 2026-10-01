"""What changed in the model since the last run, in plain words, for the web page's Updates tab.

Each slate run saves a small snapshot (data window, fitted parameters, team strengths, goalies,
injuries, headline prices, market trust) to site/model_log.json and lists what moved since the
previous snapshot. Only changes big enough to matter are listed.
"""
from __future__ import annotations

import json
import os

import pandas as pd

from .data.teams import DISPLAY
from .team_model import TeamModel

KEEP = 60   # snapshots kept

# (key, label, how to show it, smallest change worth listing)
PARAMS = [
    ("goals_pg", "League goals per game", lambda v: f"{v:.2f}", 0.01),
    ("home_edge", "Home-ice edge", lambda v: f"{100 * v:+.1f}%", 0.001),
    ("lam_scale", "League scoring calibration", lambda v: f"{v:.3f}", 0.002),
    ("lam3", "Score correlation between teams", lambda v: f"{v:.3f}", 0.005),
    ("ot_slope", "Overtime / shootout model", lambda v: f"{v:.2f}", 0.01),
    ("p1_share", "Share of goals in the 1st period", lambda v: f"{100 * v:.1f}%", 0.002),
    ("en_uplift", "Empty-net goal bump", lambda v: f"{100 * (v - 1):+.1f}%", 0.002),
    ("r_sog_F", "Shot-count spread (forwards)", lambda v: f"{v:.1f}", 0.3),
    ("r_sog_D", "Shot-count spread (defence)", lambda v: f"{v:.1f}", 0.3),
    ("b2b_off", "Back-to-back scoring effect", lambda v: "none" if v == 1 else f"{100 * (v - 1):+.1f}%", 0.001),
    ("b2b_def", "Back-to-back defence effect", lambda v: "none" if v == 1 else f"{100 * (v - 1):+.1f}%", 0.001),
    ("half_life", "Recent-form window (half-life)", lambda v: f"{v:.0f} games", 0.5),
    ("lineup_beta", "Injury / lineup adjustment strength", lambda v: "off" if v == 0 else f"{v:.2f}", 0.01),
    ("prior_w", "Weight on last season", lambda v: f"{100 * v:.0f}%", 0.01),
]
RECAL = {"goals": "Goal props", "sog": "Shot props", "assists": "Assist props"}


def snapshot(state, plays: pd.DataFrame, news: dict | None, meta: dict, market_summary: pd.DataFrame | None) -> dict:
    P, L, cfg = state.params, state.snap.league, state.cfg
    params = dict(goals_pg=L["goals_pg"], home_edge=L["home_ratio"] - 1, lam_scale=P.lam_scale, lam3=P.lam3,
                  ot_slope=P.ot_slope, p1_share=P.p1_share, en_uplift=P.en_uplift,
                  r_sog_F=P.nb_r.get("sog", {}).get("F"), r_sog_D=P.nb_r.get("sog", {}).get("D"),
                  b2b_off=P.rest.get("b2b_off", 1.0), b2b_def=P.rest.get("b2b_def", 1.0),
                  half_life=cfg.half_life_games, prior_w=cfg.prior_season_weight,
                  lineup_beta=getattr(cfg, "lineup_beta", 0.0))
    recal = {k: [round(float(x), 3) for x in v[:2]] for k, v in getattr(P, "recal", {}).items()}
    tm = TeamModel(cfg, state.snap, P)
    teams = {}
    for t in state.snap.team.index:
        try:
            r = tm.rating(t)
            teams[t] = dict(off=round(r.off, 4), dfn=round(r.dfn, 4), pp=round(r.pp_off, 4), pk=round(r.pk_def, 4))
        except Exception:
            continue
    news = news or {}
    goalies = {t: [g.get("goalie"), g.get("status")] for t, g in news.get("goalies", {}).items()}
    injuries = sorted(f"{i['team']}|{i['name']}|{i['status']}" for i in news.get("injuries", []))
    prices = {}
    if len(plays):
        gl = plays[plays.player.fillna("") == ""]
        for gid, d in gl.groupby("game_id"):
            def p(m, s, ln=None):
                x = d[(d.market == m) & (d.selection == s) & ((d.line == ln) if ln is not None else True)]
                return round(float(x.p_model.iloc[0]), 4) if len(x) else None
            prices[str(int(gid))] = dict(matchup=str(d.matchup.iloc[0]), ml_home=p("moneyline", "home"),
                                         over65=p("total", "over", 6.5))
    trust = {}
    if market_summary is not None and len(market_summary):
        ms = market_summary[market_summary.line.astype(str) == "all"]
        trust = {r.market: str(r.status) for r in ms.itertuples()}
    return dict(time=pd.Timestamp.now(tz="America/New_York").isoformat(), slate=meta.get("date"),
                data_through=meta.get("data_through"), constants=meta.get("constants"),
                params={k: (None if v is None else round(float(v), 4)) for k, v in params.items()},
                recal=recal, teams=teams, goalies=goalies, injuries=injuries, prices=prices, trust=trust)


def _nick(t):
    return DISPLAY.get(t, (t,))[0]


def diff(prev: dict | None, cur: dict) -> list[dict]:
    """Plain-language list of what moved between two snapshots: [{kind, icon, text}]."""
    if not prev:
        return [dict(kind="model", icon="🟢", text="Started tracking model changes. Updates will show here after each run.")]
    out = []
    add = lambda kind, icon, text: out.append(dict(kind=kind, icon=icon, text=text))
    if cur.get("data_through") and cur["data_through"] != prev.get("data_through"):
        add("data", "📥", f"New results loaded: games through {pd.Timestamp(cur['data_through']):%b %-d}. "
                           "Team and player ratings refreshed.")
    if cur.get("slate") != prev.get("slate"):
        add("data", "📅", f"New slate: {pd.Timestamp(cur['slate']):%a %b %-d}.")
    if cur.get("constants") != prev.get("constants"):
        add("model", "🎛️", f"Tuned settings changed ({cur.get('constants')}).")
    pp, cp = prev.get("params", {}), cur.get("params", {})
    for key, label, fmt, tol in PARAMS:
        a, b = pp.get(key), cp.get(key)
        if a is not None and b is not None and abs(b - a) >= tol:
            add("model", "⚙️", f"{label}: {fmt(a)} → {fmt(b)}")
    for k, lab in RECAL.items():
        a, b = prev.get("recal", {}).get(k), cur.get("recal", {}).get(k)
        if a and b and max(abs(x - y) for x, y in zip(a, b)) >= 0.01:
            add("model", "🎯", f"{lab} recalibrated on the latest results (level {a[0]:.2f} → {b[0]:.2f}, "
                               f"spread {a[1]:.2f} → {b[1]:.2f})")
    # biggest team-strength movers (attack / defence, 5-on-5)
    moves = []
    for t, c in cur.get("teams", {}).items():
        p = prev.get("teams", {}).get(t)
        if not p:
            continue
        for k, lab, sign in (("off", "attack", 1), ("dfn", "defence", -1), ("pp", "power play", 1), ("pk", "penalty kill", -1)):
            d = sign * (c[k] - p[k])
            if abs(d) >= 0.01:
                moves.append((abs(d), f"{t} {lab} {'+' if d > 0 else '−'}{abs(100 * d):.0f}%"))
    if moves:
        moves.sort(reverse=True)
        add("teams", "📈", "Biggest team-strength moves: " + ", ".join(m for _, m in moves[:5]))
    for t, (g, st) in cur.get("goalies", {}).items():
        pg = prev.get("goalies", {}).get(t)
        if not pg or cur.get("slate") != prev.get("slate"):
            continue
        if pg[0] != g:
            add("goalie", "🥅", f"{_nick(t)} goalie change: {pg[0] or 'TBD'} → {g or 'TBD'} ({st or 'projected'})")
        elif pg[1] != st:
            add("goalie", "🥅", f"{_nick(t)}: {g} {pg[1] or 'projected'} → {st or 'projected'}")
    if cur.get("slate") == prev.get("slate"):
        pi, ci = set(prev.get("injuries", [])), set(cur.get("injuries", []))
        for x in sorted(ci - pi):
            t, n, s = x.split("|")
            add("injury", "🚑", f"{_nick(t)}: {n} listed {s}")
        for x in sorted(pi - ci):
            t, n, s = x.split("|")
            if not any(y.startswith(f"{t}|{n}|") for y in ci):
                add("injury", "✅", f"{_nick(t)}: {n} no longer on the injury list")
        for gid, c in cur.get("prices", {}).items():
            p = prev.get("prices", {}).get(gid)
            if not p:
                continue
            home = c["matchup"].split(" @ ")[-1]
            for k, lab in (("ml_home", f"{home} win"), ("over65", "over 6.5 goals")):
                if c.get(k) is not None and p.get(k) is not None and abs(c[k] - p[k]) >= 0.015:
                    add("price", "💲", f"{c['matchup']}: {lab} {100 * p[k]:.0f}% → {100 * c[k]:.0f}%")
    for m, st in cur.get("trust", {}).items():
        if prev.get("trust", {}).get(m) not in (None, st):
            add("model", "🧪", f"{m.replace('_', ' ').title()} market: {prev['trust'][m]} → {st} after the latest backtest")
    return out


def update(site: str, state, plays, news, meta, market_summary) -> list[dict]:
    """Append this run to site/model_log.json and return the feed (newest first) for the page."""
    f = os.path.join(site, "model_log.json")
    try:
        log = json.load(open(f)) if os.path.exists(f) else []
    except (ValueError, OSError):
        log = []
    cur = snapshot(state, plays, news, meta, market_summary)
    prev = log[-1]["snap"] if log else None
    items = diff(prev, cur)
    log.append(dict(snap=cur, items=items))
    log = log[-KEEP:]
    with open(f, "w") as fh:
        json.dump(log, fh, separators=(",", ":"), default=str)
    return feed(log)


def feed(log: list) -> list[dict]:
    """Runs that changed something, newest first, plus the current settings."""
    runs = [dict(time=e["snap"]["time"], items=e["items"]) for e in log if e.get("items")][::-1][:30]
    return runs
