"""What the game simulator plays from: league tendencies, team profiles and player traits, built from nflverse play-by-play.

Everything is season to date, with last season blended in while the sample is small and every team and player rate
shrunk toward the league so a few games can't swing it. The page (sim.html) combines an offence's numbers with the
defence's (relative to the league) for each matchup.

  league   how often teams pass by down and distance, go for it on 4th down by field position, field-goal accuracy
           by distance, two-point tries, seconds between snaps, penalties by type, kickoffs and punts, and the full
           spread of yards on runs, scrambles, completions, sacks and returns
  teams    offence and defence: pass rate over expected, pace, sack, interception, fumble, completion and explosive
           rates, yards per attempt and carry, red-zone touchdowns, third downs, penalties, 4th-down aggressiveness;
           plus the kicker, punter, returners, defenders (tackles, sacks, picks, passes defended) and head coach
  players  depth of target, yards after catch, red-zone and deep target share, goal-line carries, breakaway rate,
           and for quarterbacks scramble, sack, interception and deep-ball rates
"""
from __future__ import annotations

import io
import json
import os
from collections import defaultdict

import numpy as np
import pandas as pd

from . import data

COLS = ["game_id", "season", "week", "season_type", "posteam", "defteam", "home_team", "away_team", "play_id", "qtr", "down",
        "ydstogo", "yardline_100", "game_seconds_remaining", "half_seconds_remaining", "score_differential", "wp", "play_type",
        "pass", "rush", "qb_dropback", "qb_scramble", "qb_kneel", "qb_spike", "sack", "interception", "fumble_lost",
        "complete_pass", "pass_attempt", "rush_attempt", "air_yards", "yards_after_catch", "yards_gained", "passing_yards",
        "rushing_yards", "receiving_yards", "pass_oe", "no_huddle", "penalty", "penalty_team", "penalty_type", "penalty_yards",
        "first_down_penalty", "third_down_converted", "third_down_failed", "field_goal_attempt", "field_goal_result",
        "kick_distance", "extra_point_attempt", "extra_point_result", "two_point_attempt", "two_point_conv_result", "touchdown",
        "punt_attempt", "kickoff_attempt", "touchback", "return_yards", "punt_fair_catch", "punt_inside_twenty",
        "kicker_player_name", "punter_player_name", "kickoff_returner_player_name", "punt_returner_player_name",
        "passer_player_id", "rusher_player_id", "receiver_player_id", "solo_tackle_1_player_name", "solo_tackle_2_player_name",
        "assist_tackle_1_player_name", "assist_tackle_2_player_name", "tackle_with_assist_1_player_name",
        "tackle_with_assist_2_player_name", "sack_player_name", "half_sack_1_player_name", "half_sack_2_player_name",
        "interception_player_name", "pass_defense_1_player_name", "pass_defense_2_player_name", "qb_hit_1_player_name",
        "fixed_drive", "fixed_drive_result", "drive_inside20", "home_coach", "away_coach", "timeout"]
TOGO = [(1, 1, "1"), (2, 3, "2-3"), (4, 6, "4-6"), (7, 10, "7-10"), (11, 99, "11+")]
FIELD = [(61, 99, "own"), (41, 60, "mid"), (31, 40, "edge"), (1, 30, "fg")]   # by yards to the end zone
# the probabilities each yardage spread is kept at: every 2.5%, finer in the long tail where the big plays live
QP = [round(v, 4) for v in list(np.linspace(0, .95, 39)) + [.96, .97, .98, .985, .99, .995, .998, 1.0]]


def _q(x) -> list:
    x = pd.Series(x).dropna().astype(float)
    return [round(float(v), 1) for v in np.quantile(x, QP)] if len(x) >= 20 else []


def _bucket(v, table):
    for lo, hi, k in table:
        if lo <= v <= hi:
            return k
    return table[-1][2]


def _shrink(num, den, prior, k):
    """A rate pulled toward the prior by k pseudo-observations."""
    return float((num + prior * k) / (den + k)) if den + k > 0 else float(prior)


