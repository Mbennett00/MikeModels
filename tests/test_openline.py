from calib.openline import carry


def test_first_sighting_opens_at_current_price():
    new = [{"game_id": 1, "dk": [{"m": "moneyline", "s": "home", "l": None, "price": -120}]}]
    assert carry(new, None) == 0
    assert new[0]["dk"][0]["op"] == -120


def test_carries_the_opening_price_through_later_runs():
    run1 = [{"game_id": 1, "dk": [{"m": "total", "s": "over", "l": 6.5, "price": -110}]}]
    carry(run1, None)
    run2 = [{"game_id": 1, "dk": [{"m": "total", "s": "over", "l": 6.5, "price": -125}]}]
    assert carry(run2, run1) == 1
    run3 = [{"game_id": 1, "dk": [{"m": "total", "s": "over", "l": 5.5, "price": +105}]}]
    carry(run3, run2)
    x = run3[0]["dk"][0]
    assert (x["op"], x["ol"]) == (-110, 6.5)


def test_nfl_shape_uses_its_line_key():
    old = [{"game_id": "g", "bets": [{"m": "spread", "s": "home", "line": -3.0, "price": -110}]}]
    carry(old, None, field="bets", line_key="line")
    new = [{"game_id": "g", "bets": [{"m": "spread", "s": "home", "line": -3.5, "price": -105}]}]
    carry(new, old, field="bets", line_key="line")
    assert (new[0]["bets"][0]["op"], new[0]["bets"][0]["ol"]) == (-110, -3.0)
