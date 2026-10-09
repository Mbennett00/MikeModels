from nflmodel.espn_props import parse, market


def test_market_names():
    assert market("Anytime Touchdown Scorer") == ("td", True)
    assert market("Receiving Yards Milestones") == ("rec_yds", True)
    assert market("Total Passing Yards") == ("pass_yds", False)
    assert market("Rushing + Receiving Yards") == (None, False)
    assert market("Longest Rush") == (None, False)


def test_parse_one_sided_and_sided_totals():
    ref = lambda i: {"$ref": f"http://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/2026/athletes/{i}?lang=en"}
    items = [
        {"athlete": ref(1), "type": {"name": "Anytime Touchdown Scorer"}, "odds": {"american": {"value": "+120"}}},
        {"athlete": ref(1), "type": {"name": "Receiving Yards Milestones"}, "odds": {"american": {"value": "-150"}}, "current": {"target": {"value": 50}}},
        {"athlete": ref(1), "type": {"name": "Total Receptions"}, "odds": {"over": {"american": {"value": "-115"}}, "under": {"american": {"value": "-105"}}}, "current": {"target": {"value": 4.5}}},
        {"athlete": ref(1), "type": {"name": "Total Rushing Yards"}, "odds": {"american": {"value": "-110"}}, "current": {"target": {"value": 9.5}}},   # side unknown: skipped
        {"athlete": ref(7), "type": {"name": "Anytime Touchdown Scorer"}, "odds": {"american": {"value": "+300"}}},   # not on a roster we know
    ]
    out = parse(items, {"1": "jamarrchase"})
    assert out == {"jamarrchase": {"td|0.5": {"o": 120, "n": 1, "best": 120, "src": "DK"}, "rec_yds|49.5": {"o": -150}, "rec|4.5": {"o": -115, "u": -105}}}
