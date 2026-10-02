"""NFL run: refresh nflverse data, rate teams, price this week's games, compare with the market, write the page.

    python -m nflmodel.daily            (reads/writes ./state, like the NHL job)

Writes state/site/nfl.json (kept in the data-latest release) and state/site/web/nfl.json + nfl.html.
Odds: one Odds API pull a day (3 credits) when ODDS_ENABLED is on; NFL_ODDS_PULL=1 forces one.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import sys

import numpy as np
import pandas as pd

from . import backtest as B
from . import data, model as M, odds as O
from .teams import info

HERE = os.path.dirname(__file__)
EDGE_FLAG = 0.06   # edge (model minus market no-vig) that earns the 💰; the model has not beaten closing lines


def fair_american(p: float) -> float | None:
    if p is None or not (0 < p < 1):
        return None
    return -100 * p / (1 - p) if p >= 0.5 else 100 * (1 - p) / p


def _r(x, nd=4):
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else round(f, nd)


def kickoff_utc(g) -> pd.Timestamp:
    t = str(g.gametime) if isinstance(g.gametime, str) else "13:00"
    return pd.Timestamp(f"{g.gameday:%Y-%m-%d} {t}").tz_localize("America/New_York").tz_convert("UTC")


def week_games(sched: pd.DataFrame, now_et: pd.Timestamp) -> pd.DataFrame:
    """This NFL week's games: the earliest week that still has a game to play (finished ones included)."""
    s = sched.copy()
    s["kick"] = [kickoff_utc(g) for g in s.itertuples()]
    now_utc = now_et.tz_convert("UTC")
    todo = s[s.result.isna() & (s.kick > now_utc - pd.Timedelta(hours=5))]
    if todo.empty:
        return s.iloc[0:0]
    season, week = todo.sort_values("kick").iloc[0][["season", "week"]]
    return s[(s.season == season) & (s.week == week)].sort_values(["kick", "game_id"])


def team_table(R: M.Ratings, rows: pd.DataFrame, season: int) -> dict:
    """Per team: ratings (EPA/play units; defence = allowed, lower is better), ranks and season record."""
    out = {}
    teams = sorted(R.off["epa_play"])
    net = {t: R.off["epa_play"][t] - R.dfn["epa_play"][t] for t in teams}
    pts = {t: R.off["points"][t] - R.dfn["points"][t] for t in teams}
    rk = lambda d, rev=True: {t: i + 1 for i, t in enumerate(sorted(d, key=d.get, reverse=rev))}
    keys = dict(off=R.off["epa_play"], pas=R.off["epa_db"], dfn={t: -R.dfn["epa_play"][t] for t in teams},
                pdef={t: -R.dfn["epa_db"][t] for t in teams}, net=net, pts=pts)
    ranks = {k: rk(v) for k, v in keys.items()}
    cur = rows[(rows.season == season) & (rows.season_type == "REG")]
    for t in teams:
        me = cur[cur.team == t]
        opp_pts = cur[(cur.opp == t)].set_index("game_id").points
        w = sum(1 for g in me.itertuples() if g.points > opp_pts.get(g.game_id, 1e9))
        l = sum(1 for g in me.itertuples() if g.points < opp_pts.get(g.game_id, -1))
        tie = len(me) - w - l
        out[t] = dict(info(t), **{k: _r(v[t]) for k, v in keys.items()}, rank={k: ranks[k][t] for k in keys},
                      record=f"{w}-{l}" + (f"-{tie}" if tie else ""))
    return out


def bets_for(p: dict, mk: dict, src: str, book_short: str) -> list:
    """Model vs market for ML, spread and total. mk sides are home / over first."""
    out = []

    def add(m, s, label, pm, pk, price):
        edge = None if pk is None else pm - pk
        if price is None and src != "odds" and pk is not None:
            price = mk.get("posted", {}).get((m, s), -110.0)   # posted lines: moneylines as listed, spreads/totals at -110
            bp, lab = price, "Line"
        else:
            bp = price if price is not None else fair_american(pk) if pk is not None else None
            lab = book_short if price is not None else "Mkt"
        out.append(dict(m=m, s=s, label=label, p=_r(pm), mkt=_r(pk), edge=_r(edge),
                        price=_r(bp, 0), src=lab))
    ml = mk.get("ml") or {}
    add("ml", "away", None, p["p_away"], 1 - ml["p_home"] if ml else None, ml.get("book_away"))
    add("ml", "home", None, p["p_home"], ml.get("p_home"), ml.get("book_home"))
    if "p_home_cover" in p:
        sp = mk.get("spread") or {}
        pk = sp.get("p_first")
        add("spread", "away", None, 1 - p["p_home_cover"], None if pk is None else 1 - pk, sp.get("book_second"))
        add("spread", "home", None, p["p_home_cover"], pk, sp.get("book_first"))
    if "p_over" in p:
        tt = mk.get("total") or {}
        pk = tt.get("p_first")
        add("total", "over", None, p["p_over"], pk, tt.get("book_first"))
        add("total", "under", None, 1 - p["p_over"], None if pk is None else 1 - pk, tt.get("book_second"))
    return out


