"""Automated daily job (run by .github/workflows/daily.yml).

  python -m nhlmodel.daily update    fetch newly completed games (NHL API), rebuild tables
  python -m nhlmodel.daily slate     price today's games with projected/overridden lineups + 'bet' odds
  python -m nhlmodel.daily close     snapshot closing odds for games starting within the next 75 min
  python -m nhlmodel.daily grade     settle logged plays: result, closing no-vig, CLV, profit
  python -m nhlmodel.daily backtest  walk-forward over recent dates -> validation report + dispersion inputs
  python -m nhlmodel.daily tune      grid search (slow; manual)

State lives in --state (default ./state): intermediate/ (raw parsed games) and site/ (what the
dashboard reads). The workflow syncs both with a GitHub release so runs are incremental.
"""
from __future__ import annotations

import argparse
import json
import os
import pickle

import numpy as np
import pandas as pd

from .config import DEFAULT
from .data import nhl_pipeline as nhl
from .data.teams import norm_name

ET = "America/New_York"
FIRST_SEASON_START = "2024-10-01"


def today_et() -> pd.Timestamp:
    return pd.Timestamp.now(tz=ET).tz_localize(None).normalize()


def _site(state):
    p = os.path.join(state, "site"); os.makedirs(p, exist_ok=True); return p


def _read(path, **kw):
    return pd.read_csv(path, **kw) if os.path.exists(path) else pd.DataFrame()


def load_tables(state) -> dict:
    inter = nhl.load_intermediate(os.path.join(state, "intermediate"))
    if inter["games"].empty:
        raise SystemExit("no games stored yet: run `update` first")
    tables, notes = nhl.build_tables(inter)
    odds = _read(os.path.join(_site(state), "odds_history.csv.gz"))
    if len(odds):
        odds["date"] = pd.to_datetime(odds.date.astype(str), format="mixed").dt.normalize()
        tables["odds"] = odds
    for k in ("games", "team_games", "goalie_games", "player_games", "lineups"):
        tables[k]["date"] = pd.to_datetime(tables[k].date).dt.normalize()
    tables["_notes"] = notes
    return tables


def config(state):
    f = os.path.join(_site(state), "tuned_config.json")
    if os.path.exists(f):
        from .tuning import load_config
        return load_config(f), "tuned_config.json"
    return DEFAULT, "defaults (not yet tuned)"


def cmd_update(a):
    end = today_et() - pd.Timedelta(days=1)
    path = os.path.join(a.state, "intermediate")
    start = pd.Timestamp(a.start)
    games = nhl.load_intermediate(path)["games"]
    if len(games) and not a.full:
        # only look a few days back from the newest stored game (late-finishing games, corrections)
        start = max(start, pd.to_datetime(games.date).max() - pd.Timedelta(days=3))
    inter = nhl.update(path, start, end, max_games=a.max_games, max_minutes=a.max_minutes)
    g = inter["games"]
    write_status(a.state, games_stored=int(len(g)),
                 data_through=str(pd.to_datetime(g.date).max().date()) if len(g) else None,
                 seasons=sorted(int(x) for x in g.season.unique()) if len(g) else [])


def fetch_rosters(teams) -> pd.DataFrame:
    f = nhl.Fetcher()
    rows = []
    for t in sorted(set(teams)):
        try:
            rows += f.roster(t)
        except RuntimeError as e:
            print(f"roster {t}: {e}")
    return pd.DataFrame(rows)


def _pick_starter(goalie_ids, starts: pd.DataFrame, date):
    """Most starts in each goalie's recent games (any team), recency weighted; other goalie on a B2B."""
    if not len(goalie_ids):
        return None
    s = starts[starts.player_id.isin(goalie_ids)].sort_values("date")
    if s.empty:
        return goalie_ids[0]
    age = (date - s.date).dt.days.clip(lower=0)
    w = (0.5 ** (age / 60.0)).groupby(s.player_id).sum().sort_values(ascending=False)
    pick = w.index[0]
    last = s[s.date == s.date.max()]
    if len(w) > 1 and (date - s.date.max()).days == 1 and pick in set(last.player_id):
        pick = w.index[1]
    return pick


