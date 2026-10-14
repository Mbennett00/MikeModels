"""Daily NBA run: refresh ESPN data, refit the team ratings, project the next slate, write nba.json + nba.html.

python -m nbamodel.daily [--state state]
Writes state/site/nba.json (kept with the rest of the state) and state/site/web/nba.json + nba.html.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil

import pandas as pd

from . import data, model

HERE = os.path.dirname(__file__)
ET = data.ET
FIRST_DAY = dt.date(2025, 10, 1)        # the 2025-26 season: the model's history starts here
MAX_BOX_PER_RUN = 1500


def _read(p: str) -> pd.DataFrame:
    return pd.read_csv(p, dtype={"game_id": str, "player_id": str}) if os.path.exists(p) else pd.DataFrame()


def _in_season(d: dt.date) -> bool:
    return not (d.month in (7, 8, 9) or (d.month == 6 and d.day > 25))


def refresh_games(games: pd.DataFrame, today: dt.date, log=print) -> pd.DataFrame:
    """Scoreboards from the day after the last settled day (or the start) through a week ahead."""
    if len(games):
        done = games[games.state == "post"]
        start = (pd.to_datetime(done.date).max().date() - dt.timedelta(days=2)) if len(done) else FIRST_DAY
    else:
        start = FIRST_DAY
    start = min(start, today - dt.timedelta(days=2))
    rows, d, n = [], start, 0
    while d <= today + dt.timedelta(days=8):
        if _in_season(d):
            rows += data.scoreboard(d); n += 1
        d += dt.timedelta(days=1)
    log(f"nba: {n} scoreboards fetched, {len(rows)} games seen")
    if not rows:
        return games
    new = pd.DataFrame(rows)
    out = pd.concat([games, new], ignore_index=True) if len(games) else new
    return out.drop_duplicates("game_id", keep="last").sort_values("start_utc").reset_index(drop=True)


def refresh_box(box: pd.DataFrame, games: pd.DataFrame, log=print) -> pd.DataFrame:
    have = set(box.game_id) if len(box) else set()
    cur = int(games.season.max()) if len(games) else 0
    keep = games.season_type.isin([2, 3]) | ((games.season_type == 1) & (games.season == cur))   # this season's preseason box scores too
    need = games[(games.state == "post") & keep & ~games.game_id.isin(have)].game_id.tolist()[-MAX_BOX_PER_RUN:]
    rows = []
    for gid in need:
        rows += data.box(gid)
    log(f"nba: {len(need)} box scores fetched ({len(rows)} player lines)")
    if not rows:
        return box
    new = pd.DataFrame(rows)
    return pd.concat([box, new], ignore_index=True) if len(box) else new


def next_slate(games: pd.DataFrame, today: dt.date) -> tuple[pd.DataFrame, bool]:
    """Today's games (preseason included), else the next night with games within two weeks (upcoming)."""
    cur = int(games.season.max()) if len(games) else 0
    g = games[games.season_type.isin([2, 3]) | ((games.season_type == 1) & (games.season == cur))].copy()
    g["d"] = pd.to_datetime(g.date).dt.date
    tonight = g[g.d == today]
    if len(tonight):
        return tonight, False
    ahead = g[(g.d > today) & (g.d <= today + dt.timedelta(days=14))]
    if not len(ahead):
        return ahead, True
    return ahead[ahead.d == ahead.d.min()], True


def _team_obj(r, side: str, b2b: bool) -> dict:
    return dict(abbr=r[side], name=r[f"{side}_name"], city=r[f"{side}_city"], color=r[f"{side}_color"],
                logo=str(r[f"{side}_logo"]).replace("/500/", "/500-dark/"), b2b=bool(b2b))


