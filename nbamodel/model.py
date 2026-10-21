"""NBA team ratings and player projections.

Team model: every team-game's points = league average + home court + the team's offence − the opponent's defence
+ back-to-back effects, fit by recency-weighted ridge regression on finished games. Ages are counted in game days
(the offseason doesn't count), and last season's games carry 70% weight, so a new season starts from last year's
ratings pulled part of the way back to average, and this season's games take over as they come in.

Player model: projected minutes and per-minute rates from recent games (most recent weighted most), minutes
re-balanced so each team plays 240, injured players removed, points scaled to the team's projected score.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

HALF_LIFE = 60.0        # game days for a game's weight to halve
CARRY = 0.70            # weight on previous seasons' games (rosters change over the summer)
PRESEASON = 0.25        # this season's preseason games count a quarter (starters rest, rotations are tryouts)
PRE_SD = 1.15           # preseason scores are harder to call
RIDGE = 6.0             # pull toward average, in games' worth of evidence
SD_MARGIN_FLOOR, SD_TOTAL_FLOOR = 11.0, 16.0
STATS = ("pts", "reb", "ast", "fg3")


def phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def game_days_age(dates: pd.Series, seasons: pd.Series, asof: pd.Timestamp) -> np.ndarray:
    """Age in days with each summer break removed, so last April is 'recent' when a new season starts."""
    d = pd.to_datetime(dates)
    age = (asof - d).dt.days.astype(float).to_numpy().copy()
    cur = int(seasons.max()) if len(seasons) else 0
    for s in sorted(set(seasons.dropna().astype(int))):
        if s >= cur:
            continue
        end = d[seasons == s].max()                              # that season's last game
        nxt = d[seasons > s].min() if (seasons > s).any() else asof
        gap = max(0.0, (min(nxt, asof) - end).days - 1)          # the break that followed it
        age[(seasons <= s).to_numpy()] -= gap
    return np.maximum(age, 0.0)


def add_rest(games: pd.DataFrame) -> pd.DataFrame:
    """b2b_home / b2b_away: the team also played the previous day."""
    g = games.copy()
    long = pd.concat([g[["game_id", "date", "home"]].rename(columns={"home": "team"}), g[["game_id", "date", "away"]].rename(columns={"away": "team"})])
    long["date"] = pd.to_datetime(long.date)
    played = set(zip(long.team, long.date.dt.date))
    prev = lambda t, d: (t, (pd.Timestamp(d) - pd.Timedelta(days=1)).date()) in played
    g["b2b_home"] = [prev(t, d) for t, d in zip(g.home, g.date)]
    g["b2b_away"] = [prev(t, d) for t, d in zip(g.away, g.date)]
    return g


def fit_ratings(games: pd.DataFrame, asof: pd.Timestamp) -> dict:
    """Fit on finished regular-season and playoff games. Returns ratings and the score spreads."""
    g = games[(games.state == "post") & games.home_score.notna()].copy()
    g = g[pd.to_datetime(g.date) < asof]
    cur0 = int(g.season.max()) if len(g) else 0
    g = g[g.season_type.isin([2, 3]) | ((g.season_type == 1) & (g.season == cur0))]   # this season's preseason counts, old ones don't
    if len(g) < 20:
        raise ValueError(f"only {len(g)} finished games to fit")
    teams = sorted(set(g.home) | set(g.away))
    ix = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    cur = int(g.season.max())
    w = (0.5 ** (game_days_age(g.date, g.season, asof) / HALF_LIFE) * np.where(g.season < cur, CARRY, 1.0)
         * np.where(g.season_type == 1, PRESEASON, 1.0))
    # two rows per game: [mu, home, off(n), def(n), b2b_own, b2b_opp] -> points
    rows, y, ww = [], [], []
    for (h, a, hs, as_, nh, bh, ba), wt in zip(g[["home", "away", "home_score", "away_score", "neutral", "b2b_home", "b2b_away"]].itertuples(index=False), w):
        for off, de, pts, home, own, opp in ((h, a, hs, 0.0 if nh else 1.0, bh, ba), (a, h, as_, 0.0, ba, bh)):
            r = np.zeros(2 + 2 * n + 2)
            r[0], r[1] = 1.0, home
            r[2 + ix[off]] = 1.0
            r[2 + n + ix[de]] = -1.0
            r[2 + 2 * n], r[3 + 2 * n] = float(own), float(opp)
            rows.append(r); y.append(pts); ww.append(wt)
    X, y, ww = np.array(rows), np.array(y, float), np.array(ww)
    sw = np.sqrt(ww)
    pen = np.zeros(X.shape[1]); pen[2:2 + 2 * n] = RIDGE; pen[2 + 2 * n:] = 40.0      # b2b effects are small: strong prior at 0
    A = np.vstack([X * sw[:, None], np.diag(np.sqrt(pen))[pen > 0]])
    b = np.concatenate([y * sw, np.zeros(int((pen > 0).sum()))])
    beta = np.linalg.lstsq(A, b, rcond=None)[0]
    mu, hca = beta[0], beta[1]
    off = {t: float(beta[2 + ix[t]]) for t in teams}
    dfn = {t: float(beta[2 + n + ix[t]]) for t in teams}
    b2b_own, b2b_opp = float(beta[2 + 2 * n]), float(beta[3 + 2 * n])
    # score spreads from this fit's residuals (weighted), with floors
    pred_h = mu + np.where(g.neutral, 0, hca) + g.home.map(off) - g.away.map(dfn) + b2b_own * g.b2b_home + b2b_opp * g.b2b_away
    pred_a = mu + g.away.map(off) - g.home.map(dfn) + b2b_own * g.b2b_away + b2b_opp * g.b2b_home
    rm = (g.home_score - g.away_score) - (pred_h - pred_a)
    rt = (g.home_score + g.away_score) - (pred_h + pred_a)
    wsum = w.sum()
    sd_m = max(SD_MARGIN_FLOOR, float(np.sqrt((w * rm ** 2).sum() / wsum)))
    sd_t = max(SD_TOTAL_FLOOR, float(np.sqrt((w * rt ** 2).sum() / wsum)))
    return dict(mu=float(mu), hca=float(hca), off=off, dfn=dfn, b2b_own=b2b_own, b2b_opp=b2b_opp, sd_margin=sd_m, sd_total=sd_t,
                games_fit=int(len(g)), games_this_season=int(((g.season == cur) & (g.season_type != 1)).sum()),
                games_preseason=int(((g.season == cur) & (g.season_type == 1)).sum()), season=cur)


def project_game(R: dict, home: str, away: str, neutral=False, b2b_home=False, b2b_away=False, preseason=False) -> dict:
    o, d = R["off"], R["dfn"]
    ph = R["mu"] + (0 if neutral else R["hca"]) + o.get(home, 0) - d.get(away, 0) + R["b2b_own"] * b2b_home + R["b2b_opp"] * b2b_away
    pa = R["mu"] + o.get(away, 0) - d.get(home, 0) + R["b2b_own"] * b2b_away + R["b2b_opp"] * b2b_home
    m = ph - pa
    return dict(pts_home=round(ph, 1), pts_away=round(pa, 1), margin=round(m, 2), total=round(ph + pa, 1),
                p_home=round(phi(m / (R["sd_margin"] * (PRE_SD if preseason else 1.0))), 4))


def team_table(R: dict) -> dict:
    t = pd.DataFrame(dict(off=pd.Series(R["off"]), dfn=pd.Series(R["dfn"])))
    t["net"] = t.off + t.dfn
    for k in ("off", "dfn", "net"):
        t["r_" + k] = t[k].rank(ascending=False, method="min").astype(int)
    return {a: dict(off=round(r.off, 2), dfn=round(r.dfn, 2), net=round(r.net, 2), rank=dict(off=int(r.r_off), dfn=int(r.r_dfn), net=int(r.r_net)))
            for a, r in t.iterrows()}


INJ_MULT = {"out": 0.0, "doubtful": 0.25, "questionable": 0.7, "day-to-day": 0.75, "probable": 0.95}


def inj_mult(status: str) -> float:
    s = str(status or "").lower()
    for k, v in INJ_MULT.items():
        if s.startswith(k):
            return v
    return 1.0


def player_projections(box: pd.DataFrame, games: pd.DataFrame, roster: pd.DataFrame | None, inj: pd.DataFrame | None,
                       slate: list[dict], n_recent: int = 30, decay: float = 0.9) -> list[dict]:
    """Projections for every player on tonight's teams: minutes, points, rebounds, assists, threes (+ spreads)."""
    if box is None or box.empty or not slate:
        return []
    meta = games.set_index("game_id")[["date", "season", "season_type"]]
    b = box.join(meta, on="game_id", how="inner")
    cur = int(b.season.max()) if len(b) else 0
    b = b[b.season_type.isin([2, 3]) | ((b.season_type == 1) & (b.season == cur))].copy()   # this season's preseason too
    b["date"] = pd.to_datetime(b.date)
    b = b.sort_values("date", ascending=False)
    b["k"] = b.groupby("player_id").cumcount()
    b = b[b.k < n_recent]
    pre = (b.season_type == 1).to_numpy()
    base = decay ** b.k * np.where(b.season < cur, 0.6, 1.0)
    b["w"] = base * np.where(pre, 0.35, 1.0)          # per-minute production
    b["wm"] = base * np.where(pre, 0.15, 1.0)         # minutes (starters play short preseason nights)
    b["pre"] = pre

    def _agg(x):
        reg = x[~x.pre]
        # minutes from real games when there are any; a player with only preseason (rookie, new arrival) leans on it
        mins = np.average(reg["min"], weights=reg.wm) if len(reg) else min(32.0, 1.2 * float(np.average(x["min"], weights=x.wm)))
        return pd.Series(dict(name=x["name"].iloc[0], last_team=x["team"].iloc[0], pos=x["pos"].iloc[0], gp=len(reg), gp_pre=int(x.pre.sum()),
                              min=mins, **{f"r_{s}": (x.w * x[s]).sum() / max((x.w * x["min"]).sum(), 1e-9) for s in STATS}, last=x.date.iloc[0]))
    agg = b.groupby("player_id").apply(_agg, include_groups=False) if len(b) else pd.DataFrame()
    if agg.empty:
        return []
    # current team: today's roster beats last season's box score (trades, signings)
    team = agg.last_team.copy()
    shots = {}
    if roster is not None and len(roster):
        rmap = roster.drop_duplicates("player_id").set_index("player_id")
        team.update(rmap.team.reindex(agg.index).dropna())
        shots = rmap.headshot.to_dict()
        on_roster = set(rmap.index)
        agg = agg[agg.index.isin(on_roster)]
        team = team.reindex(agg.index)
    agg["team"] = team
    st = {}
    if inj is not None and len(inj):
        st = inj.drop_duplicates("player_id").set_index("player_id")[["status", "detail"]].to_dict("index")
    out = []
    for gm in slate:
        for side, opp, pts_team in ((gm["home"], gm["away"], gm["pts_home"]), (gm["away"], gm["home"], gm["pts_away"])):
            P = agg[agg.team == side].copy()
            if P.empty:
                continue
            P["status"] = [st.get(i, {}).get("status", "") for i in P.index]
            P["mult"] = [inj_mult(s) for s in P.status]
            P["pm"] = P["min"] * P.mult
            P = P[P.pm >= 4]
            if P.empty:
                continue
            P = P.sort_values("pm", ascending=False).head(13)
            tot = P.pm.sum()
            if tot > 0:
                P["pm"] = np.minimum(P.pm * min(1.25, 240.0 / tot), 40.0)       # a team plays 240 minutes
            raw = {s: P.pm * P[f"r_{s}"] for s in STATS}
            k = float(np.clip(pts_team / max(raw["pts"].sum(), 1e-9), 0.85, 1.15))   # points sum to the team's projected score
            for pid, r in P.iterrows():
                v = {s: float(raw[s].loc[pid]) for s in STATS}
                v["pts"] *= k
                v["ast"] *= math.sqrt(k)
                out.append(dict(id=str(pid), name=r["name"], team=side, opp=opp, game_id=gm["game_id"], pos=r.pos,
                                headshot=shots.get(pid) or f"https://a.espncdn.com/i/headshots/nba/players/full/{pid}.png",
                                status=r.status, gp=int(r.gp), gp_pre=int(r.gp_pre), min=round(float(r.pm), 1),
                                pts=round(v["pts"], 1), reb=round(v["reb"], 1), ast=round(v["ast"], 1), fg3=round(v["fg3"], 2),
                                sd=dict(pts=round(0.35 * v["pts"] + 2.2, 2), reb=round(1.15 * math.sqrt(max(v["reb"], .1)) + 0.4, 2),
                                        ast=round(1.2 * math.sqrt(max(v["ast"], .1)) + 0.3, 2))))
                out[-1].update(dd=round(p_double(out[-1], out[-1]["sd"], 2), 3), trip=round(p_double(out[-1], out[-1]["sd"], 3), 3))
    return sorted(out, key=lambda p: -p["pts"])