def _roster_lineup(team, roster_t: pd.DataFrame, pg: pd.DataFrame, date, game_id) -> pd.DataFrame:
    """Build lines from a current roster: rank by each player's recent 5v5 / PP ice time on any team."""
    hist = pg[pg.player_id.isin(roster_t.player_id) & (pg.date < date)].sort_values("date")
    recent = hist.groupby("player_id").tail(15).groupby("player_id").agg(toi5=("toi_5v5", "mean"), toipp=("toi_pp", "mean"))
    r = roster_t[roster_t.pos != "G"].set_index("player_id").join(recent).fillna({"toi5": 0.0, "toipp": 0.0})
    rows = []
    for pos, n, size, prefix in (("F", 12, 3, "F"), ("D", 6, 2, "D")):
        grp = r[r.pos == pos].sort_values("toi5", ascending=False).head(n)
        for i, (pid, x) in enumerate(grp.iterrows()):
            rows.append(dict(player_id=pid, name=x["name"], pos=pos, line=f"{prefix}{i // size + 1}", toipp=x.toipp,
                             headshot=x.get("headshot", "")))
    lu = pd.DataFrame(rows)
    if lu.empty:
        return lu
    pp = lu.sort_values("toipp", ascending=False)
    lu["pp_unit"] = 0
    lu.loc[pp.index[:5], "pp_unit"] = 1
    lu.loc[pp.index[5:10], "pp_unit"] = 2
    lu.loc[lu.toipp < 0.3, "pp_unit"] = 0
    return lu.drop(columns="toipp").assign(date=date, game_id=game_id, team=team, confirmed=False)


