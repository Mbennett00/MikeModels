import pandas as pd

from nhlmodel.daily import log_flagged, projected_lineups


def test_projected_lineups_and_overrides(league, tmp_path):
    tables, _ = league
    day = pd.Timestamp("2024-12-10")
    sched = tables["games"][tables["games"].date == day][["game_id", "date", "home", "away"]]
    lu, roster = projected_lineups(tables, sched, None, day)
    assert not lu.confirmed.any()
    assert (lu.pos == "G").sum() == 2 * len(sched)
    team = sched.home.iloc[0]
    other_goalie = roster[(roster.team == team) & (roster.pos == "G")].name.iloc[-1]
    ov = pd.DataFrame([dict(team=team, goalie=other_goalie, lineup_confirmed=True)])
    lu2, _ = projected_lineups(tables, sched, ov, day)
    g = lu2[(lu2.team == team) & (lu2.pos == "G")]
    assert g.name.iloc[0] == other_goalie and g.confirmed.iloc[0]
    assert lu2[(lu2.team == team) & (lu2.pos != "G")].confirmed.all()
    assert not lu2[lu2.team != team].confirmed.any()


def test_bet_log_keeps_first_price(tmp_path):
    base = dict(game_id=1, market="sog", selection="over", line=2.5, player_id=9, matchup="A @ B", player="X",
                projection="3.1", p_model=0.6, fair_odds=-150, p_novig=0.5, edge=0.1, confidence="normal", flag=True)
    log_flagged(str(tmp_path), pd.DataFrame([dict(base, best_price=120)]), pd.Timestamp("2026-10-10"))
    log_flagged(str(tmp_path), pd.DataFrame([dict(base, best_price=105)]), pd.Timestamp("2026-10-10"))
    log = pd.read_csv(tmp_path / "bets_log.csv")
    assert len(log) == 1 and log.best_price.iloc[0] == 120


def _roster_from(tables, team, date):
    lu = tables["lineups"]
    last = lu[(lu.team == team) & (lu.date < date)]
    last = last[last.date == last.date.max()]
    return last[["team", "player_id", "name", "pos"]].assign(headshot="https://example/h.png")


def test_roster_lineup_new_season_reflects_offseason_moves(league):
    tables, _ = league
    sched_day = pd.Timestamp("2025-10-08")      # new season, no games played yet in the data
    sched = pd.DataFrame([dict(game_id=1, date=sched_day, home="BOS", away="TOR")])
    ros = pd.concat([_roster_from(tables, t, sched_day) for t in ("BOS", "TOR")], ignore_index=True)
    # offseason: BOS loses its top forward, gains TOR's top forward
    lu = tables["lineups"]
    bos_top = lu[(lu.team == "BOS") & (lu.line == "F1")].player_id.iloc[0]
    tor_top = lu[(lu.team == "TOR") & (lu.line == "F1")].player_id.iloc[0]
    ros = ros[ros.player_id != bos_top]
    ros.loc[ros.player_id == tor_top, "team"] = "BOS"
    out, roster = projected_lineups(tables, sched, None, sched_day, ros)
    bos = out[out.team == "BOS"]
    assert bos_top not in set(out.player_id)
    assert tor_top in set(bos.player_id)
    assert bos.line.isin(["F1", "F2"]).loc[bos.player_id == tor_top].all()   # keeps a top-6 role
    assert (bos.pos == "F").sum() == 12 and (bos.pos == "D").sum() == 6 and (bos.pos == "G").sum() == 1
    assert set(out[out.pos == "G"].player_id) <= set(ros[ros.pos == "G"].player_id)
    assert bos.headshot.eq("https://example/h.png").all()
    assert any("no game yet" in n for n in out.attrs["notes"])


def test_roster_lineup_drops_departed_players_midseason(league):
    tables, _ = league
    day = pd.Timestamp("2024-12-10")
    sched = tables["games"][tables["games"].date == day][["game_id", "date", "home", "away"]].head(1)
    team = sched.home.iloc[0]
    ros = _roster_from(tables, team, day)
    ros = pd.concat([ros, _roster_from(tables, sched.away.iloc[0], day)])
    gone = ros[(ros.team == team) & (ros.pos == "F")].player_id.iloc[0]
    ros = ros[ros.player_id != gone]
    out, _ = projected_lineups(tables, sched, None, day, ros)
    t = out[out.team == team]
    assert gone not in set(t.player_id)
    assert (t.pos == "F").sum() == 12 or (t.pos == "F").sum() == 11


def test_odds_history_dates_stay_consistent():
    from nhlmodel.daily import _append_odds
    hist = pd.DataFrame(dict(date=["2026-09-30", "2026-09-30 00:00:00"], price=[100, 110]))
    new = pd.DataFrame(dict(date=[pd.Timestamp("2026-10-01")], price=[-120]))
    out = _append_odds(hist, new)
    assert out.date.tolist() == ["2026-09-30", "2026-09-30", "2026-10-01"]


def test_lean_pull_window_goes_by_clock_and_pulls_once():
    from nhlmodel.daily import ET, lean_pull_window
    t = lambda s: pd.Timestamp(f"2026-10-02 {s}", tz=ET)
    empty = pd.DataFrame()
    assert lean_pull_window(t("09:00"), empty, "williamhill_us") is None
    assert lean_pull_window(t("13:40"), empty, "williamhill_us") == "morning"      # a late 11am run still pulls
    assert lean_pull_window(t("18:20"), empty, "williamhill_us") == "evening"
    assert lean_pull_window(t("21:00"), empty, "williamhill_us") is None            # too late: games started
    done = pd.DataFrame(dict(book=["williamhill_us"], fetched_at=[t("11:02").tz_convert("UTC").isoformat()]))
    assert lean_pull_window(t("15:30"), done, "williamhill_us") is None             # morning already pulled
    assert lean_pull_window(t("18:00"), done, "williamhill_us") == "evening"
    assert lean_pull_window(t("02:00"), done, "williamhill_us", force=True) == "manual"
    assert lean_pull_window(t("13:40"), empty, "williamhill_us", tried=["morning"]) is None   # empty pull: no retry