def load(seasons, cache: str | None = None, log=print) -> pd.DataFrame:
    """Regular- and post-season plays for the given seasons; finished seasons are cached."""
    out = []
    for s in seasons:
        path = os.path.join(cache, f"sim_pbp{s}.parquet") if cache else None
        if path and os.path.exists(path) and s < max(seasons):
            out.append(pd.read_parquet(path)); continue
        try:
            raw = data._get(data.PBP_URL.format(season=s)) if not data.LOCAL else open(os.path.join(data.LOCAL, f"pbp{s}.parquet"), "rb").read()
            p = pd.read_parquet(io.BytesIO(raw), columns=[c for c in COLS if c])
        except Exception as e:   # noqa: BLE001 - a missing season only thins the sample
            log(f"nfl sim: no play-by-play for {s} ({e})"); continue
        for c in ("home_team", "away_team", "posteam", "defteam", "penalty_team"):
            p[c] = p[c].replace(data.TEAM_FIX)
        if path and s < max(seasons):   # finished seasons don't change
            os.makedirs(cache, exist_ok=True); p.to_parquet(path)
        out.append(p)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=COLS)


def build(p: pd.DataFrame, season: int) -> dict:
    p = p[p.season_type.isin(["REG", "POST"]) | p.season_type.isna()].copy()
    cur = p.season == season
    weeks = int(p.loc[cur, "week"].max()) if cur.any() else 0
    w_prev = max(.15, .7 - .05 * weeks)            # last season counts less every week
    p["w"] = np.where(cur, 1.0, w_prev)
    scrim = p[p.play_type.isin(["pass", "run"]) & p.down.notna() & (p.two_point_attempt != 1)].copy()
    scrim["dropb"] = (scrim.qb_dropback == 1)
    scrim["att"] = (scrim.pass_attempt == 1) & (scrim.sack != 1) & (scrim.qb_spike != 1)
    scrim["design"] = (scrim.play_type == "run") & (scrim.qb_scramble != 1) & (scrim.qb_kneel != 1)
    scrim["neutral"] = scrim.wp.between(.2, .8) & (scrim.qtr <= 3) & (scrim.half_seconds_remaining > 120)
    W = lambda m, col=None: float((scrim.loc[m, "w"] * (scrim.loc[m, col] if col else 1)).sum())

    # ---------- league ----------
    L = {}
    pass_dd = {}
    for d in (1, 2, 3, 4):
        for lo, hi, k in TOGO:
            m = scrim.neutral & (scrim.down == d) & scrim.ydstogo.between(lo, hi)
            if W(m) >= 30:
                pass_dd[f"{d}|{k}"] = round(W(m & scrim.dropb) / W(m), 3)
    L["pass_dd"] = pass_dd
    drops, atts, designs = scrim[scrim.dropb], scrim[scrim.att], scrim[scrim.design]
    wsum = lambda d, c=None: float((d.w * (d[c] if c else 1)).sum())
    L["rates"] = dict(
        sack=wsum(drops, "sack") / wsum(drops), int=wsum(atts, "interception") / wsum(atts),
        cmp=wsum(atts, "complete_pass") / wsum(atts), ypa=wsum(atts, "passing_yards") / wsum(atts) if "passing_yards" in atts else 7.0,
        ypc=float((designs.w * designs.rushing_yards.fillna(0)).sum() / wsum(designs)),
        scr=wsum(drops, "qb_scramble") / wsum(drops), fum=wsum(scrim, "fumble_lost") / wsum(scrim),
        xr=float((designs.w * (designs.rushing_yards >= 10)).sum() / wsum(designs)), xp=float((atts.w * (atts.passing_yards.fillna(0) >= 20)).sum() / wsum(atts)),
        third=float(p.third_down_converted.fillna(0).mul(p.w).sum() / (p.third_down_converted.fillna(0) + p.third_down_failed.fillna(0)).mul(p.w).sum()),
    )
    L["rates"] = {k: round(v, 4) for k, v in L["rates"].items()}
    # 4th downs: go-for-it rate by field position and distance
    f4 = p[(p.down == 4) & p.play_type.isin(["pass", "run", "punt", "field_goal"]) & (p.qtr <= 3) & p.wp.between(.1, .9)].copy()
    f4["go"] = f4.play_type.isin(["pass", "run"])
    f4["fb"] = f4.yardline_100.map(lambda v: _bucket(v, FIELD)); f4["tb"] = f4.ydstogo.map(lambda v: _bucket(min(v, 11), [(1, 1, "1"), (2, 3, "2-3"), (4, 99, "4+")]))
    go4 = {}
    for (fb, tb), g in f4.groupby(["fb", "tb"]):
        go4[f"{fb}|{tb}"] = round(_shrink((g.go * g.w).sum(), g.w.sum(), .2, 10), 3)
    L["go4"] = go4
    # field goals: a logistic curve in distance
    fg = p[(p.field_goal_attempt == 1) & p.kick_distance.notna()].copy()
    fg["made"] = (fg.field_goal_result == "made").astype(float)
    a, b = _logit_fit(fg.kick_distance.values, fg.made.values, fg.w.values)
    L["fg"] = dict(a=round(a, 4), b=round(b, 5))
    xp = p[p.extra_point_attempt == 1]
    L["xp"] = round(float(((xp.extra_point_result == "good") * xp.w).sum() / max(1, xp.w.sum())), 4)
    tds = p[(p.touchdown == 1) & p.posteam.notna() & (p.play_type.isin(["pass", "run"]))]
    two = p[p.two_point_attempt == 1]
    L["two"] = dict(rate=round(float(len(two)) / max(1, len(tds)), 4), succ=round(float((two.two_point_conv_result == "success").mean() if len(two) else .48), 4))
    # seconds between snaps (clock running) and in a hurry
    s = p[p.play_type.isin(["pass", "run"]) & p.game_seconds_remaining.notna()].sort_values(["game_id", "play_id"])
    s = s.assign(dt=s.groupby("game_id").game_seconds_remaining.shift(0) - s.groupby("game_id").game_seconds_remaining.shift(-1),
                 nxt_qtr=s.groupby("game_id").qtr.shift(-1), nxt_pos=s.groupby("game_id").posteam.shift(-1))
    run_clock = s[(s.nxt_qtr == s.qtr) & (s.nxt_pos == s.posteam) & (s.timeout != 1) & (s.penalty != 1) &
                  ((s.play_type == "run") | (s.complete_pass == 1)) & s.dt.between(10, 60)]
    calm, hurry = run_clock[run_clock.half_seconds_remaining > 300], run_clock[(run_clock.half_seconds_remaining <= 120) & (run_clock.score_differential < 0)]
    inc = s[(s.nxt_qtr == s.qtr) & (s.nxt_pos == s.posteam) & (s.pass_attempt == 1) & (s.complete_pass == 0) & (s.sack != 1) & s.dt.between(1, 20)]
    L["secs"] = dict(run=round(float(calm.dt.median()), 1) if len(calm) else 36.0, hurry=round(float(hurry.dt.median()), 1) if len(hurry) > 20 else 18.0,
                     inc=round(float(inc.dt.median()), 1) if len(inc) else 6.0)
    # yardage spreads
    L["qp"] = QP
    L["q"] = dict(run=_q(designs.rushing_yards), scr=_q(scrim[scrim.qb_scramble == 1].rushing_yards), comp=_q(atts[atts.complete_pass == 1].passing_yards),
                  air=_q(atts[atts.complete_pass == 1].air_yards), yac=_q(atts[atts.complete_pass == 1].yards_after_catch),
                  sack=_q(-scrim[scrim.sack == 1].yards_gained), intret=_q(p[p.interception == 1].return_yards),
                  punt=_q(p[p.punt_attempt == 1].kick_distance), pret=_q(p[(p.punt_attempt == 1) & (p.return_yards > 0)].return_yards),
                  kret=_q(p[(p.kickoff_attempt == 1) & (p.touchback != 1) & p.return_yards.notna()].return_yards))
    ko, pu = p[p.kickoff_attempt == 1], p[p.punt_attempt == 1]
    L["ko"] = dict(tb=round(float(ko.touchback.fillna(0).mean()), 3) if len(ko) else .6)
    L["punt"] = dict(tb=round(float(pu.touchback.fillna(0).mean()), 3), fc=round(float(pu.punt_fair_catch.fillna(0).mean()), 3), in20=round(float(pu.punt_inside_twenty.fillna(0).mean()), 3)) if len(pu) else {}
    # penalties: per snap, by type and side, with yards and whether they give an automatic first down
    pen = p[(p.penalty == 1) & p.penalty_type.notna() & p.penalty_yards.notna() & p.posteam.notna()].copy()
    pen["side"] = np.where(pen.penalty_team == pen.posteam, "off", "def")
    snaps = float(len(scrim))
    rows = []
    for (t, side), g in pen.groupby(["penalty_type", "side"]):
        if len(g) < 8:
            continue
        rows.append(dict(t=t, side=side, rate=round(len(g) / snaps, 5), yds=round(float(g.penalty_yards.median()), 1),
                         fd=round(float(g.first_down_penalty.fillna(0).mean()), 2), pre=bool(g.play_type.isin(["no_play"]).mean() > .8 and t in PRESNAP)))
    L["pens"] = sorted(rows, key=lambda r: -r["rate"])[:16]

    # ---------- teams ----------
    teams = {}
    lr = L["rates"]
    for tm in sorted(set(scrim.posteam.dropna())):
        O, D = scrim[scrim.posteam == tm], scrim[scrim.defteam == tm]
        o, d = {}, {}
        for side, X, out in (("o", O, o), ("d", D, d)):
            dr, at, de = X[X.dropb], X[X.att], X[X.design]
            out["sack"] = _shrink((dr.w * dr.sack).sum(), dr.w.sum(), lr["sack"], 120) / lr["sack"]
            out["int"] = _shrink((at.w * at.interception).sum(), at.w.sum(), lr["int"], 250) / lr["int"]
            out["cmp"] = _shrink((at.w * at.complete_pass).sum(), at.w.sum(), lr["cmp"], 120) / lr["cmp"]
            out["ypa"] = _shrink((at.w * at.passing_yards.fillna(0)).sum(), at.w.sum(), lr["ypa"], 150) / lr["ypa"]
            out["ypc"] = _shrink((de.w * de.rushing_yards.fillna(0)).sum(), de.w.sum(), lr["ypc"], 120) / lr["ypc"]
            out["xr"] = _shrink((de.w * (de.rushing_yards >= 10)).sum(), de.w.sum(), lr["xr"], 150) / lr["xr"]
            out["xp"] = _shrink((at.w * (at.passing_yards.fillna(0) >= 20)).sum(), at.w.sum(), lr["xp"], 150) / lr["xp"]
            out["fum"] = _shrink((X.w * X.fumble_lost).sum(), X.w.sum(), lr["fum"], 400) / lr["fum"]
            pt = p[(p.posteam == tm) if side == "o" else (p.defteam == tm)]
            c3, f3 = (pt.third_down_converted.fillna(0) * pt.w).sum(), (pt.third_down_failed.fillna(0) * pt.w).sum()
            out["third"] = _shrink(c3, c3 + f3, lr["third"], 40) / lr["third"]
            dv = pt.drop_duplicates(["game_id", "fixed_drive"])
            rz = dv[dv.drive_inside20 == 1]
            out["rz"] = _shrink(((rz.fixed_drive_result == "Touchdown") * rz.w).sum(), rz.w.sum(), .57, 12) / .57
            sd = "off" if side == "o" else "def"
            mine = pen[(pen.penalty_team == tm) & (pen.side == sd)]
            out["pen"] = _shrink(float(mine.w.sum()), float(X.w.sum()), sum(r["rate"] for r in L["pens"] if r["side"] == sd), 300) / max(1e-6, sum(r["rate"] for r in L["pens"] if r["side"] == sd))
        neu = O[O.neutral & O.pass_oe.notna()]
        o["proe"] = round(float((neu.w * neu.pass_oe).sum() / max(1, neu.w.sum())) * neu.w.sum() / (neu.w.sum() + 80) / 100, 4)   # pass rate over expected, as a fraction
        ts = calm[calm.posteam == tm]
        o["pace"] = round(float(ts.dt.median()) / L["secs"]["run"], 3) if len(ts) >= 30 else 1.0
        g4 = f4[f4.posteam == tm]
        exp_go = sum(go4.get(f"{r.fb}|{r.tb}", .2) * r.w for r in g4.itertuples())
        o["go4"] = round(_shrink(float((g4.go * g4.w).sum()), exp_go, 1.0, 6) if exp_go > 0 else 1.0, 3)
        o, d = ({k: round(v, 4) if isinstance(v, float) else v for k, v in x.items()} for x in (o, d))
        teams[tm] = dict(o=o, d=d, **_special(p, tm, season, L), **_defenders(p, tm, season))
        last = p[(p.home_team == tm) | (p.away_team == tm)].sort_values(["season", "week"]).tail(1)
        if len(last):
            r = last.iloc[0]; teams[tm]["coach"] = r.home_coach if r.home_team == tm else r.away_coach

    return dict(v=1, season=season, through_week=weeks, built=pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds"),
                league=L, teams=teams, players=_players(scrim, season))


