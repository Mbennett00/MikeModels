"""Build every canonical table from the NHL API alone (for the automated daily job).

Per game it needs two public endpoints:
  api-web.nhle.com/v1/gamecenter/{id}/play-by-play   events, rosterSpots, situationCode, goalieInNetId
  api.nhle.com/stats/rest/en/shiftcharts?cayenneExp=gameId={id}   shifts -> TOI by strength, starting goalie

``parse_game`` turns one game into small intermediate tables (stored incrementally);
``build_tables`` turns the accumulated intermediates into the canonical tables.
"""
from __future__ import annotations

import gzip
import json
import os
import time

import numpy as np
import pandas as pd

from .moneypuck import infer_lines
from .xg import score_by_season, score_venue_coefs

WEB = "https://api-web.nhle.com/v1"
STATS = "https://api.nhle.com/stats/rest/en"
SHOT_EVENTS = {"shot-on-goal", "missed-shot", "blocked-shot", "goal"}
PEN_COUNTED = {"MIN", "MAJ", "BEN"}          # minors, majors, bench minors (not misconducts)

INTERMEDIATE = ["games", "shots", "goals", "penalties", "player_toi", "team_toi", "goalie_toi", "roster"]


def _secs(t: str) -> int:
    m, s = str(t or "0:0").split(":")
    return int(m) * 60 + int(s)


def _strength(sc: str, shooter_home: bool) -> tuple[str, bool]:
    """(strength from the acting team's view, target net empty)."""
    sc = str(sc or "1551").zfill(4)
    ag, ask, hsk, hg = int(sc[0]), int(sc[1]), int(sc[2]), int(sc[3])
    own_sk, opp_sk, own_g, opp_g = (hsk, ask, hg, ag) if shooter_home else (ask, hsk, ag, hg)
    en = opp_g == 0
    if en:
        return "en", True
    if own_g == 1 and opp_g == 1:
        if own_sk == 5 and opp_sk == 5:
            return "5v5", False
        if own_sk > opp_sk:
            return "pp", False
        if own_sk < opp_sk:
            return "pk", False
    return "other", False


def parse_game(pbp: dict, shifts: list[dict]) -> dict[str, pd.DataFrame]:
    from .nhl_api import parse_pbp
    grow, _ = parse_pbp(pbp)
    gid = grow["game_id"]
    hid, aid = pbp["homeTeam"]["id"], pbp["awayTeam"]["id"]
    ab = {hid: grow["home"], aid: grow["away"]}
    roster = pd.DataFrame([dict(game_id=gid, player_id=r["playerId"], team=ab.get(r["teamId"]),
                                name=f'{r.get("firstName", {}).get("default", "")} {r.get("lastName", {}).get("default", "")}'.strip(),
                                pos_code=r.get("positionCode", "")) for r in pbp.get("rosterSpots", [])])
    team_of = dict(zip(roster.player_id, roster.team)) if len(roster) else {}

    # ---- events
    shots, goals, pens = [], [], []
    hs = as_ = 0
    last_unblocked = {}   # team -> game second of last shot attempt
    for p in pbp.get("plays", []):
        pdsc = p.get("periodDescriptor", {})
        ptype, per = pdsc.get("periodType", "REG"), int(pdsc.get("number", 1))
        if ptype == "SO":
            continue
        t = (per - 1) * 1200 + _secs(p.get("timeInPeriod"))
        k = p.get("typeDescKey")
        d = p.get("details", {}) or {}
        if k in SHOT_EVENTS:
            shooter = d.get("scoringPlayerId") if k == "goal" else d.get("shootingPlayerId")
            team = team_of.get(shooter) or ab.get(d.get("eventOwnerTeamId"))
            if k == "blocked-shot" and shooter not in team_of:
                team = None   # owner of a blocked shot can be the blocking team; skip if unknown
            if team is None:
                continue
            is_home = team == grow["home"]
            strength, en = _strength(p.get("situationCode"), is_home)
            lead = (hs - as_) if is_home else (as_ - hs)
            reb = (t - last_unblocked.get(team, -99)) <= 3
            shots.append(dict(game_id=gid, season=grow["season"], team=team, is_home=int(is_home), shooter=shooter,
                              t=t, period=per, period_type=ptype, x=d.get("xCoord"), y=d.get("yCoord"),
                              shot_type=d.get("shotType"), strength=strength, en_target=en,
                              goal=k == "goal", on_goal=k in ("goal", "shot-on-goal"), unblocked=k != "blocked-shot",
                              rebound=reb, lead=int(np.clip(lead, -3, 3)), goalie=d.get("goalieInNetId")))
            last_unblocked[team] = t
            if k == "goal":
                goals.append(dict(game_id=gid, team=team, scorer=shooter, a1=d.get("assist1PlayerId"),
                                  a2=d.get("assist2PlayerId"), strength=strength, en_target=en,
                                  period_type=ptype))
                if is_home:
                    hs += 1
                else:
                    as_ += 1
        elif k == "penalty" and d.get("typeCode") in PEN_COUNTED:
            who = d.get("committedByPlayerId")
            team = team_of.get(who) or ab.get(d.get("eventOwnerTeamId"))
            if team:
                pens.append(dict(game_id=gid, team=team, t=t))

    # ---- shifts -> TOI by strength
    ptoi, ttoi, gtoi = _toi_from_shifts(gid, shifts, roster, grow)
    return dict(games=pd.DataFrame([grow]), shots=pd.DataFrame(shots), goals=pd.DataFrame(goals),
                penalties=pd.DataFrame(pens), player_toi=ptoi, team_toi=ttoi, goalie_toi=gtoi, roster=roster)


