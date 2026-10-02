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
from . import changelog, data, injuries as I, model as M, odds as O
from . import props as PP
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
    seasons = sorted(set(tg.season.astype(int)))
    snaps, inj = data.load_rosters(cache, seasons, log=log)
    cfg = M.Config()
    F = B.build_features(sched, tg, qb, cfg, log=lambda *a: None, snaps=snaps, inj=inj)
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

    S = I.prep_snaps(snaps, sched) if len(snaps) else None
    injuries, lineup = {}, {}
    live = injury_reports(inj, wk, log)

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
        side = {}
        for t, qbn in ((g.home_team, g.home_qb_name), (g.away_team, g.away_qb_name)):
            rep = live[live.team == t] if live is not None else None
            regs_all = I.regulars(S, t, asof, min_base=0.0) if S is not None else None
            if S is not None and not started:
                miss, det = I.missing(regs_all[regs_all.share >= I.MIN_BASE], rep)
                lineup[t] = depth(S, t, asof, rep)
            else:
                miss, det = {k: 0.0 for k in I.GROUPS}, []
            qbn, qb_note = qb_starter(qb, t, qbn if isinstance(qbn, str) else None, rep, asof)
            adj, qid = M.qb_adjust(qb, lvg, t, qbn, asof, cfg)
            side[t] = dict(miss=miss, det=det, qb=qbn, qb_note=qb_note, qb_adj=adj, qb_id=qid,
                           inj_pts=float(cfg.coef_m[-1] * sum(miss.values())), report=rep)
            injuries[t] = injury_detail(t, side[t], regs_all, cfg.coef_m[-1])
        sh_, sa_ = side[g.home_team], side[g.away_team]
        qh, idh, qa, ida = sh_["qb_adj"], sh_["qb_id"], sa_["qb_adj"], sa_["qb_id"]
        neutral = g.location == "Neutral"
        xm, xt = M.features(Rg, g.home_team, g.away_team, neutral, qh, qa, g.roof, g.wind, g.temp,
                            I.vector(sh_["miss"]), I.vector(sa_["miss"]))
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
        for tinfo, sd, qid in ((th, sh_, idh), (ta, sa_, ida)):
            tinfo.update(qb=pretty_qb(sd["qb"]), qb_note=sd["qb_note"], qb_adj=_r(sd["qb_adj"]),
                         qb_level=_r(lvg.level.get(qid)) if qid else None,
                         inj_pts=_r(sd["inj_pts"], 2), missing={k: _r(v, 2) for k, v in sd["miss"].items()})
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
    try:
        players, recal = player_props(cache, site, seasons, season, games, R, live, now_et, log)
    except Exception as e:   # props never block the game page
        log(f"nfl props: {e}")
        players, recal = [], {}
    record = grade_record(frozen, sched, season)

    played = sched[sched.result.notna()]
    meta = dict(sport="nfl", generated_at=now_et.isoformat(), season=season,
                week=int(wk.week.iloc[0]) if len(wk) else None,
                data_through=str(tg.date.max().date()), games_this_season=int((played.season == season).sum()),
                odds_at=cached["fetched_at"] if cached else None, book=os.environ.get("ODDS_BOOK_NAME", "Caesars"),
                book_short=book_short, edge_flag=EDGE_FLAG,
                inj_source="ESPN" if live is not None and "detail" in live else ("official report" if live is not None else None),
                pts_per_starter=_r(-cfg.coef_m[-1], 2),
                sd_margin=_r(cfg.sd_margin, 2), sd_total=_r(cfg.sd_total, 2),
                backtest={k: (list(v) if isinstance(v, tuple) else _r(v)) for k, v in bt.items()},
                backtest_seasons="2021-" + str(int(bt_rows.season.max())) if len(bt_rows) else None)
    pc = PP.PropConfig()
    recent = rows[(rows.season == season) & (rows.season_type == "REG")]
    # home edge in points: the direct term plus what the home bump in each rating adds through the margin fit
    hfa = cfg.coef_m[1] + sum(cfg.coef_m[2 + i] * R.home[mk] for i, mk in enumerate(M.METRICS))
    meta["model"] = dict(hfa=_r(hfa, 2), sd_margin=_r(cfg.sd_margin, 2), sd_total=_r(cfg.sd_total, 2),
                         pts_per_starter=_r(-cfg.coef_m[-1], 2),
                         league_total=_r(2 * recent.points.mean(), 1) if len(recent) else None,
                         games_fit=int(F.result.notna().sum()))
    meta["recal"] = {k: dict(level=_r(v["level"], 3), raw=_r(v["raw"], 3), n=v["n"]) for k, v in recal.items()}
    meta["record"] = record
    meta["props"] = dict(r_rec=pc.r_rec, cv=dict(rec_yds=pc.cv_rec_yds, rush_yds=pc.cv_rush_yds, pass_yds=pc.cv_pass_yds),
                         shift=dict(rec_yds=pc.sh_rec_yds, rush_yds=pc.sh_rush_yds, pass_yds=pc.sh_pass_yds))
    attach_props(lineup, players)
    out = dict(meta=meta, games=games, players=players, teams=team_table(R, rows, season), key_m=cfg.key_m, key_t=cfg.key_t,
               injuries=injuries, lineups=lineup)
    out["updates"] = changelog.update(site, out)
    write(site, out)
    log(f"nfl: week {meta['week']}, {len(games)} games, data through {meta['data_through']}, "
        f"odds {'from ' + str(meta['odds_at']) if cached else 'none (nflverse lines)'}")
    return out


