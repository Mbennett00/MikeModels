"""Synthetic league generator.

Used ONLY to exercise the pipeline end to end (tests, CI, smoke runs) when the
real sources are unreachable. Numbers produced from it say nothing about real
betting performance. Parameters of the generating process are returned so tests
can check that the fitting code recovers them.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

TEAMS = ["ANA", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI", "COL", "DAL", "DET", "EDM",
         "FLA", "LAK", "MIN", "MTL", "NJD", "NSH", "NYI", "NYR", "OTT", "PHI", "PIT",
         "SEA", "SJS", "STL", "TBL", "TOR", "UTA", "VAN", "VGK", "WPG", "WSH"]

TRUE = dict(base=2.95, home=1.035, lam3=0.12, pp_share=0.22, b2b=0.95,
            en_p={1: 0.30, 2: 0.18}, en_p2=0.06, p1_share=0.30, ot_beta=0.8,
            ot_goal_share=0.65, nb_r={"F": 8.0, "D": 6.0})

F_TOI = [16.0, 14.5, 12.0, 9.5]
D_TOI = [19.5, 17.0, 14.0]
F_IXG = [0.95, 0.75, 0.55, 0.40]
D_IXG = [0.24, 0.19, 0.15]


def _players(rng, teams):
    rows, pid = [], 8470000
    for t in teams:
        for li in range(4):
            for _ in range(3):
                pid += 1
                rows.append(dict(player_id=pid, name=f"{t} F{pid % 1000}", team=t, pos="F",
                                 line=f"F{li+1}",
                                 ixg=F_IXG[li] * rng.lognormal(0, 0.18),
                                 ixg_pp=2.2 * rng.lognormal(0, 0.25),
                                 sog=(8.5 - li * 0.8) * rng.lognormal(0, 0.15),
                                 ast=(1.3 - 0.2 * li) * rng.lognormal(0, 0.25),
                                 finish=rng.lognormal(0, 0.05)))
        for li in range(3):
            for _ in range(2):
                pid += 1
                rows.append(dict(player_id=pid, name=f"{t} D{pid % 1000}", team=t, pos="D",
                                 line=f"D{li+1}",
                                 ixg=D_IXG[li] * rng.lognormal(0, 0.18),
                                 ixg_pp=0.8 * rng.lognormal(0, 0.25),
                                 sog=(5.0 - li * 0.6) * rng.lognormal(0, 0.15),
                                 ast=(1.0 - 0.15 * li) * rng.lognormal(0, 0.25),
                                 finish=1.0))
    p = pd.DataFrame(rows)
    # PP units: PP1 = top-4 F by ixg_pp + top D; PP2 = next 4 F + next D
    p["pp_unit"] = 0
    for t, g in p.groupby("team"):
        f = g[g.pos == "F"].sort_values("ixg_pp", ascending=False).index
        d = g[g.pos == "D"].sort_values("ixg_pp", ascending=False).index
        p.loc[list(f[:4]) + [d[0]], "pp_unit"] = 1
        p.loc[list(f[4:8]) + [d[1]], "pp_unit"] = 2
    return p


def _schedule(rng, season, teams, n_days=175):
    start = pd.Timestamp(f"{season}-10-08")
    days = pd.date_range(start, periods=n_days, freq="D")
    rows, gid = [], season * 1000000 + 20000
    for d in days:
        n = rng.integers(4, 12)
        ts = rng.permutation(teams)[: 2 * n]
        for i in range(n):
            gid += 1
            rows.append(dict(game_id=gid, date=d, season=season, home=ts[2 * i], away=ts[2 * i + 1]))
    return pd.DataFrame(rows)


def generate(seed: int = 7, seasons=(2024, 2025), with_odds: bool = True, n_days: int = 175):
    rng = np.random.default_rng(seed)
    teams = TEAMS
    tm = pd.DataFrame(dict(team=teams,
                           off=rng.lognormal(0, 0.09, 32), dfn=rng.lognormal(0, 0.09, 32),
                           pp=rng.lognormal(0, 0.15, 32), pk=rng.lognormal(0, 0.15, 32),
                           pen=rng.lognormal(0, 0.12, 32), shots_allowed=rng.lognormal(0, 0.06, 32))
                      ).set_index("team")
    goalies = []
    gid0 = 8480000
    for t in teams:
        for j in range(2):
            gid0 += 1
            goalies.append(dict(goalie_id=gid0, name=f"{t} G{j+1}", team=t, starter=(j == 0),
                                ratio=float(np.clip(rng.normal(1.0 if j == 0 else 1.04, 0.05), 0.85, 1.2))))
    gl = pd.DataFrame(goalies)
    players = _players(rng, teams)

    sched = pd.concat([_schedule(rng, s, teams, n_days) for s in seasons], ignore_index=True)
    last_played: dict[str, pd.Timestamp] = {}
    G, TG, GG, PG, ODDS, LU = [], [], [], [], [], []
    T = TRUE
    for g in sched.itertuples(index=False):
        # goalies
        gsel = {}
        for side in (g.home, g.away):
            cand = gl[gl.team == side]
            st = cand[cand.starter].iloc[0] if rng.random() < 0.72 else cand[~cand.starter].iloc[0]
            gsel[side] = st
        b2b = {s: (s in last_played and (g.date - last_played[s]).days == 1) for s in (g.home, g.away)}
        lam, lam5, lampp, pens = {}, {}, {}, {}
        for side, opp in ((g.home, g.away), (g.away, g.home)):
            a, o = tm.loc[side], tm.loc[opp]
            n_pp = rng.poisson(3.0 * o.pen)  # penalties opp takes
            pens[side] = n_pp
            hf = T["home"] if side == g.home else 1 / T["home"]
            rest = T["b2b"] if b2b[side] else 1.0
            l5 = T["base"] * (1 - T["pp_share"]) * a.off * o.dfn
            lpp = T["base"] * T["pp_share"] * a.pp * o.pk * (o.pen)
            gr = gsel[opp].ratio
            lam5[side], lampp[side] = l5 * gr * hf * rest, lpp * gr * hf * rest
            lam[side] = lam5[side] + lampp[side]
        l3 = min(T["lam3"], 0.8 * min(lam.values()))
        x3 = rng.poisson(l3)
        h = rng.poisson(lam[g.home] - l3) + x3
        a_ = rng.poisson(lam[g.away] - l3) + x3
        # empty-net goals by the regulation leader
        en_h = en_a = 0
        d = h - a_
        if abs(d) in (1, 2):
            k = int(rng.random() < T["en_p"][abs(d)]) + int(rng.random() < T["en_p2"])
            if d > 0: en_h = k
            else: en_a = k
        hf_, af_ = h + en_h, a_ + en_a
        decision, ot_winner = "REG", None
        if hf_ == af_:
            share = lam[g.home] / (lam[g.home] + lam[g.away])
            p_home = 1 / (1 + np.exp(-T["ot_beta"] * 4 * (share - 0.5)))
            ot_winner = g.home if rng.random() < p_home else g.away
            decision = "OT" if rng.random() < T["ot_goal_share"] else "SO"
            if ot_winner == g.home: hf_ += 1
            else: af_ += 1
        p1h, p1a = rng.binomial(h, T["p1_share"]), rng.binomial(a_, T["p1_share"])
        G.append(dict(game_id=g.game_id, date=g.date, season=g.season, home=g.home, away=g.away,
                      home_reg_nonen=h, away_reg_nonen=a_, home_en_reg=en_h, away_en_reg=en_a,
                      home_final=hf_, away_final=af_, decision=decision, home_p1=p1h, away_p1=p1a))
        goals_side = {g.home: h, g.away: a_}
        en_side = {g.home: en_h, g.away: en_a}
        # split goals into 5v5 vs PP by expected share
        split = {}
        for s in (g.home, g.away):
            npp = rng.binomial(goals_side[s], lampp[s] / lam[s])
            split[s] = (goals_side[s] - npp, npp)
        # ---- player + team stats
        for side, opp in ((g.home, g.away), (g.away, g.home)):
            is_home = int(side == g.home)
            roster = players[players.team == side].copy()
            # occasional line shuffle between F2 and F3
            if rng.random() < 0.1:
                f2 = roster.index[roster.line == "F2"][rng.integers(3)]
                f3 = roster.index[roster.line == "F3"][rng.integers(3)]
                roster.loc[f2, "line"], roster.loc[f3, "line"] = "F3", "F2"
            toi5 = np.array([(F_TOI if r.pos == "F" else D_TOI)[int(r.line[1]) - 1] for r in roster.itertuples()])
            toi5 = toi5 * rng.lognormal(0, 0.08, len(toi5))
            team_pp_toi = 1.9 * pens[side] * rng.uniform(0.85, 1.05)
            ppshare = np.where(roster.pp_unit == 1, 0.66 / 5, np.where(roster.pp_unit == 2, 0.30 / 5, 0.0))
            toipp = team_pp_toi * ppshare * 5 / 1.0
            toipp = np.minimum(toipp, team_pp_toi)
            w5 = roster.ixg.values * toi5
            wpp = roster.ixg_pp.values * toipp + 1e-9
            ex5 = lam5[side] * w5 / w5.sum()
            expp = lampp[side] * wpp / wpp.sum()
            ixg5 = ex5 / roster.finish.values * rng.gamma(4, 0.25, len(ex5))
            ixgpp = expp / roster.finish.values * rng.gamma(4, 0.25, len(ex5))
            g5 = rng.multinomial(split[side][0], w5 / w5.sum())
            gpp = rng.multinomial(split[side][1], wpp / wpp.sum())
            fwd = (roster.pos == "F").values
            wen = np.where(fwd, roster.ixg.values, 0) + 1e-9
            gen = rng.multinomial(en_side[side], wen / wen.sum())
            got = np.zeros(len(roster), int)
            won_ot = decision == "OT" and ot_winner == side
            if won_ot:
                got[rng.choice(len(roster), p=w5 / w5.sum())] = 1
            a1_5 = np.zeros(len(roster), int); a2_5 = a1_5.copy(); a1pp = a1_5.copy(); a2pp = a1_5.copy()
            aw5 = roster.ast.values * toi5
            awpp = roster.ast.values * toipp + 1e-9
            for arr_g, w, A1, A2 in ((g5 + gen + got, aw5, a1_5, a2_5), (gpp, awpp, a1pp, a2pp)):
                for i, n in enumerate(arr_g):
                    for _ in range(n):
                        ww = w.copy(); ww[i] = 0
                        if rng.random() < 0.90:
                            j = rng.choice(len(ww), p=ww / ww.sum()); A1[j] += 1; ww[j] = 0
                            if rng.random() < 0.72:
                                k = rng.choice(len(ww), p=ww / ww.sum()); A2[k] += 1
            sa = tm.loc[opp].shots_allowed
            script = 1 + 0.10 * (0.5 - (lam[side] / (lam[side] + lam[opp])))
            mu5 = roster.sog.values * toi5 / 60 * sa * script * (T["home"] ** (1 if is_home else -1))
            mupp = roster.sog.values * 1.8 * toipp / 60 * sa
            mu = mu5 + mupp
            r = np.where(fwd, T["nb_r"]["F"], T["nb_r"]["D"])
            sog = stats.nbinom.rvs(r, r / (r + mu), random_state=rng)
            sog_pp = rng.binomial(sog, np.divide(mupp, mu, out=np.zeros_like(mu), where=mu > 0))
            sog = np.maximum(sog, g5 + gpp + gen + got)
            goals = g5 + gpp + gen + got
            assists = a1_5 + a2_5 + a1pp + a2pp
            for i, r_ in enumerate(roster.itertuples()):
                PG.append(dict(game_id=g.game_id, date=g.date, season=g.season, player_id=r_.player_id,
                               name=r_.name, team=side, opp=opp, is_home=is_home, pos=r_.pos,
                               line=r_.line, pp_unit=int(r_.pp_unit),
                               toi_5v5=toi5[i], toi_pp=toipp[i], ixg_5v5=ixg5[i], ixg_pp=ixgpp[i],
                               g_5v5=g5[i], g_pp=gpp[i], sog_5v5=int(sog[i] - sog_pp[i]), sog_pp=int(sog_pp[i]),
                               a1_5v5=a1_5[i], a2_5v5=a2_5[i], a1_pp=a1pp[i], a2_pp=a2pp[i],
                               ixg_nonen=ixg5[i] + ixgpp[i], g_nonen=g5[i] + gpp[i] + got[i],
                               goals=goals[i], assists=assists[i], sog=int(sog[i]),
                               points=goals[i] + assists[i], en_goals=gen[i],
                               _true_goal_mu=(ex5[i] + expp[i]), _true_sog_mu=mu[i]))
                if with_odds is not None:
                    LU.append(dict(date=g.date, game_id=g.game_id, team=side, player_id=r_.player_id,
                                   name=r_.name, pos=r_.pos, line=r_.line, pp_unit=int(r_.pp_unit), confirmed=True))
            gs = gsel[side]
            LU.append(dict(date=g.date, game_id=g.game_id, team=side, player_id=gs.goalie_id, name=gs["name"],
                           pos="G", line="G1", pp_unit=0, confirmed=True))
            xgf5 = ixg5.sum(); xgfpp = ixgpp.sum()
            TG.append(dict(game_id=g.game_id, date=g.date, season=g.season, team=side, opp=opp, is_home=is_home,
                           toi_5v5=toi5[fwd].sum() / 3, xgf_5v5=xgf5, xga_5v5=np.nan,
                           xgf_5v5_adj=xgf5, xga_5v5_adj=np.nan,
                           cf_5v5=rng.poisson(52 * tm.loc[side].off), ca_5v5=np.nan,
                           toi_pp=team_pp_toi, xgf_pp=xgfpp, toi_pk=np.nan, xga_pk=np.nan,
                           pen_taken=pens[opp], pen_drawn=pens[side], toi_all=60.0,
                           sog_for=int(sog.sum()), sog_against=np.nan, goals_nonen=goals_side[side]))
            GG.append(dict(game_id=g.game_id, date=g.date, season=g.season,
                           goalie_id=gsel[opp].goalie_id, name=gsel[opp]["name"], team=opp, toi=60.0,
                           xga=xgf5 + xgfpp, ga=goals_side[side]))
        for s in (g.home, g.away):
            last_played[s] = g.date
        if with_odds:
            ODDS.extend(_game_odds(rng, g, lam, l3))
    tg = pd.DataFrame(TG)
    opp_cols = tg[["game_id", "team", "xgf_5v5", "xgf_5v5_adj", "cf_5v5", "toi_pp", "xgf_pp", "sog_for"]].rename(
        columns={"team": "opp", "xgf_5v5": "xga_5v5", "xgf_5v5_adj": "xga_5v5_adj", "cf_5v5": "ca_5v5",
                 "toi_pp": "toi_pk", "xgf_pp": "xga_pk", "sog_for": "sog_against"})
    tg = tg.drop(columns=["xga_5v5", "xga_5v5_adj", "ca_5v5", "toi_pk", "xga_pk", "sog_against"]).merge(
        opp_cols, on=["game_id", "opp"])
    pg = pd.DataFrame(PG)
    truth = pg[["game_id", "player_id", "_true_goal_mu", "_true_sog_mu", "pos"]].copy()
    pg = pg.drop(columns=["_true_goal_mu", "_true_sog_mu"])
    tables = dict(games=pd.DataFrame(G), team_games=tg, goalie_games=pd.DataFrame(GG),
                  player_games=pg, lineups=pd.DataFrame(LU))
    if with_odds:
        odds = pd.DataFrame(ODDS)
        odds = pd.concat([odds, _player_odds(rng, pg, truth)], ignore_index=True)
        tables["odds"] = odds
    return tables, dict(true=TRUE, teams=tm, goalies=gl, players=players, truth=truth)


def _logit_noise(rng, p, sd, size=None):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    z = np.log(p / (1 - p)) + rng.normal(0, sd, size)
    return 1 / (1 + np.exp(-z))


def _vig2(rng, p, noise, vig=0.045):
    q = float(np.clip(_logit_noise(rng, p, noise), 0.02, 0.98))
    ia, ib = q * (1 + vig / 2), (1 - q) * (1 + vig / 2)
    return _to_am(ia), _to_am(ib)


def _to_am(ip):
    ip = float(np.clip(ip, 0.01, 0.99))
    return round(-100 * ip / (1 - ip)) if ip >= 0.5 else round(100 * (1 - ip) / ip)


def _game_odds(rng, g, lam, l3):
    from ..distributions import bivariate_poisson_matrix
    m = bivariate_poisson_matrix(lam[g.home], lam[g.away], l3)
    n = m.shape[0]
    hh, aa = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    p_home = m[hh > aa].sum() + 0.5 * m[hh == aa].sum()
    p_over = m[(hh + aa) > 6].sum()  # rough book view; +0.03 below stands in for EN/OT goals
    out = []
    for snap, noise in (("open", 0.12), ("close", 0.05)):
        for book in ("bookA", "bookB"):
            ph, pa = _vig2(rng, p_home, noise)
            po, pu = _vig2(rng, p_over + 0.03, noise)
            out += [dict(date=g.date, game_id=g.game_id, market="moneyline", player_id=np.nan, selection="home",
                         line=np.nan, price=ph, book=book, snapshot=snap),
                    dict(date=g.date, game_id=g.game_id, market="moneyline", player_id=np.nan, selection="away",
                         line=np.nan, price=pa, book=book, snapshot=snap),
                    dict(date=g.date, game_id=g.game_id, market="total", player_id=np.nan, selection="over",
                         line=6.5, price=po, book=book, snapshot=snap),
                    dict(date=g.date, game_id=g.game_id, market="total", player_id=np.nan, selection="under",
                         line=6.5, price=pu, book=book, snapshot=snap)]
    return out


def _player_odds(rng, pg, truth):
    t = pg[["date", "game_id", "player_id", "en_goals"]].merge(truth, on=["game_id", "player_id"])
    rows = []
    r = t.pos.map(TRUE["nb_r"]).values
    p_goal = 1 - np.exp(-t._true_goal_mu.values * 1.03)
    p_sog = stats.nbinom.sf(2, r, r / (r + t._true_sog_mu.values))
    for snap, noise in (("open", 0.15), ("close", 0.06)):
        qg = np.clip(_logit_noise(rng, p_goal, noise, len(t)), 0.02, 0.9)
        qs = np.clip(_logit_noise(rng, p_sog, noise, len(t)), 0.03, 0.97)
        for i in range(len(t)):
            base = dict(date=t.date.iat[i], game_id=t.game_id.iat[i], player_id=t.player_id.iat[i],
                        book="bookA", snapshot=snap)
            rows.append({**base, "market": "goals", "selection": "yes", "line": 0.5,
                         "price": _to_am(qg[i] * 1.12)})
            rows.append({**base, "market": "sog", "selection": "over", "line": 2.5,
                         "price": _to_am(qs[i] * 1.03)})
            rows.append({**base, "market": "sog", "selection": "under", "line": 2.5,
                         "price": _to_am((1 - qs[i]) * 1.03)})
    return pd.DataFrame(rows)
