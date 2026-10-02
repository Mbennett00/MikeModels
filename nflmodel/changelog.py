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
        games[g["game_id"]] = dict(h=h, a=a, m=g["margin"], t=g["total"], sp=g["spread"], tl=g["total_line"],
                                   src=g.get("src"))
        for t in (g["home"], g["away"]):
            qbs[t["abbr"]] = t.get("qb")
            pts[t["abbr"]] = t.get("inj_pts")
    for t, r in (out.get("injuries") or {}).items():
        inj[t] = {p["name"]: [p["status"], p.get("pos"), p.get("pts")] for p in r.get("counted", []) + r.get("qbs", [])}
    return dict(time=m["generated_at"], week=m.get("week"), data_through=m.get("data_through"), odds_at=m.get("odds_at"),
                pps=m.get("pts_per_starter"), games=games, inj=inj, qbs=qbs, pts=pts)


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
