"""What changed in the NFL model since the last run, in plain words, for the page's Updates tab.

Each run saves a small snapshot (data window, odds pull, each game's model and market numbers, injury statuses,
starting QBs) to site/nfl_log.json and lists what moved since the previous snapshot.
"""
from __future__ import annotations

import json
import os

import pandas as pd

KEEP = 80


def _sp(home: str, away: str, margin: float) -> str:
    """Model or market line as the favourite's handicap, e.g. 'CHI -3.5'."""
    if margin is None:
        return "–"
    v = round(2 * margin) / 2
    return f"{home} -{abs(v):g}" if v > 0 else f"{away} -{abs(v):g}" if v < 0 else "pick'em"


def snapshot(out: dict) -> dict:
    m = out["meta"]
    games, inj, qbs, pts = {}, {}, {}, {}
    for g in out["games"]:
        if g.get("state") != "pre":
            continue
        h, a = g["home"]["abbr"], g["away"]["abbr"]
        w = g.get("weather") or {}
        games[g["game_id"]] = dict(h=h, a=a, m=g["margin"], t=g["total"], sp=g["spread"], tl=g["total_line"],
                                   src=g.get("src"), wind=w.get("wind"), rain=w.get("rain"), temp=w.get("temp"),
                                   wxi=w.get("impact"), wtxt=w.get("text"))
        for t in (g["home"], g["away"]):
            qbs[t["abbr"]] = t.get("qb")
            pts[t["abbr"]] = t.get("inj_pts")
    for t, r in (out.get("injuries") or {}).items():
        inj[t] = {p["name"]: [p["status"], p.get("pos"), p.get("pts")] for p in r.get("counted", []) + r.get("qbs", [])}
    teams = {t: dict(net=v.get("net"), off=v.get("off"), dfn=v.get("dfn")) for t, v in (out.get("teams") or {}).items()}
    return dict(time=m["generated_at"], week=m.get("week"), data_through=m.get("data_through"), odds_at=m.get("odds_at"),
                pps=m.get("pts_per_starter"), games=games, inj=inj, qbs=qbs, pts=pts, model=m.get("model") or {},
                recal=m.get("recal") or {}, record=m.get("record") or {}, teams=teams)


PARAMS = [("hfa", "Home-field edge", lambda v: f"{v:.2f} pts", 0.05),
          ("sd_margin", "Spread of final margins (SD)", lambda v: f"{v:.2f}", 0.05),
          ("sd_total", "Spread of final totals (SD)", lambda v: f"{v:.2f}", 0.05),
          ("league_total", "League scoring this season", lambda v: f"{v:.1f} pts/game", 0.3)]
RECAL = {"rec": "Receptions", "rec_yds": "Receiving yards", "rush_yds": "Rushing yards", "pass_yds": "Passing yards",
         "td": "Anytime TD"}
PLAYS = 65   # offensive plays per game, to show EPA/play as points


