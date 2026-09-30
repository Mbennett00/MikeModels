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