ROLE = {"QB": "QB", "RB": "RB", "FB": "RB", "HB": "RB", "WR": "REC", "TE": "REC"}


def player_props(cache, site, seasons, season, games, R, live, now_et, log=print) -> list:
    """Projections for the players who matter in each upcoming game; started games keep their last projections."""
    pg = data.load_players(cache, seasons)
    if pg.empty:
        return []
    cfg = PP.PropConfig()
    cfg.priors = PP.fit_priors(pg[pg.season >= season - 4])
    tgp = PP.team_games(pg)
    ros = data.rosters(season, cache, log)
    act = ros[ros.status == "ACT"] if len(ros) else ros
    out_keys = {}
    if live is not None and len(live):
        for t, d in live.groupby("team"):
            out_keys[t] = set(d[d.status.map(I.miss_weight) >= 0.85].key)
    q_keys = ({(r.team, r.key): str(r.status) for r in live.itertuples() if I.miss_weight(r.status) > 0}
              if live is not None and len(live) else {})
    rows, starters, avail = [], {}, {}
    pending = [g for g in games if g.get("state") == "pre"]
    for g in pending:
        for side, opp, sign in (("home", "away", 1), ("away", "home", -1)):
            t = g[side]["abbr"]
            pts = g["pts_home"] if side == "home" else g["pts_away"]
            rows.append(dict(game_id=g["game_id"], team=t, opp=g[opp]["abbr"], pts=pts, margin=sign * g["margin"]))
            if len(act):
                mine = act[act.team == t]
                avail[t] = {pid for pid, r in mine.iterrows() if I.norm(r.full_name) not in out_keys.get(t, set())}
            qbname = g[side].get("qb")
            if qbname and len(act):
                cand = act[(act.team == t) & (act.position == "QB")]
                m = cand[cand.full_name.map(I.norm) == I.norm(qbname)]
                if m.empty:   # backup written as 'G. Minshew'
                    last = I.norm(qbname).split()[-1] if I.norm(qbname) else ""
                    m = cand[cand.full_name.map(lambda n: I.norm(n).split()[-1] if I.norm(n) else "") == last]
                if len(m):
                    starters[t] = m.index[0]
    fpath = os.path.join(site, "nfl_props.json")
    try:
        frozen = json.load(open(fpath))
    except (OSError, ValueError):
        frozen = {}
    recal = PP.recalibrate(graded_props(frozen, pg))
    cfg.level = {k: v["level"] for k, v in recal.items()}
    lv = {k: round(v, 4) for k, v in cfg.level.items()}
    res = []
    if rows:
        asof = now_et.tz_localize(None)
        roles = {pid: ROLE.get(r.position) for pid, r in act.iterrows()} if len(act) else None
        pr = PP.project(pg, tgp, asof, pd.DataFrame(rows), cfg, dfn={"pass": R.dfn["epa_db"], "rush": R.dfn["epa_play"]},
                        available=avail or None, roles_now=roles, starters=starters)
        for r in pr.itertuples():
            if r.role is None or (r.role == "QB" and pd.isna(getattr(r, "pass_yds", np.nan))):
                continue
            show = (r.role == "QB") or r.tgt >= 2.5 or r.car >= 5
            if not show:
                continue
            info_ = ros.loc[r.player_id] if r.player_id in ros.index else None
            full = info_.full_name if info_ is not None else r.name
            rec = dict(id=r.player_id, game_id=r.game_id, team=r.team, opp=r.opp, name=full, role=r.role,
                       pos=info_.position if info_ is not None else r.role,
                       num=_r(info_.jersey_number, 0) if info_ is not None else None,
                       headshot=info_.headshot_url if info_ is not None and isinstance(info_.headshot_url, str) else None,
                       status=q_keys.get((r.team, I.norm(full))),
                       tgt=_r(r.tgt, 2), rec=_r(r.rec, 2), rec_yds=_r(r.rec_yds, 1), car=_r(r.car, 2),
                       rush_yds=_r(r.rush_yds, 1), lam_td=_r(r.lam_td, 4), p_td=_r(1 - math.exp(-r.lam_td), 4), lv=lv)
            if not pd.isna(getattr(r, "pass_yds", np.nan)):
                rec.update(att=_r(r.att, 1), pass_yds=_r(r.pass_yds, 1), lam_pass_td=_r(r.lam_pass_td, 3))
            res.append(rec)
        for gid in {r["game_id"] for r in res}:
            frozen[gid] = [r for r in res if r["game_id"] == gid]
    pend_ids = {g["game_id"] for g in pending}
    for g in games:
        if g["game_id"] not in pend_ids and g["game_id"] in frozen:
            res += frozen[g["game_id"]]
    json.dump({k: v for k, v in frozen.items() if k.startswith(str(season))}, open(fpath, "w"), separators=(",", ":"))
    log(f"nfl props: {len(res)} players; recalibration {lv or 'none yet'}")
    return res, recal