def projected_lineups(tables: dict, schedule: pd.DataFrame, overrides: pd.DataFrame | None, date,
                      rosters: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Projected lineup per team, kept current with today's NHL rosters.

    * Team has played this season: its last game's lineup, minus players no longer on the roster
      (replacements from the roster by recent ice time).
    * Team has not played yet this season: lines built from the current roster, ranked by each
      player's recent ice time on any team (so offseason moves are reflected).
    * Starter: the roster goalie with the most recent starts (any team); the other one on a B2B.
    Without ``rosters`` (offline/tests) it falls back to the last game's lineup and goalies.
    """
    from .slate import season_of
    lu, gg, pg = tables["lineups"], tables["goalie_games"], tables["player_games"]
    season = season_of(date)
    starts = lu[(lu.pos == "G") & (lu.date < date)]
    rows, roster, notes = [], [], []
    for g in schedule.itertuples():
        for team in (g.home, g.away):
            tl = lu[(lu.team == team) & (lu.date < date)]
            rt = rosters[rosters.team == team] if rosters is not None and len(rosters) else None
            if rt is not None and len(rt):
                roster += rt.to_dict("records")
                this_season = tl[pd.to_datetime(tl.date) >= pd.Timestamp(f"{season}-08-01")]
                if len(this_season):
                    last = this_season[this_season.date == this_season.date.max()]
                    sk = last[(last.pos != "G") & last.player_id.isin(rt.player_id)].copy()
                    missing_f = 12 - (sk.pos == "F").sum()
                    missing_d = 6 - (sk.pos == "D").sum()
                    if missing_f > 0 or missing_d > 0:
                        fill = _roster_lineup(team, rt[~rt.player_id.isin(sk.player_id)], pg, date, g.game_id)
                        if len(fill):
                            extra = pd.concat([fill[fill.pos == "F"].head(max(missing_f, 0)),
                                               fill[fill.pos == "D"].head(max(missing_d, 0))])
                            sk = pd.concat([sk, extra.assign(line=np.where(extra.pos == "F", "F4", "D3"), pp_unit=0)])
                    sk = sk.merge(rt[["player_id", "headshot"]], on="player_id", how="left", suffixes=("_x", ""))
                    sk = sk.drop(columns=[c for c in sk if c.endswith("_x")])
                    sk = sk.assign(date=date, game_id=g.game_id, confirmed=False)
                else:
                    sk = _roster_lineup(team, rt, pg, date, g.game_id)
                    notes.append(f"{team}: no game yet this season, lines built from the current roster")
                rows.append(sk)
                gids = list(rt[rt.pos == "G"].player_id)
                pick = _pick_starter(gids, starts, date)
                if pick is not None:
                    gr = rt[rt.player_id == pick].iloc[0]
                    rows.append(pd.DataFrame([dict(date=date, game_id=g.game_id, team=team, player_id=pick,
                                                   name=gr["name"], pos="G", line="G1", pp_unit=0, confirmed=False,
                                                   headshot=gr.get("headshot", ""))]))
                continue
            # ---- offline fallback: last game in the data
            if tl.empty:
                continue
            last = tl[tl.date == tl.date.max()]
            rows.append(last[last.pos != "G"].assign(date=date, game_id=g.game_id, confirmed=False))
            tg_starts = tl[tl.pos == "G"]
            pick = _pick_starter(list(tg_starts.player_id.unique()), tg_starts, date)
            goalies = gg[(gg.team == team) & (gg.date < date)].sort_values("date").drop_duplicates("goalie_id", keep="last").tail(4)
            for r in goalies.itertuples():
                roster.append(dict(team=team, player_id=r.goalie_id, name=r.name, pos="G"))
            if pick is not None:
                nm = goalies.set_index("goalie_id").name.get(pick, "")
                rows.append(pd.DataFrame([dict(date=date, game_id=g.game_id, team=team, player_id=pick, name=nm,
                                               pos="G", line="G1", pp_unit=0, confirmed=False)]))
            recent = tl[(tl.pos != "G") & (tl.date >= tl.date.max() - pd.Timedelta(days=30))].drop_duplicates("player_id")
            for r in recent.itertuples():
                roster.append(dict(team=team, player_id=r.player_id, name=r.name, pos=r.pos))
    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    roster = pd.DataFrame(roster).drop_duplicates(["team", "player_id"]) if roster else pd.DataFrame(
        columns=["team", "player_id", "name", "pos"])
    if overrides is not None and len(overrides) and len(out):
        out = apply_overrides(out, overrides, roster)
    out.attrs["notes"] = notes
    return out, roster


def apply_overrides(lu: pd.DataFrame, ov: pd.DataFrame, roster: pd.DataFrame) -> pd.DataFrame:
    """overrides columns: team, goalie (name, optional), lineup_confirmed (bool, optional)."""
    lu = lu.copy()
    for r in ov.itertuples():
        team = r.team
        gname = getattr(r, "goalie", None)
        if isinstance(gname, str) and gname.strip():
            cand = roster[(roster.team == team) & (roster.pos == "G")]
            hit = cand[cand.name.map(norm_name) == norm_name(gname)]
            if len(hit):
                gi = lu.index[(lu.team == team) & (lu.pos == "G")]
                lu.loc[gi, ["player_id", "name"]] = [hit.player_id.iloc[0], hit.name.iloc[0]]
                lu.loc[gi, "confirmed"] = True
        if str(getattr(r, "lineup_confirmed", "")).lower() in ("true", "1", "yes"):
            lu.loc[(lu.team == team) & (lu.pos != "G"), "confirmed"] = True
    return lu


def _schedule(date):
    f = nhl.Fetcher()
    s = pd.DataFrame([g for g in f.schedule(date) if g["game_type"] == 2 and g["date"] == date])
    return s


def next_game_day(start, days: int = 45):
    """First date >= start with regular-season games (the schedule endpoint returns a week per call)."""
    f = nhl.Fetcher()
    d = pd.Timestamp(start)
    while d <= pd.Timestamp(start) + pd.Timedelta(days=days):
        games = [g for g in f.schedule(d) if g["game_type"] == 2 and g["date"] >= pd.Timestamp(start)]
        if games:
            return min(g["date"] for g in games)
        d += pd.Timedelta(days=7)
    return None


def write_status(state, **kw):
    site = _site(state)
    f = os.path.join(site, "status.json")
    st = json.load(open(f)) if os.path.exists(f) else {}
    st.update(kw, updated_at=pd.Timestamp.now(tz=ET).isoformat())
    json.dump(st, open(f, "w"), indent=2, default=str)


def cmd_slate(a):
    from .data import odds_api
    from .report import slate_markdown, write
    from .slate import build_state, price_state
    site = _site(a.state)
    date = pd.Timestamp(a.date) if a.date else today_et()
    sched = _schedule(date)
    upcoming = False
    if sched.empty and not a.date:
        nxt = next_game_day(date)
        if nxt is not None:
            date, sched, upcoming = nxt, _schedule(nxt), True
    meta = dict(generated_at=pd.Timestamp.now(tz=ET).isoformat(), date=str(date.date()), games=len(sched),
                upcoming=upcoming)
    if sched.empty:
        meta["warnings"] = ["no NHL regular-season games in the next 45 days"]
        json.dump(meta, open(os.path.join(site, "meta.json"), "w"), indent=2)
        print("no games"); return
    tables = load_tables(a.state)
    cfg, cfg_src = config(a.state)
    ovf = os.path.join(a.overrides, f"{date.date()}.csv")
    ov = pd.read_csv(ovf) if os.path.exists(ovf) else None
    rosters = fetch_rosters(list(sched.home) + list(sched.away))
    lineups, roster = projected_lineups(tables, sched, ov, date, rosters)
    odds = odds_api.fetch(sched, roster if len(roster) else lineups, "bet", props=not a.no_props)
    hist = _read(os.path.join(site, "odds_history.csv.gz"))
    if len(odds):
        hist = _append_odds(hist, odds)
        hist.to_csv(os.path.join(site, "odds_history.csv.gz"), index=False, compression="gzip")
        # latest bet-time price per book for today's pricing
        odds = odds.sort_values("fetched_at").drop_duplicates(
            ["game_id", "market", "player_id", "selection", "line", "book"], keep="last")
    hp = {}
    for k in ("games", "players"):
        f = os.path.join(site, f"bt_{k}.csv.gz")
        if os.path.exists(f):
            hp[k] = pd.read_csv(f, parse_dates=["date"])
    state = build_state({k: v for k, v in tables.items() if not k.startswith("_")}, sched, lineups,
                        odds if len(odds) else None, cfg, hp or None, date)
    state.warnings = (list(tables["_notes"]) + state.warnings + [f"constants: {cfg_src}"]
                      + lineups.attrs.get("notes", []) + ["lineups and goalies use today's NHL rosters"])
    if ov is None:
        state.warnings.append("lineups and starting goalies are projected (not confirmed), so nothing is flagged yet; "
                              "confirm them in the Lineups tab or with an overrides file")
    plays, cons, warnings = price_state(state)
    try:
        from .images import resolve
        people = lineups[["player_id", "name"]].assign(
            headshot=lineups["headshot"] if "headshot" in lineups else "").fillna("").to_dict("records")
        imgs = resolve(list(sched.home) + list(sched.away), people)
        json.dump(imgs, open(os.path.join(site, "images.json"), "w"))
        if len(plays):
            hs = imgs["headshots"]
            plays["headshot"] = [hs.get(str(int(p)), h) if pd.notna(p) else h
                                 for p, h in zip(plays.player_id, plays.get("headshot", pd.Series([""] * len(plays))))]
    except Exception as e:   # images are cosmetic: never fail the slate over them
        print(f"image lookup failed: {e}")
    plays.to_csv(os.path.join(site, "plays.csv"), index=False)
    cons.to_csv(os.path.join(site, "consistency.csv"), index=False)
    write(os.path.join(site, "slate.md"), slate_markdown(plays, cons, warnings, date))
    with open(os.path.join(site, "slate_state.pkl"), "wb") as fh:
        pickle.dump(dict(state=state, roster=roster), fh)
    if not upcoming:
        log_flagged(site, plays, date)   # only today's slate goes into the track record
    n_teams = lineups.team.nunique() if len(lineups) else 0
    conf = lineups.groupby("team").confirmed.all().sum() if len(lineups) else 0
    meta.update(warnings=warnings, odds_rows=int(len(odds)), flagged=int(plays.flag.sum()) if len(plays) else 0,
                teams=int(n_teams), teams_confirmed=int(conf),
                data_through=str(tables["games"].date.max().date()), constants=cfg_src)
    json.dump(meta, open(os.path.join(site, "meta.json"), "w"), indent=2, default=str)
    print(f"{len(plays)} plays, {meta['flagged']} flagged")


def _append_odds(hist: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Append odds rows, keeping one date format (YYYY-MM-DD) in the stored history."""
    out = pd.concat([hist, new], ignore_index=True)
    out["date"] = pd.to_datetime(out.date.astype(str), format="mixed").dt.strftime("%Y-%m-%d")
    return out


LOG_KEYS = ["date", "game_id", "market", "selection", "line", "player_id"]


def log_flagged(site, plays, date):
    if plays.empty or not plays.flag.any():
        return
    f = os.path.join(site, "bets_log.csv")
    new = plays[plays.flag].copy()
    new["date"] = str(date.date())
    new["logged_at"] = pd.Timestamp.now(tz=ET).isoformat()
    keep = LOG_KEYS + ["matchup", "player", "projection", "p_model", "fair_odds", "p_novig", "best_price", "edge",
                       "confidence", "logged_at"]
    new = new[keep]
    old = _read(f)
    allr = pd.concat([old, new], ignore_index=True) if len(old) else new
    allr["line"] = pd.to_numeric(allr.line, errors="coerce")
    allr["player_id"] = pd.to_numeric(allr.player_id, errors="coerce")
    allr = allr.drop_duplicates(LOG_KEYS, keep="first")    # first time it was flagged = the bet price
    allr.to_csv(f, index=False)


def cmd_close(a):
    from .data import odds_api
    site = _site(a.state)
    now = pd.Timestamp.now(tz="UTC")
    date = today_et()
    sched = _schedule(date)
    if sched.empty:
        print("no games"); return
    st = pd.to_datetime(sched.start_utc, utc=True)
    hist = _read(os.path.join(site, "odds_history.csv.gz"))
    done = set(hist[hist.snapshot == "close"].game_id) if len(hist) else set()
    soon = sched[(st > now) & (st <= now + pd.Timedelta(minutes=a.window)) & ~sched.game_id.isin(done)]
    if soon.empty:
        print("no games starting soon"); return
    tables = load_tables(a.state)
    _, roster = projected_lineups(tables, soon, None, date, fetch_rosters(list(soon.home) + list(soon.away)))
    odds = odds_api.fetch(soon, roster, "close", props=not a.no_props, game_ids=set(soon.game_id))
    if len(odds):
        hist = _append_odds(hist, odds)
        hist.to_csv(os.path.join(site, "odds_history.csv.gz"), index=False, compression="gzip")
    print(f"closing odds for {len(soon)} games: {len(odds)} rows")


def cmd_grade(a):
    from .backtest import settle_game
    from .book import novig_table
    from .pricing import american_to_decimal
    site = _site(a.state)
    f = os.path.join(site, "bets_log.csv")
    log = _read(f)
    if log.empty:
        print("no logged plays"); return
    tables = load_tables(a.state)
    games = tables["games"].set_index("game_id")
    pg = tables["player_games"].set_index(["game_id", "player_id"])
    for c in ("result", "p_close", "clv_prob", "clv_ev", "profit"):
        if c not in log:
            log[c] = np.nan
    if "odds" in tables:
        close = novig_table(tables["odds"], DEFAULT, "close")
        if len(close):
            close = close[["game_id", "market", "selection", "line", "player_id", "p_novig"]].rename(
                columns={"p_novig": "p_close_new"})
            log = log.merge(close, on=["game_id", "market", "selection", "line", "player_id"], how="left")
            log["p_close"] = log.p_close.fillna(log.p_close_new)
            log = log.drop(columns="p_close_new")
    for i, r in log[log.result.isna()].iterrows():
        if r.game_id not in games.index:
            continue
        g = games.loc[r.game_id]
        if pd.isna(r.player_id):
            y = settle_game(r.market, r.selection, r.line, g)
        else:
            key = (r.game_id, int(r.player_id))
            if key not in pg.index:
                y = np.nan    # did not play: void
            else:
                stat = pg.loc[key, {"goals": "goals", "sog": "sog", "assists": "assists", "points": "points"}[r.market]]
                over = stat > r.line
                y = float(over if r.selection == "over" else not over)
        log.at[i, "result"] = y
    dec = log.best_price.map(american_to_decimal)
    log["clv_prob"] = log.p_close - log.p_novig
    log["clv_ev"] = log.p_close * dec - 1
    log["profit"] = np.where(log.result == 1, dec - 1, np.where(log.result == 0, -1.0, np.nan))
    log.to_csv(f, index=False)
    print(f"graded: {int(log.result.notna().sum())}/{len(log)}")


def cmd_backtest(a):
    from .backtest import walk_forward
    from .cli import _data_notes, run_validation
    site = _site(a.state)
    tables = load_tables(a.state)
    notes = tables.pop("_notes")
    cfg, src = config(a.state)
    dates = sorted(tables["games"].date.unique())
    if len(dates) < 60:
        print("not enough history to backtest"); return
    start, end = dates[max(0, len(dates) - a.days)], dates[-1]
    bt = walk_forward(tables, cfg, start, end, verbose=True)
    bt["games"].to_csv(os.path.join(site, "bt_games.csv.gz"), index=False, compression="gzip")
    keep = ["game_id", "date", "player_id", "pos", "lam_goals", "lam_sog", "lam_ast", "lam_pts",
            "lam_goals_nonen_pre", "lam_sog_pre", "lam_ast_raw_pre", "goals", "assists", "sog", "points"]
    bt["players"][keep].to_csv(os.path.join(site, "bt_players.csv.gz"), index=False, compression="gzip")
    summary, _ = run_validation(bt, tables, cfg, site, f"Walk-forward {pd.Timestamp(start).date()} to "
                                f"{pd.Timestamp(end).date()} ({src})", notes + _data_notes(tables, False))
    print(summary[["market", "line", "n", "logloss", "logloss_base", "status"]].to_string(index=False))


def cmd_tune(a):
    from .tuning import coordinate_search, save_config
    site = _site(a.state)
    tables = load_tables(a.state)
    tables.pop("_notes")
    dates = sorted(tables["games"].date.unique())
    start, end = dates[max(0, len(dates) - a.days)], dates[-1]
    best, log = coordinate_search(tables, DEFAULT, start, end, date_stride=3)
    log.to_csv(os.path.join(site, "grid_search.csv"), index=False)
    save_config(best, os.path.join(site, "tuned_config.json"))
    print("tuned ->", os.path.join(site, "tuned_config.json"))


def main(argv=None):
    p = argparse.ArgumentParser(prog="nhlmodel.daily")
    p.add_argument("cmd", choices=["update", "slate", "close", "grade", "backtest", "tune"])
    p.add_argument("--state", default="state")
    p.add_argument("--overrides", default="overrides")
    p.add_argument("--date")
    p.add_argument("--start", default=FIRST_SEASON_START)
    p.add_argument("--max-games", type=int)
    p.add_argument("--full", action="store_true", help="update: rescan the whole date range")
    p.add_argument("--max-minutes", type=float, default=240, help="update: stop fetching after this long")
    p.add_argument("--window", type=int, default=75, help="close: minutes ahead of puck drop")
    p.add_argument("--days", type=int, default=150, help="backtest/tune: number of recent game dates")
    p.add_argument("--no-props", action="store_true", help="skip player-prop odds (saves API credits)")
    a = p.parse_args(argv)
    {"update": cmd_update, "slate": cmd_slate, "close": cmd_close, "grade": cmd_grade,
     "backtest": cmd_backtest, "tune": cmd_tune}[a.cmd](a)


if __name__ == "__main__":
    main()