def run(state: str = "state", log=print) -> dict:
    cache, site = os.path.join(state, "intermediate", "nfl"), os.path.join(state, "site")
    web = os.path.join(site, "web")
    os.makedirs(web, exist_ok=True)
    now_et = pd.Timestamp.now(tz="America/New_York")
    sched, tg, qb = data.load(cache, log=log)
    cfg = M.Config()
    F = B.build_features(sched, tg, qb, cfg, log=lambda *a: None)
    bt_rows, bt = B.run(sched, tg, qb, cfg, F=F, log=lambda *a: None)
    cfg = B.fit_mapping(F, cfg)
    rows = M.team_rows(tg, sched)
    wk = week_games(sched, now_et)
    R = M.fit_ratings(rows, now_et.tz_localize(None), cfg)
    lv = M.qb_levels(qb, now_et.tz_localize(None), cfg)
    season = int(wk.season.iloc[0]) if len(wk) else int(sched[sched.result.notna()].season.max())

    # market: today's pull, else the last one, else the nflverse lines
    key, mode = os.environ.get("ODDS_API_KEY"), os.environ.get("ODDS_ENABLED", "0")
    book, book_short = os.environ.get("ODDS_BOOK", "williamhill_us"), os.environ.get("ODDS_BOOK_SHORT", "CZR")
    opath = os.path.join(site, "nfl_odds.json")
    cached = O.load_cached(opath)
    upcoming = wk[wk.result.isna()]
    if key and mode != "0" and O.due(cached, now_et, len(upcoming) > 0, os.environ.get("NFL_ODDS_PULL") == "1"):
        try:
            cached = O.fetch(key, log)
            json.dump(cached, open(opath, "w"))
        except Exception as e:
            log(f"nfl odds: {e}")
    evs = O.match(cached["events"], wk) if cached else {}

    ppath = os.path.join(site, "nfl_prices.json")   # last pre-kickoff prices, so finished games keep theirs
    try:
        frozen = json.load(open(ppath))
    except (OSError, ValueError):
        frozen = {}
    games = []
    for g in wk.itertuples():
        kick = g.kick
        started = kick <= now_et.tz_convert("UTC") or not pd.isna(g.result)
        if started and g.game_id in frozen:
            games.append(dict(frozen[g.game_id], result=_result(g), state="post" if not pd.isna(g.result) else "in"))
            continue
        asof, Rg, lvg = now_et.tz_localize(None), R, lv
        if started:   # first seen after kickoff: price it with what was known before the game
            asof = kick.tz_convert("America/New_York").tz_localize(None).normalize()
            Rg, lvg = M.fit_ratings(rows, asof, cfg), M.qb_levels(qb, asof, cfg)
        qh, idh = M.qb_adjust(qb, lvg, g.home_team, g.home_qb_name, asof, cfg)
        qa, ida = M.qb_adjust(qb, lvg, g.away_team, g.away_qb_name, asof, cfg)
        neutral = g.location == "Neutral"
        xm, xt = M.features(Rg, g.home_team, g.away_team, neutral, qh, qa, g.roof, g.wind, g.temp)
        mm, tm = float(xm @ cfg.coef_m), float(xt @ cfg.coef_t)
        mk, src = {}, "line"
        if g.game_id in evs:
            mk, src = O.consensus(evs[g.game_id], book), "odds"
        if "spread" in mk:
            spread = -mk["spread"]["line"]              # Odds API home point -3.5 -> home expected to win by 3.5
        else:
            spread = g.spread_line
        total = mk["total"]["line"] if "total" in mk else g.total_line
        if "ml" not in mk and not pd.isna(g.home_moneyline):
            mk["ml"] = dict(p_home=implied_pair(g.home_moneyline, g.away_moneyline))
            mk["posted"] = {("ml", "home"): float(g.home_moneyline), ("ml", "away"): float(g.away_moneyline)}
        if "spread" not in mk and not pd.isna(g.spread_line) and src == "line":
            mk["spread"] = dict(p_first=0.5)
        if "total" not in mk and not pd.isna(g.total_line) and src == "line":
            mk["total"] = dict(p_first=0.5)
        p = M.price_game(mm, tm, cfg, spread, total)
        km, pm = p["margin_pmf"]; kt, pt = p["total_pmf"]
        sel = (km >= -45) & (km <= 45); selt = (kt >= 10) & (kt <= 90)
        th, ta = info(g.home_team), info(g.away_team)
        th.update(qb=g.home_qb_name if isinstance(g.home_qb_name, str) else None, qb_adj=_r(qh),
                  qb_level=_r(lvg.level.get(idh)) if idh else None)
        ta.update(qb=g.away_qb_name if isinstance(g.away_qb_name, str) else None, qb_adj=_r(qa),
                  qb_level=_r(lvg.level.get(ida)) if ida else None)
        rec = dict(game_id=g.game_id, week=int(g.week), start_utc=kick.isoformat(), home=th, away=ta,
                   neutral=bool(neutral), roof=g.roof if isinstance(g.roof, str) else None,
                   stadium=g.stadium if isinstance(g.stadium, str) else None,
                   margin=_r(mm, 2), total=_r(tm, 2), pts_home=_r((tm + mm) / 2, 1), pts_away=_r((tm - mm) / 2, 1),
                   p_home=_r(p["p_home"]), spread=_r(spread, 1), total_line=_r(total, 1), src=src,
                   n_books=max([v.get("n", 0) for k, v in mk.items() if k != "posted"] + [0]),
                   bets=bets_for(p, mk, src, book_short),
                   mpmf=dict(lo=int(km[sel][0]), p=[round(float(v), 6) for v in pm[sel]]),
                   tpmf=dict(lo=int(kt[selt][0]), p=[round(float(v), 6) for v in pt[selt]]))
        if not started:
            frozen[g.game_id] = rec
        games.append(dict(rec, result=_result(g), state="post" if not pd.isna(g.result) else ("in" if started else "pre")))
    json.dump({k: v for k, v in frozen.items() if k.startswith(str(season))}, open(ppath, "w"), separators=(",", ":"))

    played = sched[sched.result.notna()]
    meta = dict(sport="nfl", generated_at=now_et.isoformat(), season=season,
                week=int(wk.week.iloc[0]) if len(wk) else None,
                data_through=str(tg.date.max().date()), games_this_season=int((played.season == season).sum()),
                odds_at=cached["fetched_at"] if cached else None, book=os.environ.get("ODDS_BOOK_NAME", "Caesars"),
                book_short=book_short, edge_flag=EDGE_FLAG,
                sd_margin=_r(cfg.sd_margin, 2), sd_total=_r(cfg.sd_total, 2),
                backtest={k: (list(v) if isinstance(v, tuple) else _r(v)) for k, v in bt.items()},
                backtest_seasons="2021-" + str(int(bt_rows.season.max())) if len(bt_rows) else None)
    out = dict(meta=meta, games=games, teams=team_table(R, rows, season), key_m=cfg.key_m, key_t=cfg.key_t)
    write(site, out)
    log(f"nfl: week {meta['week']}, {len(games)} games, data through {meta['data_through']}, "
        f"odds {'from ' + str(meta['odds_at']) if cached else 'none (nflverse lines)'}")
    return out


