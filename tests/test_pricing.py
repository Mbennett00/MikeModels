import pytest

from nhlmodel import pricing as pr


def test_fair_odds_formula():
    assert pr.fair_american(0.6) == pytest.approx(-150)
    assert pr.fair_american(0.25) == pytest.approx(300)
    assert pr.fair_american(0.5) == pytest.approx(-100)


def test_roundtrip():
    for p in (0.1, 0.33, 0.5, 0.71):
        assert pr.american_to_prob(pr.fair_american(p)) == pytest.approx(p)


def test_novig_two_way_sums_to_one():
    a, b = pr.novig_two_way(-120, 100)
    assert a + b == pytest.approx(1)
    assert a > b


def test_one_sided_hold_is_conservative():
    raw = pr.american_to_prob(+400)
    nv = pr.novig_one_sided(+400, 0.05)
    assert nv < raw and nv == pytest.approx(raw / 1.05)


def test_edge_and_ev():
    assert pr.edge(0.55, 0.5) == pytest.approx(0.05)
    assert pr.expected_value(0.5, +100) == pytest.approx(0)


def test_stray_alternate_totals_are_dropped():
    import pandas as pd
    from nhlmodel.book import novig_table
    from nhlmodel.config import DEFAULT
    rows = []
    for b in range(9):   # main line 5.5 at all nine books
        rows += [dict(book=f"b{b}", selection="over", line=5.5, price=-109), dict(book=f"b{b}", selection="under", line=5.5, price=-111)]
    for b in range(4):   # four books with an off 4.5 (the 2026-10-04 UTA@NYR case)
        rows += [dict(book=f"b{b}", selection="over", line=4.5, price=-126), dict(book=f"b{b}", selection="under", line=4.5, price=104)]
    for b in range(6):   # a real alternate most books carry
        rows += [dict(book=f"b{b}", selection="over", line=6.5, price=150), dict(book=f"b{b}", selection="under", line=6.5, price=-180)]
    o = pd.DataFrame(rows).assign(game_id=1, market="total", player_id=None, snapshot="bet", date="2026-10-04")
    out = novig_table(o, DEFAULT, "bet")
    assert sorted(out.line.unique()) == [5.5, 6.5]


def test_espn_props_parse_one_sided_markets_only():
    from nhlmodel.espn_props import parse
    ref = lambda i: {"$ref": f"http://sports.core.api.espn.com/v2/sports/hockey/leagues/nhl/seasons/2027/athletes/{i}?lang=en"}
    items = [
        {"athlete": ref(1), "type": {"name": "Anytime Goalscorer"}, "odds": {"american": {"value": "+550"}}},
        {"athlete": ref(1), "type": {"name": "Shots on Goal Milestones"}, "odds": {"american": {"value": "-110"}}, "current": {"target": {"value": 3.0}}},
        {"athlete": ref(1), "type": {"name": "Points Milestones"}, "odds": {"american": {"value": "EVEN"}}, "current": {"target": {"value": 1.0}}},   # points / assists dropped
        {"athlete": ref(1), "type": {"name": "Total Points"}, "odds": {"american": {"value": "+150"}}, "current": {"target": {"value": 0.5}}},   # two-sided: skipped
        {"athlete": ref(9), "type": {"name": "Anytime Goalscorer"}, "odds": {"american": {"value": "+300"}}},   # not on a roster we know
    ]
    out = parse(items, {"1": "jackhughes"})
    assert out == {"jackhughes": {"goals|0.5": 550, "sog|2.5": -110}}
