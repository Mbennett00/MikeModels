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


def test_starting_qb_comes_from_the_depth_chart_skipping_ruled_out():
    from nflmodel.daily import qb_starter
    qb = pd.DataFrame(dict(team=["SEA"], name=["D.Lock"], dropbacks=[30], date=pd.to_datetime(["2026-09-21"])))
    depth = {"SEA": ["Sam Darnold", "Drew Lock"], "CHI": ["Caleb Williams", "Tyson Bagent", "Case Keenum"]}
    none = pd.DataFrame(columns=["key", "status"])
    # schedule still lists last week's starter; the depth chart says Darnold is back
    assert qb_starter(qb, "SEA", "Drew Lock", none, "2026-10-04", depth=depth) == ("Sam Darnold", None)
    rep = pd.DataFrame(dict(key=["caleb williams"], status=["Out"]))
    name, note = qb_starter(qb, "CHI", "Case Keenum", rep, "2026-10-04", depth=depth)
    assert name == "Tyson Bagent" and note == "Caleb Williams Out"   # next healthy QB on the chart
    # next man up is himself questionable while the team has been starting someone else on the chart: keep that QB
    rep2 = pd.DataFrame(dict(key=["caleb williams", "tyson bagent"], status=["Out", "Questionable"]))
    assert qb_starter(qb, "CHI", "Case Keenum", rep2, "2026-10-04", depth=depth)[0] == "Case Keenum"
    # no depth chart for the team: old behaviour (listed QB)
    assert qb_starter(qb, "KC", "Patrick Mahomes", none, "2026-10-04", depth=depth)[0] == "Patrick Mahomes"


def test_depth_qbs_takes_latest_snapshot(tmp_path, monkeypatch):
    from nflmodel import data
    d = pd.DataFrame(dict(dt=["2026-10-03T13:00:00Z", "2026-10-03T13:00:00Z", "2026-10-04T13:00:00Z", "2026-10-04T13:00:00Z",
                              "2026-10-05T13:00:00Z"],
                          team=["SEA"] * 5, player_name=["Drew Lock", "Sam Darnold", "Sam Darnold", "Drew Lock", "X"],
                          pos_abb=["QB"] * 5, pos_rank=[1, 2, 1, 2, 1], pos_slot=[1] * 5))
    d.to_parquet(tmp_path / "depth2026.parquet")
    monkeypatch.setattr(data, "LOCAL", str(tmp_path))
    assert data.depth_qbs(2026, str(tmp_path), "2026-10-04 12:00")["SEA"] == ["Sam Darnold", "Drew Lock"]


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


def test_props_recalibrate_shrinks_toward_one():
    from nflmodel import props as PP
    rng = np.random.default_rng(0)
    n = 300
    g = pd.DataFrame(dict(rec=np.full(n, 5.0), rec_yds=np.full(n, 60.0), rush_yds=np.nan, pass_yds=np.nan,
                          p_td=np.full(n, 0.3), a_rec=rng.poisson(5.5, n), a_rec_yds=np.full(n, 66.0),
                          a_rush_yds=np.nan, a_pass_yds=np.nan, a_td=(rng.random(n) < 0.3).astype(float)))
    lv = PP.recalibrate(g)
    assert 1.0 < lv["rec_yds"]["level"] < 1.1                  # raw 1.10, pulled toward 1 by the prior
    assert abs(lv["rec_yds"]["raw"] - 1.1) < 1e-9 and lv["rec_yds"]["n"] == n
    assert 0.85 <= lv["td"]["level"] <= 1.15
    assert "rush_yds" not in lv                                # no data, no change


def test_grade_record_counts_leans_and_flags():
    from nflmodel.daily import grade_record
    sched = pd.DataFrame(dict(game_id=["2026_04_A_B"], result=[7.0], total=[40.0]))
    frozen = {"2026_04_A_B": dict(week=4, spread=3.5, total_line=44.5, bets=[
        dict(m="spread", s="home", edge=0.07, price=-110),     # home -3.5, won by 7: win, flagged
        dict(m="total", s="over", edge=0.04, price=-110),      # 40 < 44.5: loss, lean only
        dict(m="ml", s="away", edge=0.01, price=150)])}        # below 3 points: ignored
    r = grade_record(frozen, sched, 2026)
    assert (r["lean"]["w"], r["lean"]["l"]) == (1, 1) and (r["flag"]["w"], r["flag"]["l"]) == (1, 0)
    assert abs(r["lean"]["units"] - (100 / 110 - 1)) < 0.01