def graded_props(frozen: dict, pg: pd.DataFrame) -> pd.DataFrame:
    """Pre-kickoff projections for finished games next to the box scores, with the live recalibration that was
    applied at the time taken back out (so the levels don't feed on themselves)."""
    rows = [p for gid, L in frozen.items() for p in L]
    if not rows or pg.empty:
        return pd.DataFrame()
    d = pd.DataFrame(rows)
    a = pg.assign(a_td=((pg.rec_td + pg.rush_td) > 0).astype(float))[
        ["game_id", "player_id", "rec", "rec_yds", "rush_yds", "pass_yds", "a_td"]]
    a = a.rename(columns={c: f"a_{c}" for c in ("rec", "rec_yds", "rush_yds", "pass_yds")})
    d = d.merge(a, left_on=["game_id", "id"], right_on=["game_id", "player_id"], how="inner")
    if "lv" not in d:
        d["lv"] = None
    for m in ("rec", "rec_yds", "rush_yds", "pass_yds"):
        if m in d:
            d[m] = d[m] / d.lv.map(lambda v: (v or {}).get(m, 1.0) if isinstance(v, dict) else 1.0)
    if "p_td" in d:
        c = d.lv.map(lambda v: (v or {}).get("td", 1.0) if isinstance(v, dict) else 1.0)
        d["p_td"] = 1 - np.exp(np.log(1 - d.p_td.clip(upper=0.99)) / c)
    if "pass_yds" not in d:
        d["pass_yds"] = np.nan
    return d