def _toi_from_shifts(gid, shifts, roster, grow):
    sh = [s for s in shifts if s.get("typeCode") == 517 and s.get("startTime") and s.get("endTime")]
    if not sh or roster.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    df = pd.DataFrame(dict(player_id=[s["playerId"] for s in sh], team=[s.get("teamAbbrev") for s in sh],
                           period=[int(s["period"]) for s in sh],
                           start=[(int(s["period"]) - 1) * 1200 + _secs(s["startTime"]) for s in sh],
                           end=[(int(s["period"]) - 1) * 1200 + _secs(s["endTime"]) for s in sh]))
    df = df[(df.end > df.start) & (df.period <= 4)]
    pos = dict(zip(roster.player_id, roster.pos_code))
    df["is_g"] = df.player_id.map(pos).eq("G")
    T = int(df.end.max()) + 1
    arr = {}
    for team in (grow["home"], grow["away"]):
        for g in (False, True):
            d = np.zeros(T + 1)
            s = df[(df.team == team) & (df.is_g == g)]
            np.add.at(d, s.start.to_numpy(), 1); np.add.at(d, s.end.to_numpy(), -1)
            arr[(team, g)] = np.cumsum(d)[:T]
    states = {}
    for team, opp in ((grow["home"], grow["away"]), (grow["away"], grow["home"])):
        own, oth = arr[(team, False)], arr[(opp, False)]
        both_g = (arr[(team, True)] >= 1) & (arr[(opp, True)] >= 1)
        st = {"5v5": both_g & (own == 5) & (oth == 5), "pp": both_g & (own > oth) & (oth >= 3),
              "pk": both_g & (own < oth) & (own >= 3)}
        states[team] = {k: np.r_[0, np.cumsum(v)] for k, v in st.items()}
    rows = []
    for r in df.itertuples():
        cs = states.get(r.team)
        if cs is None:
            continue
        rows.append(dict(game_id=gid, player_id=r.player_id, team=r.team, is_g=r.is_g, all=r.end - r.start,
                         **{k: cs[k][r.end] - cs[k][r.start] for k in ("5v5", "pp", "pk")},
                         first=r.start == 0))
    t = pd.DataFrame(rows)
    ptoi = t[~t.is_g].groupby(["game_id", "player_id", "team"])[["all", "5v5", "pp", "pk"]].sum().div(60).reset_index()
    g = t[t.is_g].groupby(["game_id", "player_id", "team"]).agg(toi=("all", "sum"), starter=("first", "max")).reset_index()
    g["toi"] /= 60
    ttoi = pd.DataFrame([dict(game_id=gid, team=team, toi_all=T / 60,
                              **{f"toi_{k}": states[team][k][-1] / 60 for k in ("5v5", "pp", "pk")})
                         for team in states])
    return ptoi, ttoi, g


