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
    dk = sharp._p(-105) / (sharp._p(-105) + sharp._p(-125)); fd = 0.5 / 1.06
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


def test_merge_keeps_draftkings_rungs_and_adds_missing_games():
    out = {"props": {"NHL": {"book": "DraftKings", "players": {"nathanmackinnon": {"points|1.5": -110, "points|2.5": 285}}}},
           "lines": {"NHL": {"games": [{"home": "Boston Bruins", "away": "Buffalo Sabres"}]}}}
    sh = {"NHL": {"fetched_at": "t", "complete": True, "props": {"nathanmackinnon": {"points|1.5": -105, "points|3.5": 900}},
                  "bk": {"nathanmackinnon": {"points|3.5": "FD", "points|2.5": "FD"}}, "fair": {"nathanmackinnon": {"points|1.5": 0.49}},
                  "games": [{"home": "New Jersey Devils", "away": "Colorado Avalanche"}, {"home": "Boston Bruins", "away": "Buffalo Sabres"}]}}
    odds.merge_sharp(out, sh, log=lambda *_: None)
    P = out["props"]["NHL"]
    assert P["players"]["nathanmackinnon"] == {"points|1.5": -110, "points|2.5": 285, "points|3.5": 900}   # ESPN DraftKings wins
    assert P["bk"] == {"nathanmackinnon": {"points|3.5": "FD"}} and P["book"] == "DraftKings + FanDuel"
    assert [g["home"] for g in out["lines"]["NHL"]["games"]] == ["Boston Bruins", "New Jersey Devils"]