def grade_record(frozen: dict, sched: pd.DataFrame, season: int) -> dict:
    """This season's results for what the model liked (pre-kickoff prices): leans (3+ pt edge) and 💰 picks."""
    res = sched.set_index("game_id")
    out = {k: dict(w=0, l=0, p=0, units=0.0) for k in ("lean", "flag")}
    weeks = {}
    for gid, g in frozen.items():
        if gid not in res.index or pd.isna(res.loc[gid, "result"]) or not gid.startswith(str(season)):
            continue
        m, t = float(res.loc[gid, "result"]), float(res.loc[gid, "total"])
        for b in g.get("bets", []):
            if b.get("edge") is None or b["edge"] < 0.03 or b.get("price") is None:
                continue
            if b["m"] == "ml":
                v = m if b["s"] == "home" else -m
            elif b["m"] == "spread":
                v = (m - g["spread"]) if b["s"] == "home" else (g["spread"] - m)
            else:
                v = (t - g["total_line"]) if b["s"] == "over" else (g["total_line"] - t)
            pr = float(b["price"])
            u = 0.0 if v == 0 else (pr / 100 if pr > 0 else 100 / -pr) if v > 0 else -1.0
            for k in ("lean",) + (("flag",) if b["edge"] >= EDGE_FLAG else ()):
                o = out[k]
                o["w" if v > 0 else "l" if v < 0 else "p"] += 1
                o["units"] = round(o["units"] + u, 2)
            wk = weeks.setdefault(int(g.get("week", 0)), dict(w=0, l=0, p=0, units=0.0))
            wk["w" if v > 0 else "l" if v < 0 else "p"] += 1
            wk["units"] = round(wk["units"] + u, 2)
    out["weeks"] = {str(k): v for k, v in sorted(weeks.items())}
    return out


def injury_reports(inj: pd.DataFrame, wk: pd.DataFrame, log=print) -> pd.DataFrame | None:
    """This week's statuses: ESPN's live list, else nflverse's copy of the official report."""
    espn = I.fetch_espn(log)
    if espn is not None:
        return espn
    if inj is None or inj.empty or wk.empty:
        return None
    season, week = int(wk.season.iloc[0]), int(wk.week.iloc[0])
    r = I.history_reports(inj)
    r = r[(r.season == season) & (r.week == week)].rename(columns={"full_name": "name"})
    log(f"injuries: ESPN unavailable, using the official report ({len(r)} players, week {week})")
    return r if len(r) else None


def qb_starter(qb: pd.DataFrame, team: str, listed: str | None, rep, asof) -> tuple[str | None, str | None]:
    """The listed starter, or his backup when the injury report has him out / doubtful."""
    if not listed or rep is None or rep.empty:
        return listed, None
    hit = rep[rep.key == I.norm(listed)]
    if hit.empty or I.miss_weight(hit.status.iloc[0]) < 0.85:
        return listed, None
    status = str(hit.status.iloc[0])
    q = qb[(qb.team == team) & (qb.date < pd.Timestamp(asof)) & (qb.date >= pd.Timestamp(asof) - pd.Timedelta(days=400))]
    last = I.norm(listed).split()[-1]
    q = q[~q.name.fillna("").str.lower().str.replace(".", " ", regex=False).str.split().str[-1].eq(last)]
    if q.empty:
        return "Backup QB", f"{listed} {status}"
    backup = q.groupby("name").dropbacks.sum().idxmax()
    return backup, f"{listed} {status}"


def pretty_qb(name):
    if not isinstance(name, str):
        return None
    return name.replace(".", ". ", 1) if "." in name and " " not in name else name


def injury_detail(team: str, sd: dict, regs_all, coef: float) -> dict:
    """Everything the Updates tab shows for one team: who is counted (and for how much), injured QBs, and the
    rest of the list with the reason each one is not counted."""
    counted = [dict(name=d["name"], pos=d["pos"], group=I.LABEL[d["group"]], status=d["status"], share=d["share"],
                    usual=d["usual"], presence=d["presence"], pts=_r(coef * d["w"] * d["share"], 2)) for d in sd["det"]]
    done = {d["key"] for d in sd["det"]}
    qbs, listed = [], []
    rep = sd["report"]
    if rep is not None and len(rep):
        r = rep.assign(_w=rep.status.map(I.miss_weight))
        r = r[r._w > 0].sort_values("_w", ascending=False).drop_duplicates("key")
        nm = "name" if "name" in r else "full_name"
        for _, x in r.iterrows():
            if x.key in done:
                continue
            row = dict(name=x[nm], pos=x.pos, status=str(x.status))
            if str(x.pos).upper() == "QB":
                row["note"] = f"{pretty_qb(sd['qb']) or 'the backup'} projected to start" if sd.get("qb_note") else "not the projected starter"
                qbs.append(row)
                continue
            b = float(regs_all.share.get(x.key, 0.0)) if regs_all is not None and len(regs_all) else 0.0
            row["note"] = ("hasn't played for them in the past year" if b == 0 else
                           f"only {round(100 * b)}% of snaps in the ratings")
            listed.append(row)
    return dict(abbr=team, inj_pts=_r(sd["inj_pts"], 2), qb=pretty_qb(sd["qb"]), qb_note=sd.get("qb_note"),
                counted=counted, qbs=qbs, listed=listed[:12])