# ---------------------------------------------------------------------------------------------
def build_tables(inter: dict[str, pd.DataFrame]) -> tuple[dict, list[str]]:
    games = inter["games"].copy()
    games["date"] = pd.to_datetime(games.date)
    shots = inter["shots"].merge(games[["game_id", "date"]], on="game_id")
    shots["xg"], notes = score_by_season(shots)
    coefs = score_venue_coefs(shots)   # league-wide; small leakage accepted, see README
    shots = shots.merge(coefs, on=["lead", "is_home"], how="left").fillna({"coef": 1.0})
    shots["xg_adj"] = shots.xg * np.where(shots.strength == "5v5", shots.coef, 1.0)
    opp = {}
    for g in games.itertuples():
        opp[(g.game_id, g.home)] = g.away; opp[(g.game_id, g.away)] = g.home
    shots["opp"] = [opp.get((a, b)) for a, b in zip(shots.game_id, shots.team)]
    reg = shots.period_type != "SO"

    # ---- team games
    tt = inter["team_toi"].copy()
    tt["opp"] = [opp.get((a, b)) for a, b in zip(tt.game_id, tt.team)]
    def agg(mask, val, by="team"):
        return shots[mask].groupby(["game_id", by])[val].sum()
    s5 = (shots.strength == "5v5")
    parts = {
        "xgf_5v5": agg(s5 & shots.unblocked, "xg"), "xgf_5v5_adj": agg(s5 & shots.unblocked, "xg_adj"),
        "xga_5v5": agg(s5 & shots.unblocked, "xg", "opp"), "xga_5v5_adj": agg(s5 & shots.unblocked, "xg_adj", "opp"),
        "cf_5v5": shots[s5].groupby(["game_id", "team"]).size(), "ca_5v5": shots[s5].groupby(["game_id", "opp"]).size(),
        "xgf_pp": agg((shots.strength == "pp") & shots.unblocked, "xg"),
        "xga_pk": agg((shots.strength == "pp") & shots.unblocked, "xg", "opp"),
        "sog_for": shots[shots.on_goal & reg].groupby(["game_id", "team"]).size(),
        "sog_against": shots[shots.on_goal & reg].groupby(["game_id", "opp"]).size(),
    }
    tg = tt.set_index(["game_id", "team"])
    for k, v in parts.items():
        v.index = v.index.set_names(["game_id", "team"])
        tg[k] = v.reindex(tg.index).fillna(0).to_numpy()
    pen = inter["penalties"]
    taken = pen.groupby(["game_id", "team"]).size() if len(pen) else pd.Series(dtype=float)
    tg["pen_taken"] = taken.reindex(tg.index).fillna(0).to_numpy()
    tg = tg.reset_index()
    tg["pen_drawn"] = [taken.get((g, o), 0) for g, o in zip(tg.game_id, tg.opp)]
    gm = games.set_index("game_id")
    tg["is_home"] = [int(gm.at[g, "home"] == t) for g, t in zip(tg.game_id, tg.team)]
    tg["goals_nonen"] = [gm.at[g, "home_reg_nonen"] if h else gm.at[g, "away_reg_nonen"]
                         for g, h in zip(tg.game_id, tg.is_home)]
    tg = tg.merge(games[["game_id", "date", "season"]], on="game_id")

    # ---- goalie games
    gt = inter["goalie_toi"].merge(games[["game_id", "date", "season"]], on="game_id")
    fac = shots[shots.unblocked & ~shots.en_target & shots.goalie.notna()]
    gx = fac.groupby(["game_id", "goalie"]).agg(xga=("xg", "sum"), ga=("goal", "sum"))
    gx.index = gx.index.set_names(["game_id", "player_id"])
    gt = gt.merge(gx.reset_index(), on=["game_id", "player_id"], how="left").fillna({"xga": 0, "ga": 0})
    names = inter["roster"].drop_duplicates(["game_id", "player_id"]).set_index(["game_id", "player_id"]).name
    gt["name"] = [names.get((a, b), "") for a, b in zip(gt.game_id, gt.player_id)]
    goalie_games = gt.rename(columns={"player_id": "goalie_id"})[
        ["game_id", "date", "season", "goalie_id", "name", "team", "toi", "xga", "ga"]]

    # ---- player games
    pt = inter["player_toi"].rename(columns={"5v5": "toi_5v5", "pp": "toi_pp"})
    ro = inter["roster"].drop_duplicates(["game_id", "player_id"])
    pg = pt.merge(ro[["game_id", "player_id", "name", "pos_code"]], on=["game_id", "player_id"], how="left")
    pg["pos"] = np.where(pg.pos_code == "D", "D", "F")
    key = ["game_id", "shooter"]
    def pagg(mask, val=None):
        s = shots[mask]
        r = s.groupby(key)[val].sum() if val else s.groupby(key).size()
        r.index = r.index.set_names(["game_id", "player_id"])
        return r
    unb = shots.unblocked
    cols = {
        "ixg_5v5": pagg(s5 & unb, "xg"), "ixg_pp": pagg((shots.strength == "pp") & unb, "xg"),
        "g_5v5": pagg(s5 & shots.goal), "g_pp": pagg((shots.strength == "pp") & shots.goal),
        "sog_5v5": pagg(s5 & shots.on_goal), "sog_pp": pagg((shots.strength == "pp") & shots.on_goal),
        "ixg_nonen": pagg(unb & ~shots.en_target, "xg"), "g_nonen": pagg(shots.goal & ~shots.en_target),
        "goals": pagg(shots.goal & reg), "sog": pagg(shots.on_goal & reg), "en_goals": pagg(shots.goal & shots.en_target),
    }
    gl = inter["goals"]
    gl = gl[gl.period_type != "SO"]
    for a in ("a1", "a2"):
        for st, name in (("5v5", "5v5"), ("pp", "pp")):
            r = gl[gl.strength == st].groupby(["game_id", a]).size()
            r.index = r.index.set_names(["game_id", "player_id"]); cols[f"{a}_{name}"] = r
    ast = pd.concat([gl.groupby(["game_id", "a1"]).size().rename_axis(["game_id", "player_id"]),
                     gl.groupby(["game_id", "a2"]).size().rename_axis(["game_id", "player_id"])]).groupby(level=[0, 1]).sum()
    cols["assists"] = ast
    pg = pg.set_index(["game_id", "player_id"])
    for k, v in cols.items():
        pg[k] = v.reindex(pg.index).fillna(0).to_numpy()
    pg = pg.reset_index()
    pg["points"] = pg.goals + pg.assists
    pg["opp"] = [opp.get((a, b)) for a, b in zip(pg.game_id, pg.team)]
    pg["is_home"] = [int(gm.at[g, "home"] == t) for g, t in zip(pg.game_id, pg.team)]
    pg = pg.merge(games[["game_id", "date", "season"]], on="game_id")
    pg = infer_lines(pg)

    starters = goalie_games.merge(inter["goalie_toi"][["game_id", "player_id", "starter"]].rename(
        columns={"player_id": "goalie_id"}), on=["game_id", "goalie_id"])
    starters = starters[starters.starter]
    lu = pd.concat([pg[["date", "game_id", "team", "player_id", "name", "pos", "line", "pp_unit"]],
                    starters.assign(pos="G", line="G1", pp_unit=0).rename(columns={"goalie_id": "player_id"})[
                        ["date", "game_id", "team", "player_id", "name", "pos", "line", "pp_unit"]]],
                   ignore_index=True).assign(confirmed=True)
    games = games[games.game_id.isin(tg.game_id)]
    return dict(games=games, team_games=tg, goalie_games=goalie_games, player_games=pg, lineups=lu), notes