PRESNAP = {"False Start", "Defensive Offside", "Neutral Zone Infraction", "Encroachment", "Delay of Game", "Illegal Formation", "Illegal Shift", "Illegal Motion", "Defensive Delay of Game"}


def _logit_fit(x, y, w, iters=25):
    """Weighted logistic regression of made kicks on distance (Newton's method)."""
    a, b = 6.0, -.1
    for _ in range(iters):
        z = np.clip(a + b * x, -30, 30); pr = 1 / (1 + np.exp(-z)); s = w * pr * (1 - pr)
        g = np.array([np.sum(w * (y - pr)), np.sum(w * (y - pr) * x)])
        H = np.array([[np.sum(s), np.sum(s * x)], [np.sum(s * x), np.sum(s * x * x)]])
        try:
            da, db = np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            break
        a, b = a + da, b + db
    return float(a), float(b)


def _special(p, tm, season, L) -> dict:
    """The kicker, punter and returners this team uses now, and how they do."""
    out = {}
    cur = p[p.season == season]
    fga = p[(p.field_goal_attempt == 1) & (p.posteam == tm) & p.kick_distance.notna()]
    kname = (cur[(cur.posteam == tm) & ((cur.field_goal_attempt == 1) | (cur.extra_point_attempt == 1))].kicker_player_name.dropna().tail(12).mode())
    if len(kname):
        k = kname.iloc[0]; mine = fga[fga.kicker_player_name == k]
        pr = 1 / (1 + np.exp(-(L["fg"]["a"] + L["fg"]["b"] * mine.kick_distance.values)))
        made = (mine.field_goal_result == "made").astype(float).values
        off = float(np.sum(made - pr) / (np.sum(pr * (1 - pr)) + 12)) if len(mine) else 0.0   # log-odds edge over the league curve, shrunk
        xpk = p[(p.extra_point_attempt == 1) & (p.kicker_player_name == k)]
        out["k"] = dict(name=k, off=round(off, 3), fg=f"{int(made.sum())}/{len(mine)}", lng=int(mine[mine.field_goal_result == "made"].kick_distance.max()) if (made > 0).any() else None,
                        xp=round(_shrink(float((xpk.extra_point_result == "good").sum()), len(xpk), L["xp"], 40), 4))
    pu = p[(p.punt_attempt == 1) & (p.posteam == tm)]
    pname = cur[(cur.punt_attempt == 1) & (cur.posteam == tm)].punter_player_name.dropna().tail(15).mode()
    if len(pname):
        mine = pu[pu.punter_player_name == pname.iloc[0]]
        lg = float(np.median([v for v in L["q"]["punt"]])) if L["q"]["punt"] else 47.0
        out["p"] = dict(name=pname.iloc[0], gross=round(_shrink(float(mine.kick_distance.fillna(0).sum()), len(mine), lg, 15), 1),
                        in20=round(_shrink(float(mine.punt_inside_twenty.fillna(0).sum()), len(mine), L["punt"].get("in20", .4), 20), 3))
    for key, col, kind in (("kr", "kickoff_returner_player_name", "kickoff_attempt"), ("pr", "punt_returner_player_name", "punt_attempt")):
        r = cur[(cur[kind] == 1) & (cur.defteam == tm)][col].dropna()
        if len(r):
            out[key] = r.value_counts().index[0]
    ko = p[(p.kickoff_attempt == 1) & (p.posteam == tm)]
    out["ko_tb"] = round(_shrink(float(ko.touchback.fillna(0).sum()), len(ko), L["ko"]["tb"], 25), 3)
    return out