def build(games: pd.DataFrame, box: pd.DataFrame, roster: pd.DataFrame | None, inj: pd.DataFrame | None, today: dt.date,
          prev_meta: dict | None = None) -> dict:
    games = model.add_rest(games)
    asof = pd.Timestamp(today)
    R = model.fit_ratings(games, asof)
    sl, upcoming = next_slate(games, today)
    slate = []
    for _, r in sl.iterrows():
        pre = int(r.season_type) == 1
        pr = model.project_game(R, r.home, r.away, bool(r.neutral), bool(r.b2b_home), bool(r.b2b_away), preseason=pre)
        res = dict(home=int(r.home_score), away=int(r.away_score)) if r.state == "post" and pd.notna(r.home_score) else None
        slate.append(dict(game_id=r.game_id, start_utc=r.start_utc, state=r.state, detail=r.detail, neutral=bool(r.neutral), pre=pre,
                          home=_team_obj(r, "home", r.b2b_home), away=_team_obj(r, "away", r.b2b_away),
                          sd_margin=round(R["sd_margin"] * (model.PRE_SD if pre else 1), 2), sd_total=round(R["sd_total"] * (model.PRE_SD if pre else 1), 2), result=res, **pr))
    flat = [dict(game_id=s["game_id"], home=s["home"]["abbr"], away=s["away"]["abbr"], pts_home=s["pts_home"], pts_away=s["pts_away"]) for s in slate]
    players = model.player_projections(box, games, roster, inj, flat)
    teams = model.team_table(R)
    finished = games[(games.state == "post") & (games.season_type.isin([2, 3]) | ((games.season_type == 1) & (games.season == R["season"])))]
    # what changed since the last run: rating movers, injuries to projected regulars, the refit itself
    items = [dict(kind="data", icon="📥", text=f"Ratings refit on {R['games_fit']} games ({R['games_this_season']} this season"
                  f"{', ' + str(R['games_preseason']) + ' preseason at ' + str(int(100 * model.PRESEASON)) + '% weight' if R['games_preseason'] else ''}) through {finished.date.max()}")]
    old = (prev_meta or {}).get("ratings") or {}
    movers = sorted(((t, v["net"] - old[t]["net"]) for t, v in teams.items() if t in old), key=lambda x: -abs(x[1]))[:3]
    for t, dlt in movers:
        if abs(dlt) >= 0.5:
            items.append(dict(kind="teams", icon="📈" if dlt > 0 else "📉", text=f"{t} net rating {dlt:+.1f} to {teams[t]['net']:+.1f}"))
    if inj is not None and len(inj):
        outs = inj[inj.status.str.lower().str.startswith(("out", "doubt"))]
        on_slate = {s["home"]["abbr"] for s in slate} | {s["away"]["abbr"] for s in slate}
        for _, r in outs[outs.team.isin(on_slate)].head(12).iterrows():
            items.append(dict(kind="injury", icon="🚑", text=f"{r['name']} ({r.team}) {r.status}{': ' + r.detail if r.detail else ''}"))
    now = pd.Timestamp.now(tz=ET).isoformat()
    updates = ([dict(time=now, items=items)] + list((prev_meta or {}).get("updates") or []))[:30]
    inj_list = [] if inj is None or inj.empty else inj[["name", "team", "status", "detail"]].to_dict("records")
    return dict(
        meta=dict(sport="NBA", date=str(sl.date.iloc[0]) if len(sl) else str(today), generated_at=now, upcoming=upcoming,
                  preseason=bool(len(sl)) and bool((sl.season_type == 1).all()),
                  data_through=str(finished.date.max()) if len(finished) else None, season=R["season"],
                  model=dict(games_fit=R["games_fit"], games_this_season=R["games_this_season"], games_preseason=R["games_preseason"],
                             preseason_weight=model.PRESEASON, hca=round(R["hca"], 2),
                             league_pts=round(R["mu"], 1), sd_margin=round(R["sd_margin"], 2), sd_total=round(R["sd_total"], 2),
                             b2b_own=round(R["b2b_own"], 2), b2b_opp=round(R["b2b_opp"], 2), half_life=model.HALF_LIFE, carry=model.CARRY)),
        games=slate, players=players, teams=teams, injuries=inj_list, updates=updates, ratings=teams)


def run(state: str = "state", log=print):
    site = os.path.join(state, "site")
    os.makedirs(site, exist_ok=True)
    today = pd.Timestamp.now(tz=ET).date()
    gp, bp = os.path.join(site, "nba_games.csv.gz"), os.path.join(site, "nba_box.csv.gz")
    games = refresh_games(_read(gp), today, log)
    if games.empty:
        log("nba: no games from ESPN; leaving the page as it was"); return
    games.to_csv(gp, index=False, compression="gzip")
    box = refresh_box(_read(bp), games, log)
    if len(box):
        box.to_csv(bp, index=False, compression="gzip")
    tids = {}
    for side in ("home", "away"):
        for a, t in zip(games[side], games[f"{side}_tid"]):
            if pd.notna(t):
                tids[a] = str(int(float(t))) if str(t).replace(".", "").isdigit() else str(t)
    try:
        roster = data.rosters(tids)
    except Exception as e:
        log(f"nba: rosters failed ({e})"); roster = None
    try:
        inj = data.injuries()
    except Exception as e:
        log(f"nba: injuries failed ({e})"); inj = None
    prev = {}
    jp = os.path.join(site, "nba.json")
    if os.path.exists(jp):
        try:
            prev = json.load(open(jp))
        except ValueError:
            prev = {}
    out = build(games, box, roster, inj, today, prev_meta=dict(ratings=prev.get("ratings"), updates=prev.get("updates")))
    out["meta"]["repo"] = os.environ.get("GITHUB_REPOSITORY", "Mbennett00/MikeModels")
    write(site, out)
    log(f"nba: {len(out['games'])} games ({'upcoming' if out['meta']['upcoming'] else 'tonight'}), {len(out['players'])} player projections")


def write(site: str, out: dict):
    web = os.path.join(site, "web")
    os.makedirs(web, exist_ok=True)
    txt = json.dumps(out, separators=(",", ":"), default=str)
    for d in (site, web):
        with open(os.path.join(d, "nba.json"), "w") as f:
            f.write(txt)
    install_page(web)


def install_page(web: str):
    """Copy the NBA page next to the others (the NHL build calls this too, so no page drops another)."""
    from calib.webassets import install as _install
    _install(os.path.join(HERE, "web_template.html"), os.path.join(web, "nba.html"))
    src = os.path.join(os.path.dirname(web), "nba.json")
    if os.path.exists(src) and os.path.abspath(src) != os.path.abspath(os.path.join(web, "nba.json")):
        shutil.copy(src, os.path.join(web, "nba.json"))


if __name__ == "__main__":
    p = argparse.ArgumentParser(prog="nbamodel.daily")
    p.add_argument("--state", default="state")
    run(p.parse_args().state)