# ---------------------------------------------------------------------------------------------
class Fetcher:
    def __init__(self, sleep: float = 0.2, retries: int = 4):
        import requests
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "nhlmodel/2.0 (research)"
        self.sleep, self.retries = sleep, retries

    def get(self, url: str) -> dict:
        err = None
        for i in range(self.retries):
            try:
                r = self.s.get(url, timeout=30)
                if r.status_code == 404:
                    return {}
                r.raise_for_status()
                time.sleep(self.sleep)
                return r.json()
            except Exception as e:  # network hiccup: back off and retry
                err = e
                time.sleep(2 ** (i + 1))
        raise RuntimeError(f"GET {url} failed: {err}")

    def schedule(self, date) -> list[dict]:
        js = self.get(f"{WEB}/schedule/{pd.Timestamp(date).date()}")
        out = []
        for wk in js.get("gameWeek", []):
            for g in wk.get("games", []):
                out.append(dict(game_id=g["id"], date=pd.Timestamp(wk["date"]), game_type=g.get("gameType"),
                                state=g.get("gameState"), home=g["homeTeam"]["abbrev"], away=g["awayTeam"]["abbrev"],
                                start_utc=g.get("startTimeUTC")))
        return out

    def game(self, gid: int) -> tuple[dict, list]:
        pbp = self.get(f"{WEB}/gamecenter/{gid}/play-by-play")
        sh = self.get(f"{STATS}/shiftcharts?cayenneExp=gameId={gid}").get("data", [])
        return pbp, sh


