from calib import odds, sharp


def row(book, mt, sel, line, am, who=None, st="over", **kw):
    r = {"sportsbook": book, "market_type": mt, "selection": sel, "selection_type": st, "line": line, "odds_american": am,
         "player_name": who, "is_live": False, "home_team": "New Jersey Devils", "away_team": "Colorado Avalanche",
         "event_id": "e1", "event_start_time": "2026-10-20T23:00Z"}
    r.update(kw)
    return r


def test_props_two_books_fair_and_fanduel_fill():
    R = [row("draftkings", "player_points", "Over", 1.5, -105, "Nathan MacKinnon"),
         row("draftkings", "player_points", "Under", 1.5, -125, "Nathan MacKinnon", st="under"),
         row("fanduel", "player_points", "Over", 1.5, 100, "Nathan MacKinnon"),
         row("fanduel", "player_points", "Over", 3.5, 900, "Nathan MacKinnon"),          # only FanDuel hangs 4+
         row("fanduel", "anytime_goal_scorer", "Nathan MacKinnon", None, 120, "Nathan MacKinnon", st="other"),
         row("fanduel", "player_points", "Over", 2.0, 400, "Nathan MacKinnon"),          # whole line: skipped
         row("fanduel", "player_power_play_points", "Over", 0.5, 145, "Nathan MacKinnon"),   # not a page stat
         row("draftkings", "player_points", "Over", 0.5, -400, "Any Player")]
    P = sharp.build_props("NHL", R)
    m = P["props"]["nathanmackinnon"]
    assert m == {"points|1.5": -105, "points|3.5": 900, "goals|0.5": 120}
    assert P["bk"]["nathanmackinnon"] == {"points|3.5": "FD", "goals|0.5": "FD"}
    f = P["fair"]["nathanmackinnon"]["points|1.5"]
    dk = sharp._p(-105) / (sharp._p(-105) + sharp._p(-125)); fd = 0.5 / sharp.hold1(0.5)
    assert abs(f - (dk + fd) / 2) < 1e-3
    assert "anyplayer" not in P["props"]


def test_games_consensus():
    R = [row("draftkings", "moneyline", "x", None, -150, st="away"), row("draftkings", "moneyline", "x", None, 130, st="home"),
         row("fanduel", "moneyline", "x", None, -140, st="away"), row("fanduel", "moneyline", "x", None, 120, st="home"),
         row("fanduel", "puck_line", "x", -1.5, 200, st="home"), row("fanduel", "puck_line", "x", 1.5, -240, st="away"),
         row("fanduel", "total_goals", "Over", 6.5, -105), row("fanduel", "total_goals", "Under", 6.5, -115, st="under")]
    g = sharp.build_games("NHL", R)[0]
    assert g["home"] == "New Jersey Devils" and g["books"] == 2 and g["t"] == "2026-10-20T23:00:00Z"
    assert g["spread"] == {"home": -1.5, "home_price": 200, "away_price": -240} and g["total"]["line"] == 6.5
    assert g["ml"]["away"] < -140 and g["ml"]["home"] > 120


def test_merge_takes_both_books():
    out = {"props": {"NHL": {"book": "DraftKings", "players": {"old": {"points|1.5": -110}}}}, "lines": {"NHL": {"games": [{"home": "X"}]}}}
    sh = {"NHL": {"fetched_at": "t", "complete": True, "props": {"nathanmackinnon": {"points|1.5": -105, "points|3.5": 900}},
                  "bk": {"nathanmackinnon": {"points|3.5": "FD"}}, "fair": {"nathanmackinnon": {"points|1.5": 0.49}},
                  "games": [{"home": "New Jersey Devils", "away": "Colorado Avalanche"}]}}
    odds.merge_sharp(out, sh, log=lambda *_: None)
    P = out["props"]["NHL"]
    assert P["players"] == {"nathanmackinnon": {"points|1.5": -105, "points|3.5": 900}} and P["book"] == "DraftKings + FanDuel"
    assert [g["home"] for g in out["lines"]["NHL"]["games"]] == ["New Jersey Devils"]


def test_misfiled_period_market_is_dropped():
    """DraftKings' 1st-quarter points came through as full-game player_points (1+ points at -112)."""
    J = "John Collins"
    R = [row("draftkings", "player_points", "Over", 0.5, -112, J, market_id="q1"),
         row("draftkings", "player_points", "Over", 1.5, -108, J, market_id="q1"),
         row("draftkings", "player_points", "Over", 2.5, 323, J, market_id="q1"),
         row("draftkings", "player_points", "Over", 12.5, 101, J, market_id="full"),
         row("draftkings", "player_points", "Under", 12.5, -129, J, st="under", market_id="full"),
         row("fanduel", "player_points", "Over", 4.5, -2800, J, market_id="fd1"),
         row("fanduel", "player_points", "Over", 11.5, -122, J, market_id="fd2"),
         row("fanduel", "player_points", "Under", 11.5, -108, J, st="under", market_id="fd2"),
         row("fanduel", "player_points", "Over", 13.5, 148, J, market_id="fd2"),
         row("fanduel", "player_points", "Over", 24.5, 1700, J, market_id="fd3")]
    m = sharp.build_props("NBA", R)["props"]["johncollins"]
    assert set(m) == {"pts|12.5", "pts|4.5", "pts|11.5", "pts|13.5", "pts|24.5"}
    assert m["pts|12.5"] == 101


def test_ladder_judged_from_even_money():
    F = {"pts|0.5": 0.53, "pts|4.5": 0.96, "pts|11.5": 0.53, "pts|12.5": 0.48, "pts|13.5": 0.38, "pts|24.5": 0.05}
    assert sharp.ladder_drop(F) == ["pts|0.5"]


def test_quarter_market_cannot_anchor_a_book():
    """Ausar Thompson: DraftKings' only two-way rebounds market was a 1st-quarter one (4+ at +561 next to 5+ at -308)."""
    A = "Ausar Thompson"
    R = [row("draftkings", "player_rebounds", "Over", 1.5, -110, A, market_id="q1"),
         row("draftkings", "player_rebounds", "Under", 1.5, -110, A, st="under", market_id="q1"),
         row("draftkings", "player_rebounds", "Over", 3.5, 561, A, market_id="q1"),
         row("draftkings", "player_rebounds", "Over", 4.5, -308, A, market_id="m4"),
         row("draftkings", "player_rebounds", "Over", 5.5, -167, A, market_id="m5"),
         row("draftkings", "player_rebounds", "Over", 6.5, 105, A, market_id="m6"),
         row("fanduel", "player_rebounds", "Over", 5.5, -130, A, market_id="f"),
         row("fanduel", "player_rebounds", "Under", 5.5, 100, A, st="under", market_id="f")]
    m = sharp.build_props("NBA", R)["props"]["ausarthompson"]
    assert "reb|3.5" not in m and "reb|1.5" not in m
    assert m["reb|4.5"] == -308 and m["reb|6.5"] == 105


def test_poisson_check_drops_a_rung_out_of_line():
    F = {"points|0.5": 0.724, "points|1.5": 0.106}     # Cale Makar: 1+ at -330, 2+ at +790
    assert sharp.poisson_drop(F) == ["points|1.5"]
    sane = {"sog|1.5": 0.72, "sog|2.5": 0.48, "sog|3.5": 0.27, "sog|4.5": 0.15}
    assert sharp.poisson_drop(sane) == []