def _defenders(p, tm, season) -> dict:
    """Who makes this defence's tackles, sacks, interceptions and pass breakups, as shares of the team's total."""
    cur = p[(p.season == season) & (p.defteam == tm)]
    if len(cur) < 150:
        cur = p[p.defteam == tm]
    tk, sk, it, pd_, hit = (defaultdict(float) for _ in range(5))
    for c in ("solo_tackle_1_player_name", "solo_tackle_2_player_name", "assist_tackle_1_player_name", "assist_tackle_2_player_name",
              "tackle_with_assist_1_player_name", "tackle_with_assist_2_player_name"):
        for n, v in cur[c].dropna().value_counts().items():
            tk[n] += v
    for n, v in cur.sack_player_name.dropna().value_counts().items(): sk[n] += v
    for c in ("half_sack_1_player_name", "half_sack_2_player_name"):
        for n, v in cur[c].dropna().value_counts().items(): sk[n] += .5 * v
    for n, v in cur.interception_player_name.dropna().value_counts().items(): it[n] += v
    for c in ("pass_defense_1_player_name", "pass_defense_2_player_name"):
        for n, v in cur[c].dropna().value_counts().items(): pd_[n] += v
    for n, v in cur.qb_hit_1_player_name.dropna().value_counts().items(): hit[n] += v
    names = sorted(set(tk) | set(sk) | set(it) | set(pd_), key=lambda n: -(tk[n] + 6 * sk[n] + 8 * it[n] + 2 * pd_[n]))[:18]
    tot = lambda dct: max(1e-9, sum(dct.values()))
    return dict(defs=[[n, round(tk[n] / tot(tk), 4), round((sk[n] + .3 * hit[n]) / max(1e-9, sum(sk.values()) + .3 * sum(hit.values())), 4),
                       round((it[n] + .25 * pd_[n]) / max(1e-9, sum(it.values()) + .25 * sum(pd_.values())), 4)] for n in names])


