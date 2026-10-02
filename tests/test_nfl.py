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


def test_injured_starters_count_by_snap_share_and_status():
    from nflmodel import injuries as I
    sched = pd.DataFrame(dict(game_id=[f"g{i}" for i in range(4)], gameday=pd.date_range("2026-09-07", periods=4, freq="7D")))
    rows = []
    for gid in sched.game_id:
        rows += [dict(game_id=gid, team="KC", player="Star Receiver", position="WR", offense_pct=0.9, defense_pct=0.0),
                 dict(game_id=gid, team="KC", player="Depth Guy", position="WR", offense_pct=0.05, defense_pct=0.0),
                 dict(game_id=gid, team="KC", player="Top Corner Jr.", position="CB", offense_pct=0.0, defense_pct=1.0)]
    S = I.prep_snaps(pd.DataFrame(rows), sched)
    regs = I.regulars(S, "KC", "2026-10-05")
    assert set(regs.index) == {"star receiver", "top corner"}           # 5% snap player is below the floor
    rep = pd.DataFrame(dict(key=["star receiver", "top corner", "depth guy", "star receiver"],
                            status=["Out", "Questionable", "Out", "Questionable"], pos=["WR", "CB", "WR", "WR"]))
    miss, det = I.missing(regs, rep)
    assert abs(miss["REC"] - 0.9) < 1e-9                                # duplicate row counted once, most severe
    assert abs(miss["DB"] - 0.33) < 1e-9
    assert [d["name"] for d in det] == ["Star Receiver", "Top Corner Jr."]


def test_espn_injury_parsing(monkeypatch):
    from nflmodel import injuries as I

    class R:
        def raise_for_status(self): pass
        def json(self):
            return {"injuries": [{"displayName": "Los Angeles Rams", "injuries": [
                {"status": "Out", "athlete": {"displayName": "Puka Nacua", "position": {"abbreviation": "WR"}},
                 "details": {"type": "Ankle"}}]}]}
    monkeypatch.setattr(I.requests, "get", lambda *a, **k: R())
    d = I.fetch_espn(log=lambda *a: None)
    assert d.iloc[0].team == "LA" and d.iloc[0].key == "puka nacua" and d.iloc[0].status == "Out"


def test_ruled_out_qb_is_replaced_by_backup():
    from nflmodel.daily import qb_starter
    qb = pd.DataFrame(dict(team=["KC"] * 3, name=["P.Mahomes", "G.Minshew", "P.Mahomes"], dropbacks=[40, 12, 38],
                           date=pd.to_datetime(["2026-09-14", "2026-09-14", "2026-09-21"])))
    rep = pd.DataFrame(dict(key=["patrick mahomes"], status=["Out"]))
    name, note = qb_starter(qb, "KC", "Patrick Mahomes", rep, "2026-10-01")
    assert name == "G.Minshew" and "Out" in note
    assert qb_starter(qb, "KC", "Patrick Mahomes", rep.assign(status="Questionable"), "2026-10-01")[0] == "Patrick Mahomes"


def test_baseline_reflects_how_much_he_is_in_the_ratings():
    from nflmodel import injuries as I
    sched = pd.DataFrame(dict(game_id=["g0", "g1", "g2", "g3"], gameday=pd.date_range("2026-09-07", periods=4, freq="7D")))
    rows = [dict(game_id=g, team="KC", player="Every Week", position="TE", offense_pct=0.8, defense_pct=0) for g in sched.game_id]
    rows += [dict(game_id=g, team="KC", player="Hurt Early", position="RB", offense_pct=0.8, defense_pct=0) for g in ("g0",)]
    rows += [dict(game_id="g0", team="CLE", player="Traded In", position="DE", offense_pct=0, defense_pct=0.9)]
    rows += [dict(game_id=g, team="KC", player="Traded In", position="DE", offense_pct=0, defense_pct=0.9) for g in ("g3",)]
    regs = I.regulars(I.prep_snaps(pd.DataFrame(rows), sched), "KC", "2026-10-05")
    assert abs(regs.loc["every week", "share"] - 0.8) < 1e-9 and abs(regs.loc["every week", "presence"] - 1) < 1e-9
    assert regs.loc["hurt early", "share"] < 0.25                      # mostly gone from the ratings already
    assert 0.2 < regs.loc["traded in", "share"] < 0.3                   # only his game for KC counts


