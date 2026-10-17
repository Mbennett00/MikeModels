"""What the NHL game simulator plays from, built from the pipeline's NHL API tables (and the NHL stats API when reachable).

Season to date with last season blended in, every rate shrunk toward the league:

  league   how often a shot on goal goes in by distance and shot type, the rebound and power-play lifts, the mix of
           shot types, how often attempts are blocked or miss the net, penalties per 60, hits / blocks / takeaways /
           giveaways per 60
  teams    shot attempts for and against per 60 at 5-on-5, on the power play and short-handed; share of attempts on
           goal; how many opposing attempts they block; penalties taken and drawn per 60; rebound rate; the team-wide
           hits, blocks, giveaways, takeaways and faceoff rate
  players  position, ice time at even strength / power play / penalty kill, where his shots come from (a sample of real
           shot locations and types), how his shots split by strength, his most frequent assist partners, faceoff
           record, hits, blocks, penalty minutes, giveaways and takeaways per 60
  goalies  save percentage and goals saved above what the shot locations would predict
"""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

DIST = [0, 10, 20, 30, 40, 50, 60, 999]
TYPES = ["wrist", "snap", "slap", "tip-in", "backhand", "deflected", "wrap-around"]
STATS = "https://api.nhle.com/stats/rest/en"


def _shrink(num, den, prior, k):
    return float((num + prior * k) / (den + k)) if den + k > 0 else float(prior)


def _read(path, name):
    f = os.path.join(path, f"{name}.csv.gz")
    return pd.read_csv(f, low_memory=False) if os.path.exists(f) else pd.DataFrame()