def load_intermediate(path: str) -> dict[str, pd.DataFrame]:
    out = {}
    for k in INTERMEDIATE:
        f = os.path.join(path, f"{k}.csv.gz")
        out[k] = pd.read_csv(f) if os.path.exists(f) else pd.DataFrame()
    return out


def save_intermediate(inter: dict, path: str) -> None:
    os.makedirs(path, exist_ok=True)
    for k, v in inter.items():
        v.to_csv(os.path.join(path, f"{k}.csv.gz"), index=False, compression="gzip")


def update(path: str, start, end, fetcher: Fetcher | None = None, log=print, max_games: int | None = None,
           max_minutes: float | None = None) -> dict:
    """Fetch every completed regular-season game in [start, end] not already stored.

    ``max_minutes`` stops early (progress is saved) so a CI job can finish and resume next run.
    """
    t_end = time.time() + 60 * max_minutes if max_minutes else None
    f = fetcher or Fetcher()
    inter = load_intermediate(path)
    have = set(inter["games"].game_id) if len(inter["games"]) else set()
    todo, d = [], pd.Timestamp(start)
    while d <= pd.Timestamp(end):
        for g in f.schedule(d):
            if (g["game_type"] == 2 and g["state"] in ("OFF", "FINAL") and g["game_id"] not in have
                    and pd.Timestamp(start) <= g["date"] <= pd.Timestamp(end)):
                todo.append(g["game_id"]); have.add(g["game_id"])
        d += pd.Timedelta(days=7)
    if max_games:
        todo = todo[:max_games]
    log(f"{len(todo)} new games to fetch")
    new = {k: [] for k in INTERMEDIATE}
    for i, gid in enumerate(todo):
        if t_end and time.time() > t_end:
            log(f"time limit reached after {i} games; the rest will be fetched next run")
            break
        pbp, sh = f.game(gid)
        if not pbp:
            continue
        parts = parse_game(pbp, sh)
        if parts["player_toi"].empty:
            log(f"  {gid}: no shift data, skipped")
            continue
        for k, v in parts.items():
            new[k].append(v)
        if i % 100 == 0:
            log(f"  {i}/{len(todo)} fetched")
            # checkpoint so a timeout does not lose progress
            if i:
                _merge(inter, new); new = {k: [] for k in INTERMEDIATE}; save_intermediate(inter, path)
    _merge(inter, new)
    save_intermediate(inter, path)
    return inter


def _merge(inter, new):
    for k in INTERMEDIATE:
        if new[k]:
            inter[k] = pd.concat([inter[k]] + new[k], ignore_index=True)