def _players(scrim, season) -> dict:
    """Per-player traits keyed by nflverse player id."""
    out = {}
    cur = scrim[scrim.season == season]
    tg = cur[cur.receiver_player_id.notna() & cur.att]
    team_rz = tg[tg.yardline_100 <= 20].groupby("posteam").size()
    for pid, g in tg.groupby("receiver_player_id"):
        if len(g) < 5:
            continue
        team = g.posteam.mode().iloc[0]
        rec = g[g.complete_pass == 1]
        out[pid] = dict(adot=round(float(g.air_yards.mean()), 1), yac=round(float(rec.yards_after_catch.mean()), 1) if len(rec) else None,
                        deep=round(float((g.air_yards >= 20).mean()), 3),
                        rz=round(float((g.yardline_100 <= 20).sum()) / max(1, int(team_rz.get(team, 0))), 3))
    ru = cur[cur.rusher_player_id.notna() & cur.design]
    gl = ru[ru.yardline_100 <= 5].groupby("posteam").size()
    for pid, g in ru.groupby("rusher_player_id"):
        if len(g) < 8:
            continue
        team = g.posteam.mode().iloc[0]
        o = out.setdefault(pid, {})
        o.update(gl=round(float((g.yardline_100 <= 5).sum()) / max(1, int(gl.get(team, 0))), 3), brk=round(float((g.rushing_yards >= 10).mean()), 3),
                 stuff=round(float((g.rushing_yards <= 0).mean()), 3))
    dr = cur[cur.dropb & cur.passer_player_id.notna()]
    scr = cur[(cur.qb_scramble == 1)]
    for pid, g in dr.groupby("passer_player_id"):
        if len(g) < 40:
            continue
        a = g[g.att]
        o = out.setdefault(pid, {})
        o.update(scr=round(_shrink(float((g.qb_scramble == 1).sum()), len(g), .05, 60), 4), sack=round(_shrink(float(g.sack.sum()), len(g), .066, 80), 4),
                 int=round(_shrink(float(a.interception.sum()), len(a), .023, 200), 4), deep=round(float((a.air_yards >= 20).mean()), 3),
                 adot=round(float(a.air_yards.mean()), 1), cmp=round(float(a.complete_pass.mean()), 3))
    return out


def clean(o):
    """JSON-safe: numpy numbers to Python, NaN to null."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return None if np.isnan(o) else round(float(o), 4)
    return o


def run(state: str = "state", season: int | None = None, log=print) -> dict | None:
    cache, site = os.path.join(state, "intermediate", "nfl"), os.path.join(state, "site")
    season = season or data.season_of(pd.Timestamp.now(tz="America/New_York"))
    p = load([season - 1, season], cache, log)
    if not len(p):
        log("nfl sim: no plays"); return None
    out = build(p, season)
    os.makedirs(site, exist_ok=True)
    json.dump(clean(out), open(os.path.join(site, "nfl_sim.json"), "w"), separators=(",", ":"))
    log(f"nfl sim: {len(out['teams'])} teams, {len(out['players'])} players, through week {out['through_week']}")
    return out


if __name__ == "__main__":
    run()