def build(inter: str, season: int, api: dict | None = None) -> dict:
    S, G, P, PT, TT, GT, RO, GM = (_read(inter, n) for n in ("shots", "goals", "penalties", "player_toi", "team_toi", "goalie_toi", "roster", "games"))
    GM["season"] = GM.season.astype(int)
    seasons = sorted(GM.season.unique())
    season = season if season in seasons else seasons[-1]
    keep = GM[GM.season.isin([season - 1, season])]
    gid = set(keep.game_id)
    ncur = int((keep.season == season).sum())
    w_prev = max(.2, .8 - ncur / 600)                # last season fades as this one fills in (about 1,300 games a season)
    wmap = {g: (1.0 if s == season else w_prev) for g, s in zip(keep.game_id, keep.season)}
    for d in (S, G, P, PT, TT, GT, RO):
        if len(d):
            d.drop(d.index[~d.game_id.isin(gid)], inplace=True)
            d["w"] = d.game_id.map(wmap)
    S["shot_type"] = S.shot_type.replace({"bat": "deflected", "poke": "backhand", "between-legs": "backhand", "cradle": "wrap-around"})
    S["ax"] = S.x.abs(); S["ay"] = np.where(S.x >= 0, S.y, -S.y)          # every shot drawn attacking the right-hand net
    S["d"] = np.sqrt((89 - S.ax) ** 2 + S.ay ** 2)
    S["db"] = pd.cut(S.d, DIST, labels=False, include_lowest=True)
    og = S[S.on_goal & ~S.en_target.astype(bool)]

    # ---------- league ----------
    L = {}
    base = float((og.goal * og.w).sum() / og.w.sum())
    tab = {}
    for t in TYPES:
        row = []
        for b in range(len(DIST) - 1):
            m = og[(og.shot_type == t) & (og.db == b)]
            allb = og[og.db == b]
            prior = float((allb.goal * allb.w).sum() / max(1e-9, allb.w.sum()))
            row.append(round(_shrink(float((m.goal * m.w).sum()), float(m.w.sum()), prior, 150), 4))
        tab[t] = row
    L["xg"] = dict(dist=DIST[1:-1], tab=tab, base=round(base, 4))
    reb, nreb = og[og.rebound.astype(bool)], og[~og.rebound.astype(bool)]
    L["reb"] = dict(rate=round(float((S.rebound.astype(bool) * S.w).sum() / S.w.sum()), 4), lift=round(float(reb.goal.mean() / max(1e-9, nreb.goal.mean())), 3))
    for st in ("pp", "pk"):
        m = og[og.strength == st]
        L[f"{st}_lift"] = round(float(m.goal.mean() / max(1e-9, og[og.strength == "5v5"].goal.mean())), 3)
    ty = og.shot_type.value_counts(normalize=True)
    L["mix"] = {t: round(float(ty.get(t, 0)), 4) for t in TYPES}
    att = S
    L["att"] = dict(on=round(float(att.on_goal.mean()), 4), blocked=round(float((~att.unblocked.astype(bool)).mean()), 4))
    L["att"]["miss"] = round(1 - L["att"]["on"] - L["att"]["blocked"], 4)
    games = len(set(S.game_id))
    L["pen60"] = round(float(len(P)) / max(1, games) / 2, 3)   # per team per game

    # ---------- teams ----------
    teams = {}
    tw = TT.assign(**{c: TT[c] * TT.w for c in ("toi_5v5", "toi_pp", "toi_pk", "toi_all")}).groupby("team")[["toi_5v5", "toi_pp", "toi_pk", "toi_all", "w"]].sum()
    opp = {}
    for g, d in S.groupby("game_id"):
        tms = list(set(d.team))
        if len(tms) == 2:
            opp[(g, tms[0])], opp[(g, tms[1])] = tms[1], tms[0]
    S["opp"] = [opp.get((g, t)) for g, t in zip(S.game_id, S.team)]
    P["opp"] = [opp.get((g, t)) for g, t in zip(P.game_id, P.team)]
    lg_cf60 = float(S[S.strength == "5v5"].w.sum() / max(1e-9, tw.toi_5v5.sum()) * 60)
    lg_pp60 = float(S[S.strength == "pp"].w.sum() / max(1e-9, tw.toi_pp.sum()) * 60)
    lg_on = L["att"]["on"]
    L["cf60"], L["pp60"] = round(lg_cf60, 2), round(lg_pp60, 2)
    for tm in sorted(tw.index):
        t5, tp, tk, ta = (float(tw.loc[tm, c]) for c in ("toi_5v5", "toi_pp", "toi_pk", "toi_all"))
        mine, against = S[S.team == tm], S[S.opp == tm]
        cf = float(mine[mine.strength == "5v5"].w.sum()); ca = float(against[against.strength == "5v5"].w.sum())
        ppf = float(mine[mine.strength == "pp"].w.sum()); pka = float(against[against.strength == "pp"].w.sum())
        o = dict(
            cf60=round(_shrink(cf, t5 / 60, lg_cf60, 8) / lg_cf60, 4), ca60=round(_shrink(ca, t5 / 60, lg_cf60, 8) / lg_cf60, 4),
            pp60=round(_shrink(ppf, tp / 60, lg_pp60, 4) / lg_pp60, 4), pk60=round(_shrink(pka, tk / 60, lg_pp60, 4) / lg_pp60, 4),
            on=round(_shrink(float((mine.on_goal * mine.w).sum()), float(mine.w.sum()), lg_on, 400) / lg_on, 4),
            blk=round(_shrink(float((~against.unblocked.astype(bool) * against.w).sum()), float(against.w.sum()), L["att"]["blocked"], 400) / L["att"]["blocked"], 4),
            reb=round(_shrink(float((mine.rebound.astype(bool) * mine.w).sum()), float(mine.w.sum()), L["reb"]["rate"], 400) / L["reb"]["rate"], 4),
        )
        ng = float(tw.loc[tm, "w"])
        o["pen"] = round(_shrink(float(P[P.team == tm].w.sum()), ng, L["pen60"], 10) / L["pen60"], 4)
        o["drawn"] = round(_shrink(float(P[P.opp == tm].w.sum()), ng, L["pen60"], 10) / L["pen60"], 4)
        teams[tm] = o

    # ---------- goalies ----------
    xgt = lambda r: tab.get(r.shot_type, tab["wrist"])[int(r.db) if r.db == r.db else 3] * (L["reb"]["lift"] if r.rebound else 1)
    og = og.assign(xg=[xgt(r) for r in og[["shot_type", "db", "rebound"]].itertuples()])
    goalies = {}
    names = RO.drop_duplicates("player_id", keep="last").set_index("player_id").name.to_dict() if len(RO) else {}
    lsv = 1 - base
    for gk, d in og[og.goalie.notna()].groupby("goalie"):
        n, ga, xga = float(d.w.sum()), float((d.goal * d.w).sum()), float((d.xg * d.w).sum())
        goalies[str(int(gk))] = dict(name=names.get(int(gk)), sv=round(1 - _shrink(ga, n, 1 - lsv, 300), 4), gsax=round((xga - ga) / max(1.0, n) * 100, 3), sa=int(len(d)))

    # ---------- players ----------
    pos = RO.drop_duplicates("player_id", keep="last").set_index("player_id").pos_code.to_dict() if len(RO) else {}
    active = set(PT[PT.w == 1.0].player_id) or set(PT.player_id)   # skaters who have played this season
    recent = PT[PT.player_id.isin(active)].sort_values("game_id").groupby("player_id").tail(15)
    tois = recent.groupby("player_id")[["5v5", "pp", "pk", "all"]].mean()
    players = {}
    shooter = S[S.shooter.notna()]
    asts = defaultdict(Counter)
    for r in G.itertuples():
        for a in (r.a1, r.a2):
            if a == a and a:
                asts[int(r.scorer)][int(a)] += 1
    by_shooter = dict(tuple(shooter.groupby("shooter")))
    for pid, row in tois.iterrows():
        pid = int(pid); o = dict(pos=pos.get(pid), toi=[round(float(row["5v5"]), 2), round(float(row["pp"]), 2), round(float(row["pk"]), 2)])
        d = by_shooter.get(pid)
        if d is not None and len(d):
            on = d[d.on_goal & ~d.en_target.astype(bool)]
            split = on.strength.value_counts()
            o["split"] = [int(split.get("5v5", 0) + split.get("other", 0)), int(split.get("pp", 0)), int(split.get("pk", 0))]
            mix = on.shot_type.value_counts()
            o["mix"] = {t: round(_shrink(float(mix.get(t, 0)), float(len(on)), L["mix"][t], 25), 3) for t in TYPES}
            sm = on.sort_values("game_id").tail(28)
            o["loc"] = [[int(r.ax), int(r.ay), TYPES.index(r.shot_type) if r.shot_type in TYPES else 0] for r in sm.itertuples() if r.ax == r.ax]
        if asts.get(pid):
            o["ast"] = {str(k): v for k, v in asts[pid].most_common(6)}
        players[str(pid)] = o
    api = api or {}
    for pid, extra in api.get("skaters", {}).items():
        players.setdefault(pid, {}).update(extra)
    for tm, extra in api.get("teams", {}).items():
        teams.setdefault(tm, {}).update(extra)
    if api.get("league"):
        L.update(api["league"])
    return dict(v=1, season=int(season), games=int(ncur), built=pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds"),
                league=L, teams=teams, players=players, goalies=goalies)


