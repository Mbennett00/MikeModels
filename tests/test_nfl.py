import numpy as np
import pandas as pd

from nflmodel import model as M, odds as O
from nflmodel.daily import week_games


def _league(n_weeks=10, seed=0):
    """Synthetic team-games: team T0 is far better on offense, T3 far worse on defense."""
    rng = np.random.default_rng(seed)
    teams = ["T0", "T1", "T2", "T3"]
    rows, sched = [], []
    d0 = pd.Timestamp("2025-09-07")
    for w in range(n_weeks):
        for i, (h, a) in enumerate([("T0", "T1"), ("T2", "T3")] if w % 2 == 0 else [("T0", "T3"), ("T1", "T2")]):
            gid = f"2025_{w:02d}_{a}_{h}"
            pts = {}
            for off, dfn in ((h, a), (a, h)):
                epa = 0.25 * (off == "T0") + 0.2 * (dfn == "T3") + rng.normal(0, 0.03)
                n = 60
                rows.append(dict(game_id=gid, team=off, opp=dfn, season=2025, week=w + 1, season_type="REG",
                                 date=d0 + pd.Timedelta(days=7 * w), home_team=h, n_pass=36, n_rush=24,
                                 epa_pass=epa * 36, epa_rush=epa * 24, success=0.45))
                pts[off] = 20 + 40 * epa
            sched.append(dict(game_id=gid, season=2025, week=w + 1, home_team=h, away_team=a, location="Home",
                              home_score=pts[h], away_score=pts[a], result=pts[h] - pts[a]))
    tg = pd.DataFrame(rows)
    return tg, pd.DataFrame(sched), teams


def test_ratings_find_the_strong_offense_and_weak_defence():
    tg, sched, teams = _league()
    rows = M.team_rows(tg, sched)
    R = M.fit_ratings(rows, "2026-01-01", M.Config(ridge=1.0))
    off = R.off["epa_play"]
    assert max(off, key=off.get) == "T0"
    dfn = R.dfn["epa_play"]
    assert max(dfn, key=dfn.get) == "T3"      # defence rating = EPA allowed, so the worst defence is highest


def test_margin_pmf_keeps_mean_and_bumps_key_numbers():
    key = {k: 1.0 for k in range(71)}
    key[3], key[7] = 2.0, 1.6
    ks, p = M.pmf(2.5, 13.5, key, True, -70, 70)
    assert abs(p.sum() - 1) < 1e-9
    assert abs((ks * p).sum() - 2.5) < 1e-3
    assert p[ks == 3][0] > 1.5 * p[ks == 2][0]


def test_price_game_is_consistent():
    cfg = M.Config(key_m={}, key_t={})
    even = M.price_game(0.0, 44.0, cfg, 0.0, 44.0)
    assert abs(even["p_home"] - 0.5) < 1e-6 and abs(even["p_home_cover"] - 0.5) < 1e-6 and abs(even["p_over"] - 0.5) < 2e-3
    fav = M.price_game(7.0, 44.0, cfg, 3.0, 40.5)
    assert fav["p_home"] > 0.65 and fav["p_home_cover"] > 0.55 and fav["p_over"] > 0.55


def test_qb_name_matching():
    lv = pd.DataFrame(dict(name=["P.Mahomes", "C.Wentz", "M.Penix"], team=["KC", "KC", "ATL"],
                           last=pd.to_datetime(["2026-09-28", "2025-01-05", "2026-09-28"]), level=[0.2, -0.05, 0.0]),
                      index=["id1", "id2", "id3"])
    assert M._match_qb(lv, "Patrick Mahomes", "KC") == "id1"
    assert M._match_qb(lv, "Michael Penix Jr.", "ATL") == "id3"
    assert M._match_qb(lv, "Nobody Here", "KC") is None


def _event(books):
    return dict(home_team="Kansas City Chiefs", away_team="Las Vegas Raiders", commence_time="2026-10-04T20:25:00Z",
                bookmakers=books)


def _book(key, title, hp, ap, line, sh, sa, tot, o, u):
    return dict(key=key, title=title, markets=[
        dict(key="h2h", outcomes=[dict(name="Kansas City Chiefs", price=hp), dict(name="Las Vegas Raiders", price=ap)]),
        dict(key="spreads", outcomes=[dict(name="Kansas City Chiefs", price=sh, point=line),
                                      dict(name="Las Vegas Raiders", price=sa, point=-line)]),
        dict(key="totals", outcomes=[dict(name="Over", price=o, point=tot), dict(name="Under", price=u, point=tot)])])


def test_consensus_uses_the_common_line_and_keeps_caesars_price():
    ev = _event([_book("draftkings", "DraftKings", -200, 170, -4.5, -110, -110, 47.5, -110, -110),
                 _book("fanduel", "FanDuel", -210, 175, -4.5, -105, -115, 47.5, -105, -115),
                 _book("caesars_new", "Caesars Sportsbook", -190, 160, -4.5, -112, -108, 48.0, -110, -110),
                 _book("bovada", "Bovada", -205, 170, -5.0, -110, -110, 47.5, -110, -110)])
    c = O.consensus(ev, "williamhill_us")
    assert c["spread"]["line"] == -4.5 and c["spread"]["n"] == 3
    assert c["total"]["line"] == 47.5 and c["total"]["n"] == 3
    assert 0.6 < c["ml"]["p_home"] < 0.7
    assert c["ml"]["book_home"] == -190 and c["spread"]["book_first"] == -112
    assert c["total"]["book_first"] is None        # Caesars hangs 48, not the consensus 47.5


def test_match_events_to_schedule():
    g = pd.DataFrame(dict(game_id=["2026_04_KC_LV"], home_team=["KC"], away_team=["LV"], gameday=pd.to_datetime(["2026-10-04"])))
    assert list(O.match([_event([])], g)) == ["2026_04_KC_LV"]


def test_odds_pull_once_a_day_after_1030():
    et = lambda s: pd.Timestamp(s, tz="America/New_York")
    assert not O.due(None, et("2026-10-04 09:00"), True)
    assert O.due(None, et("2026-10-04 10:45"), True)
    assert not O.due(None, et("2026-10-04 10:45"), False)
    done = dict(fetched_at=et("2026-10-04 10:40").tz_convert("UTC").isoformat())
    assert not O.due(done, et("2026-10-04 18:00"), True)
    assert O.due(done, et("2026-10-05 11:00"), True)
    assert O.due(done, et("2026-10-04 18:00"), True, force=True)


def test_week_games_picks_the_week_still_being_played():
    s = pd.DataFrame(dict(game_id=["a", "b", "c"], season=[2026] * 3, week=[4, 4, 5],
                          gameday=pd.to_datetime(["2026-10-01", "2026-10-04", "2026-10-08"]), gametime=["20:15", "13:00", "20:15"],
                          result=[3.0, np.nan, np.nan]))
    w = week_games(s, pd.Timestamp("2026-10-02 12:00", tz="America/New_York"))
    assert list(w.game_id) == ["a", "b"]