def implied_pair(h, a) -> float:
    ih, ia = O.implied(float(h)), O.implied(float(a))
    return ih / (ih + ia)


def _result(g):
    if pd.isna(g.result):
        return None
    return dict(home=int(g.home_score), away=int(g.away_score))


def write(site: str, out: dict):
    web = os.path.join(site, "web")
    os.makedirs(web, exist_ok=True)
    txt = json.dumps(out, separators=(",", ":"), default=str)
    for d in (site, web):
        with open(os.path.join(d, "nfl.json"), "w") as f:
            f.write(txt)
    install_page(web)


def install_page(web: str):
    """Copy the NFL page next to the NHL one (the NHL build calls this too, so neither drops the other)."""
    shutil.copy(os.path.join(HERE, "web_template.html"), os.path.join(web, "nfl.html"))
    src = os.path.join(os.path.dirname(web), "nfl.json")
    if os.path.exists(src) and os.path.abspath(src) != os.path.abspath(os.path.join(web, "nfl.json")):
        shutil.copy(src, os.path.join(web, "nfl.json"))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd == "run":
        run()
    elif cmd == "backtest":
        sched, tg, qb = data.load(os.path.join("state", "intermediate", "nfl"))
        R, S = B.run(sched, tg, qb, M.Config())
        print(json.dumps(S, indent=1, default=str))
    else:
        raise SystemExit(f"unknown command {cmd}")