def test_changelog_reports_model_recal_teams_and_record():
    from nflmodel import changelog as CL
    def snap(hfa, lvl, net, w):
        return dict(time="t", week=4, data_through="2026-10-01", games={}, inj={}, qbs={}, pts={},
                    model=dict(hfa=hfa, sd_margin=13.0, sd_total=13.3, league_total=44.0),
                    recal={"rec_yds": dict(level=lvl, raw=1.1, n=120)}, teams={"SEA": dict(net=net)},
                    record={"lean": dict(w=w, l=2, p=0, units=0.5)})
    items = CL.diff(snap(1.6, 1.0, 0.10, 3), snap(1.4, 1.03, 0.13, 5))
    kinds = {i["kind"] for i in items}
    assert {"model", "recal", "teams", "record"} <= kinds


def test_weather_exposure_and_prop_factor():
    from nflmodel import weather as WX
    assert WX.exposure("BUF00", "outdoors") == "outdoor"
    assert WX.exposure("DET00", "dome") == "dome"
    assert WX.exposure("HOU00", float("nan")) == "retractable"
    assert WX.exposure("PAR00", "dome") == "outdoor"           # nflverse marks Stade de France as a dome
    assert WX.prop_factor("rush_yds", 25, 1.0) == 1.0
    assert WX.prop_factor("pass_yds", 5, 0) == 1.0
    assert WX.prop_factor("pass_yds", 20, 1.0) < WX.prop_factor("pass_yds", 14, 0) < 1.0
    assert WX.rain_flag("Light Rain Temp: 45° F") == 1.0 and WX.rain_flag("Sunny Temp: 70° F") == 0.0


def test_weather_forecast_window(monkeypatch):
    from nflmodel import weather as WX
    times = pd.date_range("2026-10-04 15:00", periods=8, freq="h").strftime("%Y-%m-%dT%H:%M").tolist()

    class R:
        def raise_for_status(self): pass
        def json(self):
            n = len(times)
            return {"hourly": dict(time=times, temperature_2m=[50.0] * n, wind_speed_10m=[10, 12, 18, 20, 22, 9, 9, 9],
                                   wind_gusts_10m=[20] * n, precipitation_probability=[0, 0, 80, 80, 80, 0, 0, 0],
                                   rain=[0, 0, 1.0, 1.0, 1.0, 0, 0, 0], showers=[0] * n, snowfall=[0] * n, weather_code=[61] * n)}
    monkeypatch.setattr(WX.requests, "get", lambda *a, **k: R())
    w = WX.forecast("BUF00", pd.Timestamp("2026-10-04 17:00", tz="UTC"), log=lambda *a: None)
    assert w["wind"] == 20.0 and w["pp"] == 0.8 and w["rain"] == 0.8
    icon, txt = WX.describe(w, "outdoor")
    assert icon == "🌧️" and "80% rain" in txt


def test_rain_lowers_the_total_feature():
    from nflmodel import model as M
    R = M.Ratings(pd.Timestamp("2026-10-01"), {m: 0.0 for m in M.METRICS}, {m: 0.0 for m in M.METRICS},
                  {m: {} for m in M.METRICS}, {m: {} for m in M.METRICS})
    _, dry = M.features(R, "A", "B", roof="outdoors", wind=5, temp=60)
    _, wet = M.features(R, "A", "B", roof="outdoors", wind=5, temp=60, rain=1.0)
    _, dome = M.features(R, "A", "B", roof="dome", wind=25, temp=20, rain=1.0)
    assert dry[-1] == 0 and wet[-1] == 1.0 and dome[-1] == 0 and dome[-2] == 0 and dome[-3] == 0


def test_blend_weights_and_market_shift_edges():
    from nflmodel.daily import blend_weights, bets_for, total_bias
    from nflmodel import model as M
    rng = np.random.default_rng(1)
    n = 600
    close = rng.normal(0, 6, n)
    noise_model = close + rng.normal(0, 3, n)                  # model = market + pure noise
    result = close + rng.normal(0, 13, n)
    tl = rng.normal(45, 4, n); truth = tl + rng.normal(0, 2, n)
    tmod = truth + rng.normal(0, 2, n) + 1.0                   # model knows something about totals, runs 1 pt high
    tot = truth + rng.normal(0, 12, n)
    bt = pd.DataFrame(dict(result=result, spread_line=close, m_model=noise_model, total=tot, total_line=tl, t_model=tmod))
    ws, wt = blend_weights(bt)
    assert ws <= 0.15 and wt >= 0.2
    assert 0.5 < total_bias(bt) < 1.5
    cfg = M.Config(key_m={7: 2.0, 3: 2.5}, key_t={})
    p = M.price_game(-7.0, 44.0, cfg, -7.0, 44.0)               # model centred exactly on the market
    rows = bets_for(p, {"spread": dict(p_first=0.5), "total": dict(p_first=0.5)}, "line", "CZR", p0=p)
    assert all(abs(b["edge"]) < 1e-9 for b in rows if b["m"] in ("spread", "total"))