def fetch_api(season: int, log=print) -> dict:
    """Hits, blocks, giveaways, takeaways, faceoffs and penalty minutes per skater from the NHL stats API (skipped if unreachable)."""
    import requests
    sid = f"{season}{season + 1}"
    out = dict(skaters={}, teams={}, league={})

    def get(report):
        r = requests.get(f"{STATS}/skater/{report}", params=dict(limit=-1, cayenneExp=f"seasonId={sid} and gameTypeId=2"), timeout=40,
                         headers={"User-Agent": "Mozilla/5.0 (nhlmodel)"})
        r.raise_for_status(); return r.json().get("data", [])
    try:
        rt, fo, pe = get("realtime"), get("faceoffwins"), get("penalties")
    except Exception as e:   # noqa: BLE001 - the sim falls back to league rates
        log(f"nhl sim: stats API unavailable ({e})"); return out
    sec = lambda r: max(1.0, float(r.get("timeOnIcePerGame") or 0) * float(r.get("gamesPlayed") or 0) / 60)
    tot = defaultdict(lambda: defaultdict(float))
    for r in rt:
        m = sec(r); pid = str(r["playerId"])
        o = out["skaters"].setdefault(pid, {})
        for k, src in (("hit60", "hits"), ("blk60", "blockedShots"), ("give60", "giveaways"), ("take60", "takeaways")):
            o[k] = round(float(r.get(src) or 0) / m * 60, 3)
            tot[r.get("teamAbbrevs", "").split(",")[-1]][src] += float(r.get(src) or 0)
        tot[r.get("teamAbbrevs", "").split(",")[-1]]["gp"] = max(tot[r.get("teamAbbrevs", "").split(",")[-1]]["gp"], float(r.get("gamesPlayed") or 0))
    for r in fo:
        o = out["skaters"].setdefault(str(r["playerId"]), {})
        o["fo"] = [int(r.get("totalFaceoffWins") or 0), int(r.get("totalFaceoffs") or 0)]
        tm = r.get("teamAbbrevs", "").split(",")[-1]
        tot[tm]["fow"] += float(r.get("totalFaceoffWins") or 0); tot[tm]["fot"] += float(r.get("totalFaceoffs") or 0)
    for r in pe:
        m = sec(r) if "timeOnIcePerGame" in r else max(1.0, float(r.get("gamesPlayed") or 1) * 15 / 60)
        o = out["skaters"].setdefault(str(r["playerId"]), {})
        o["pim60"] = round(float(r.get("penaltyMinutes") or 0) / m * 60, 3)
        o["drawn60"] = round(float(r.get("penaltiesDrawn") or 0) / m * 60, 3)
    for tm, t in tot.items():
        if t["gp"]:
            out["teams"][tm] = dict(hits_g=round(t["hits"] / t["gp"], 2), blk_g=round(t["blockedShots"] / t["gp"], 2), give_g=round(t["giveaways"] / t["gp"], 2),
                                    take_g=round(t["takeaways"] / t["gp"], 2), fo=round(t["fow"] / t["fot"], 4) if t["fot"] else .5)
    log(f"nhl sim: stats API {len(out['skaters'])} skaters")
    return out


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return None if np.isnan(o) else round(float(o), 4)
    return o


def run(state: str = "state", log=print) -> dict | None:
    inter, site = os.path.join(state, "intermediate"), os.path.join(state, "site")
    if not os.path.exists(os.path.join(inter, "shots.csv.gz")):
        log("nhl sim: no shot data yet"); return None
    gm = _read(inter, "games")
    season = int(gm.season.max())
    api = fetch_api(season, log) if os.environ.get("NHL_SIM_API", "1") == "1" else {}
    out = build(inter, season, api)
    os.makedirs(site, exist_ok=True)
    json.dump(clean(out), open(os.path.join(site, "nhl_sim.json"), "w"), separators=(",", ":"))
    log(f"nhl sim: {len(out['teams'])} teams, {len(out['players'])} skaters, {len(out['goalies'])} goalies, {out['games']} games this season")
    return out


if __name__ == "__main__":
    run()