# formation slots: (group of snap positions, how many)
OFF_SLOTS = [("QB", ("QB",), 1), ("RB", ("RB", "FB", "HB"), 1), ("WR", ("WR",), 3), ("TE", ("TE",), 1),
             ("OL", ("T", "G", "C", "OL", "OT", "OG"), 5)]
DEF_SLOTS = [("DL", ("DE", "DT", "NT", "DL", "EDGE"), 4), ("LB", ("LB", "ILB", "OLB", "MLB"), 2),
             ("CB", ("CB",), 3), ("S", ("S", "SS", "FS", "SAF", "DB"), 2)]   # nickel, the most common look


def depth(S: pd.DataFrame, team: str, asof, rep) -> dict:
    """Who is lining up now: the most-used players at each spot over the last few games (half-life 3 weeks),
    with anyone ruled out (Out / Doubtful / IR) replaced by the next man up."""
    t = S[(S.team == team) & (S.gameday < pd.Timestamp(asof)) & (S.gameday >= pd.Timestamp(asof) - pd.Timedelta(days=300))]
    if t.empty:
        return {}
    games = t.groupby("game_id").gameday.first()
    w = 0.5 ** ((pd.Timestamp(asof) - games).dt.days.astype(float) / 21.0)
    t = t.assign(w=t.game_id.map(w)).sort_values("gameday")
    use = t.assign(ws=t.w * t.share).groupby("key").agg(player=("player", "last"), pos=("position", "last"),
                                                        ws=("ws", "sum"))
    use["share"] = use.ws / float(w.sum())
    status = {}
    if rep is not None and len(rep):
        for x in rep.itertuples():
            if I.miss_weight(x.status) > 0:
                status[x.key] = str(x.status)
    out = {}
    for side, slots in (("off", OFF_SLOTS), ("def", DEF_SLOTS)):
        rows, outs = [], []
        for slot, poss, n in slots:
            cand = use[use.pos.isin(poss)].sort_values("share", ascending=False)
            picked = []
            for k, r in cand.iterrows():
                st = status.get(k)
                if st and I.miss_weight(st) >= 0.99:
                    if len(picked) + len(outs) < n + 2 and r.share >= 0.3:
                        outs.append(dict(name=r.player, pos=r.pos, status=st))
                    continue
                if r.share < 0.2 and slot not in ("QB", "OL"):
                    break          # nobody else really plays there (e.g. no true nickel corner)
                picked.append(dict(slot=slot, name=r.player, key=k, pos=r.pos, share=round(float(r.share), 2), status=st))
                if len(picked) == n:
                    break
            rows += picked
        out[side] = dict(players=rows, out=outs)
    return out


def attach_props(lineup: dict, players: list):
    """Put each skill player's headline projection on his formation spot."""
    by = {(p["team"], I.norm(p["name"])): p for p in players}
    for t, L in lineup.items():
        for p in (L.get("off") or {}).get("players", []):
            q = by.get((t, p["key"]))
            if not q:
                continue
            if p["slot"] == "QB" and q.get("pass_yds") is not None:
                p["proj"] = f"{round(q['pass_yds'])} pass yds"
            elif p["slot"] == "RB":
                p["proj"] = f"{round(q['rush_yds'])} rush yds"
            elif p["slot"] in ("WR", "TE"):
                p["proj"] = f"{round(q['rec_yds'])} rec yds"
            p["td"] = q.get("p_td")
            p["id"] = q.get("id")


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