def p_over(mean: float, sd: float, line: float) -> float:
    """Chance a stat clears line (line ends in .5): normal with a continuity correction."""
    return 1 - phi((line - mean) / max(sd, 1e-6))


def p_threes(mean: float, line: float) -> float:
    """Threes made: Poisson."""
    k, lam = int(math.floor(line)), max(mean, 1e-6)
    cdf, pm = 0.0, math.exp(-lam)
    for i in range(k + 1):
        cdf += pm; pm *= lam / (i + 1)
    return 1 - cdf


# Double-doubles and triple-doubles: ten or more in two (three) of points, rebounds and assists. The three stats are
# not independent: a player who plays long minutes fills every column at once. So the chance is mixed over a shared
# minutes factor (normal, sd MIN_SWING, by Gauss-Hermite quadrature) with the stats independent given it.
MIN_SWING = 0.16
_GH = ((-2.8570, 0.0113), (-1.3556, 0.2221), (0.0, 0.5333), (1.3556, 0.2221), (2.8570, 0.0113))   # probabilists' nodes, weights


def p_double(mean: dict, sd: dict, need: int = 2) -> float:
    """Chance at least `need` of pts, reb, ast reach 10 (need=2 a double-double, 3 a triple-double)."""
    out = 0.0
    for z, w in _GH:
        f = max(0.0, 1 + MIN_SWING * z)
        q = []
        for k in ("pts", "reb", "ast"):
            m, s = mean[k], sd[k]
            sc = math.sqrt(max(s * s - (MIN_SWING * m) ** 2, 0.25 * s * s))   # the spread left once minutes are known
            q.append(p_over(m * f, sc, 9.5))
        a, b, c = q
        two = a * b * (1 - c) + a * (1 - b) * c + (1 - a) * b * c
        out += w * (a * b * c + (two if need == 2 else 0.0))
    return float(min(1.0, max(0.0, out)))