def diff(prev: dict | None, cur: dict) -> list[dict]:
    if not prev:
        return [dict(kind="data", icon="🟢", text="Started tracking NFL changes. Updates will show here after each run.")]
    out = []
    add = lambda kind, icon, text: out.append(dict(kind=kind, icon=icon, text=text))
    if cur.get("data_through") and cur["data_through"] != prev.get("data_through"):
        add("data", "📥", f"New results loaded: games through {pd.Timestamp(cur['data_through']):%a %b %-d}. "
                           "Team ratings, QB levels and player usage refreshed.")
    if cur.get("week") != prev.get("week"):
        add("data", "📅", f"New week: Week {cur.get('week')}.")
    if cur.get("odds_at") and cur["odds_at"] != prev.get("odds_at"):
        add("line", "📊", "Market lines pulled (consensus across US books).")
    if cur.get("pps") and prev.get("pps") and abs(cur["pps"] - prev["pps"]) >= 0.02:
        add("model", "⚙️", f"Points per missing starter: {prev['pps']:.2f} → {cur['pps']:.2f}")
    pm, cm = prev.get("model") or {}, cur.get("model") or {}
    for key, label, fmt, tol in PARAMS:
        a, b = pm.get(key), cm.get(key)
        if a is not None and b is not None and abs(b - a) >= tol:
            add("model", "⚙️", f"{label}: {fmt(a)} → {fmt(b)}")
    for k, lab in RECAL.items():
        a, b = (prev.get("recal") or {}).get(k), (cur.get("recal") or {}).get(k)
        if b and (not a or abs(b["level"] - a["level"]) >= 0.005):
            was = f"{a['level']:.3f}" if a else "1.000"
            add("recal", "🎯", f"{lab} props recalibrated on this season's results: level {was} → {b['level']:.3f} "
                               f"({b['n']} player-games, raw {b['raw']:.2f})")
    moves = []
    for t, c in (cur.get("teams") or {}).items():
        p = (prev.get("teams") or {}).get(t)
        if not p or c.get("net") is None or p.get("net") is None:
            continue
        d = (c["net"] - p["net"]) * PLAYS
        if abs(d) >= 0.4:
            moves.append((abs(d), f"{t} {'+' if d > 0 else '−'}{abs(d):.1f}"))
    if moves:
        moves.sort(reverse=True)
        add("teams", "📈", "Biggest team-strength moves (pts/game): " + ", ".join(m for _, m in moves[:6]))
    pr, cr = (prev.get("record") or {}).get("lean"), (cur.get("record") or {}).get("lean")
    if cr and (cr["w"] + cr["l"] + cr["p"]) > ((pr["w"] + pr["l"] + pr["p"]) if pr else 0):
        n0 = (pr["w"] + pr["l"] + pr["p"]) if pr else 0
        dw, dl = cr["w"] - (pr["w"] if pr else 0), cr["l"] - (pr["l"] if pr else 0)
        du = cr["units"] - (pr["units"] if pr else 0)
        add("record", "🧾", f"Graded {cr['w'] + cr['l'] + cr['p'] - n0} model leans: {dw}-{dl} ({du:+.1f}u). "
                            f"Season: {cr['w']}-{cr['l']}{'-' + str(cr['p']) if cr['p'] else ''} ({cr['units']:+.1f}u)")
    same_week = cur.get("week") == prev.get("week")
    for t, q in cur.get("qbs", {}).items():
        pq = prev.get("qbs", {}).get(t)
        if same_week and pq and q and pq != q:
            add("qb", "🏈", f"{t} starting QB: {pq} → {q}")
    if same_week:
        for t, now in cur.get("inj", {}).items():
            was = prev.get("inj", {}).get(t, {})
            for n, (st, pos, p) in sorted(now.items()):
                tail = f" ({p:+.1f} pts)" if p else ""
                if n not in was:
                    add("injury", "🚑", f"{t}: {n} ({pos}) listed {st}{tail}")
                elif was[n][0] != st:
                    add("injury", "🔁", f"{t}: {n} ({pos}) {was[n][0]} → {st}{tail}")
            for n, (st, pos, _) in sorted(was.items()):
                if n not in now:
                    add("injury", "✅", f"{t}: {n} ({pos}) off the injury list")
        for gid, g in cur.get("games", {}).items():
            p = prev.get("games", {}).get(gid)
            if not p:
                continue
            lab = f"{g['a']} @ {g['h']}"
            if g["m"] is not None and p["m"] is not None and abs(g["m"] - p["m"]) >= 1.0:
                add("price", "💲", f"{lab}: model {_sp(g['h'], g['a'], p['m'])} → {_sp(g['h'], g['a'], g['m'])}")
            if g["t"] is not None and p["t"] is not None and abs(g["t"] - p["t"]) >= 1.5:
                add("price", "💲", f"{lab}: model total {p['t']:.1f} → {g['t']:.1f}")
            if g["sp"] is not None and p["sp"] is not None and abs(g["sp"] - p["sp"]) >= 1.0:
                add("line", "📊", f"{lab}: market {_sp(g['h'], g['a'], p['sp'])} → {_sp(g['h'], g['a'], g['sp'])}")
            if g.get("wtxt") and g.get("wind") is not None and (p.get("wind") is None or abs(g["wind"] - p["wind"]) >= 5
                                                              or abs((g.get("rain") or 0) - (p.get("rain") or 0)) >= 0.25
                                                              or abs((g.get("wxi") or 0) - (p.get("wxi") or 0)) >= 0.5):
                icon = "🌧️" if (g.get("rain") or 0) >= 0.35 else "🌬️" if g["wind"] >= 15 else "🌦️"
                was = f"{p['wtxt']} → " if p.get("wtxt") and p.get("wind") is not None else "first forecast: "
                add("weather", icon, f"{lab} weather {was}{g['wtxt']} (total {g.get('wxi') or 0:+.1f} pts)")
            if g["tl"] is not None and p["tl"] is not None and abs(g["tl"] - p["tl"]) >= 1.0:
                add("line", "📊", f"{lab}: market total {p['tl']:g} → {g['tl']:g}")
    return out


def update(site: str, out: dict) -> list[dict]:
    f = os.path.join(site, "nfl_log.json")
    try:
        log = json.load(open(f)) if os.path.exists(f) else []
    except (ValueError, OSError):
        log = []
    cur = snapshot(out)
    items = diff(log[-1]["snap"] if log else None, cur)
    log.append(dict(snap=cur, items=items))
    log = log[-KEEP:]
    with open(f, "w") as fh:
        json.dump(log, fh, separators=(",", ":"), default=str)
    return [dict(time=e["snap"]["time"], items=e["items"]) for e in log if e.get("items")][::-1][:40]