def _box(n_games=6):
    rows = []
    d0 = pd.Timestamp("2026-09-07")
    for k in range(n_games):
        gid, date = f"2026_{k:02d}_KC_LV", d0 + pd.Timedelta(days=7 * k)
        base = dict(game_id=gid, season=2026, week=k + 1, date=date, team="KC", opp="LV")
        z = dict(tgt=0, rz_tgt=0, rec=0, rec_yds=0, rec_td=0, car=0, rz_car=0, rush_yds=0, rush_td=0, att=0, cmp=0, pass_yds=0, pass_td=0, ints=0)
        mk = lambda **kw: {**base, **z, **kw}
        rows += [mk(player_id="qb", name="Q.Back", att=34, cmp=22, pass_yds=250, pass_td=2),
                 mk(player_id="wr1", name="W.One", tgt=10, rz_tgt=2, rec=7, rec_yds=90, rec_td=1),
                 mk(player_id="wr2", name="W.Two", tgt=5, rz_tgt=1, rec=3, rec_yds=40),
                 mk(player_id="rb", name="R.Back", car=18, rz_car=3, rush_yds=80, rush_td=1, tgt=3, rec=2, rec_yds=15)]
    return pd.DataFrame(rows)


def test_props_projection_and_injury_redistribution():
    from nflmodel import props as PP
    pg = _box()
    tg = PP.team_games(pg)
    cfg = PP.PropConfig(); cfg.priors = PP.fit_priors(pg)
    games = pd.DataFrame([dict(game_id="next", team="KC", opp="LV", pts=24.0, margin=0.0)])
    pr = PP.project(pg, tg, "2026-10-20", games, cfg).set_index("player_id")
    assert pr.loc["wr1", "rec_yds"] > pr.loc["wr2", "rec_yds"] > 0
    assert pr.loc["rb", "rush_yds"] > 50 and 150 < pr.loc["qb", "pass_yds"] < 350
    assert pr.loc["wr1", "lam_td"] > 0 and pd.isna(pr.loc["wr1", "pass_yds"])
    # WR1 out: WR2 picks up targets
    pr2 = PP.project(pg, tg, "2026-10-20", games, cfg, available={"KC": {"qb", "wr2", "rb"}}).set_index("player_id")
    assert "wr1" not in pr2.index and pr2.loc["wr2", "tgt"] > pr.loc["wr2", "tgt"]
    # leading teams run more
    lead = PP.project(pg, tg, "2026-10-20", games.assign(margin=10.0), cfg).set_index("player_id")
    assert lead.loc["rb", "car"] > pr.loc["rb", "car"] and lead.loc["wr1", "tgt"] < pr.loc["wr1", "tgt"]


def test_prop_probabilities_behave():
    from nflmodel import props as PP
    cfg = PP.PropConfig()
    row = dict(rec=5.0, rec_yds=60.0, rush_yds=70.0, pass_yds=250.0, lam_pass_td=1.6, lam_td=0.5)
    assert PP.p_over(row, "rec_yds", 30.5, cfg) > PP.p_over(row, "rec_yds", 60.5, cfg) > PP.p_over(row, "rec_yds", 90.5, cfg)
    assert 0.3 < PP.p_over(row, "rush_yds", 65.5, cfg) < 0.7
    assert abs(PP.p_over(row, "td", 0.5, cfg) - (1 - np.exp(-0.5))) < 1e-9
    assert PP.p_over(row, "pass_td", 0.5, cfg) > PP.p_over(row, "pass_td", 1.5, cfg)


def test_nfl_changelog_lists_injury_qb_and_line_moves():
    from nflmodel import changelog as CL
    def out(status, qb, spread, week=4):
        g = dict(game_id="g1", state="pre", home=dict(abbr="CHI", qb="Caleb Williams", inj_pts=-1.0),
                 away=dict(abbr="NYJ", qb=qb, inj_pts=-2.0), margin=5.0, total=44.0, spread=spread, total_line=43.0, src="odds")
        return dict(meta=dict(generated_at="2026-10-02T12:00:00-04:00", week=week, data_through="2026-10-01", odds_at=None,
                              pts_per_starter=1.07), games=[g],
                    injuries={"NYJ": dict(counted=[dict(name="Breece Hall", status=status, pos="RB", pts=-0.6)], qbs=[])})
    first = CL.diff(None, CL.snapshot(out("Questionable", "Geno Smith", 3.5)))
    assert first[0]["kind"] == "data"
    items = CL.diff(CL.snapshot(out("Questionable", "Geno Smith", 3.5)), CL.snapshot(out("Out", "Tyrod Taylor", 5.0)))
    kinds = {i["kind"] for i in items}
    assert {"injury", "qb", "line"} <= kinds
    assert any("Questionable → Out" in i["text"] for i in items)
    assert any("CHI -3.5 → CHI -5" in i["text"] for i in items)