def double_check(box: pd.DataFrame, games: pd.DataFrame, n_games: int = 500, n_recent: int = 30, decay: float = 0.9) -> dict:
    """Backtest: each player's last n_games regular-season and playoff games, projected from his games before it (per
    minute rates times average minutes, the page's spreads), the chances above against what happened."""
    meta = games.set_index("game_id")[["date", "season_type"]]
    b = box.join(meta, on="game_id", how="inner")
    b = b[b.season_type.isin([2, 3]) & (b["min"] > 0)].copy()
    b["date"] = pd.to_datetime(b.date)
    b = b.sort_values("date")
    test_ids = set(b.drop_duplicates("game_id").game_id.tail(n_games))
    rows = []
    for pid, x in b.groupby("player_id"):
        x = x.reset_index(drop=True)
        for i in x.index[x.game_id.isin(test_ids)]:
            h = x.iloc[max(0, i - n_recent):i]
            if len(h) < 5:
                continue
            w = decay ** np.arange(len(h))[::-1]
            mins = float(np.average(h["min"], weights=w))
            v = {s: mins * float((w * h[s]).sum() / max((w * h["min"]).sum(), 1e-9)) for s in ("pts", "reb", "ast")}
            sd = dict(pts=0.35 * v["pts"] + 2.2, reb=1.15 * math.sqrt(max(v["reb"], .1)) + 0.4, ast=1.2 * math.sqrt(max(v["ast"], .1)) + 0.3)
            r = x.loc[i]
            n10 = int(r.pts >= 10) + int(r.reb >= 10) + int(r.ast >= 10)
            rows.append((p_double(v, sd, 2), p_double(v, sd, 3), n10 >= 2, n10 >= 3))
    if not rows:
        return {}
    R = pd.DataFrame(rows, columns=["pdd", "ptd", "dd", "td"])
    out = dict(n=len(R), dd_exp=round(float(R.pdd.sum())), dd=int(R.dd.sum()), td_exp=round(float(R.ptd.sum()), 1), td=int(R.td.sum()))
    for lo, hi in ((0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)):
        g = R[(R.pdd >= lo) & (R.pdd < hi)]
        out[f"dd{int(100 * lo)}"] = f"{len(g)}:{g.pdd.mean():.2f}/{g.dd.mean():.2f}" if len(g) else "-"
    for lo, hi in ((0.05, 0.15), (0.15, 0.3), (0.3, 1.01)):
        g = R[(R.ptd >= lo) & (R.ptd < hi)]
        out[f"td{int(100 * lo)}"] = f"{len(g)}:{g.ptd.mean():.2f}/{g.td.mean():.2f}" if len(g) else "-"
    return out