def test_star_values_team_aware_and_usage():
    from nflmodel import injuries as I
    con = pd.DataFrame(dict(player=["Justin Jefferson", "Justin Jefferson", "Puka Nacua", "Top Pick"],
                            team=["Vikings", "Browns", "Rams", "Jets"], position=["WR", "WR", "WR", "CB"],
                            year_signed=[2024, 2026, 2023, 2025], years=[4, 4, 4, 4], apy_cap_pct=[0.137, 0.004, 0.004, 0.02],
                            draft_year=[2020, 2026, 2023, 2025], draft_round=[1, 7, 5, 1]))
    cv = I.contract_values(con)
    v_min = I.team_values(cv, 2026, "MIN", 1.0)
    assert I.value_of(v_min, "justin jefferson") == 2.5                 # the Vikings' star, not the namesake
    v_cle = I.team_values(cv, 2026, "CLE", 1.0)
    assert I.value_of(v_cle, "justin jefferson") == 0.5
    v_la = I.team_values(cv, 2026, "LA", 1.0, shares={"p nacua": (0.30, 0.0)})
    assert 1.8 < I.value_of(v_la, "puka nacua") <= 2.5                  # rookie deal, but a 30% target share
    v_nyj = I.team_values(cv, 2026, "NYJ", 1.0)
    assert I.value_of(v_nyj, "top pick") == 1.25                        # first-round rookie floor
    assert I.value_of(v_nyj, "nobody") == 1.0


def test_matchup_grades_from_yards_allowed():
    from nflmodel.daily import defense_allowed, grade
    rows = []
    d0 = pd.Timestamp("2026-09-07")
    for k in range(6):
        for off, dfn, wr in (("A", "SOFT", 250), ("B", "HARD", 90)):
            gid = f"g{k}{dfn}"
            base = dict(game_id=gid, date=d0 + pd.Timedelta(days=7 * k), team=off, opp=dfn, tgt=0, car=0, rec_yds=0,
                        rush_yds=0, pass_yds=0)
            rows += [dict(base, player_id=f"{off}wr", tgt=10, rec_yds=wr), dict(base, player_id=f"{off}rb", car=15, rush_yds=80),
                     dict(base, player_id=f"{off}qb", pass_yds=wr + 30)]
    pg = pd.DataFrame(rows)
    a = defense_allowed(pg, None, "2026-10-30")
    assert a["SOFT"]["WR"] > 1.1 > 0.9 > a["HARD"]["WR"]
    assert grade(a["SOFT"]["WR"]) in ("A", "A+") and grade(a["HARD"]["WR"]) in ("D", "F")
    assert grade(1.0) == "B"


def test_dk_props_parse_and_daily_pull():
    import pandas as pd
    from nflmodel import odds as O
    from nflmodel.injuries import norm
    ev = {"bookmakers": [
        {"key": "fanduel", "markets": [{"key": "player_rush_yds", "outcomes": [{"name": "Over", "description": "Bijan Robinson", "point": 80.5, "price": -110}]}]},
        {"key": "draftkings", "markets": [
            {"key": "player_rush_yds", "outcomes": [{"name": "Over", "description": "Bijan Robinson", "point": 74.5, "price": -115},
                                                    {"name": "Under", "description": "Bijan Robinson", "point": 74.5, "price": -105}]},
            {"key": "player_anytime_td", "outcomes": [{"name": "Yes", "description": "Bijan Robinson", "price": -150}]},
            {"key": "player_receptions", "outcomes": [{"name": "Over", "description": "Drake London", "point": 5.5, "price": 120}]}]}]}
    got = O.parse_props(ev, norm)
    b = got[norm("Bijan Robinson")]
    assert b["rush_yds|74.5"] == {"o": -115, "u": -105} and b["td|0.5"] == {"o": -150}
    assert "rush_yds|80.5" not in b                       # other books ignored
    assert got[norm("Drake London")]["rec|5.5"] == {"o": 120}
    now = pd.Timestamp("2026-10-04 11:00", tz="America/New_York")
    assert O.props_due(None, now, [{"id": "x"}])
    assert not O.props_due({"pulled_on": "2026-10-04"}, now, [{"id": "x"}])   # once a day
    assert O.props_due({"pulled_on": "2026-10-03"}, now, [{"id": "x"}])
    assert not O.props_due(None, now, [])                                    # no games today
    assert not O.props_due(None, pd.Timestamp("2026-10-04 06:00", tz="America/New_York"), [{"id": "x"}])
