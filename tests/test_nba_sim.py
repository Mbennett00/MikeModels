import pandas as pd

from nbamodel import simdata

LAB = ["MIN", "PTS", "FG", "3PT", "FT", "REB", "AST", "TO", "STL", "BLK", "OREB", "DREB", "PF", "+/-"]


def summary(h, a, hs, as_):
    def team(ab, base):
        ath = [{"athlete": {"id": f"{ab}{i}", "displayName": f"{ab} P{i}"}, "starter": i < 5,
                "stats": ["30", str(base + i), "8-17", "2-6", "3-4", "6", "4", "2", "1", "1", "1", "5", "2", "+3"]} for i in range(8)]
        ath.append({"athlete": {"id": f"{ab}dnp", "displayName": "DNP"}, "didNotPlay": True, "stats": []})
        return {"team": {"abbreviation": ab}, "statistics": [{"labels": LAB, "athletes": ath}]}
    return {"boxscore": {"players": [team(h, hs), team(a, as_)]}}


def test_parse_and_build_rates():
    rows = simdata.parse_full(summary("BOS", "NY", 10, 8))
    assert len(rows) == 16 and rows[0]["fgm"] == 8 and rows[0]["fga"] == 17 and rows[0]["tpa"] == 6 and rows[0]["oreb"] == 1
    G = pd.DataFrame([dict(game_id=str(i), home="BOS", away="NY", season_type=2, date=f"2026-01-{i + 1:02d}") for i in range(12)])
    cache = {str(i): simdata.parse_full(summary("BOS", "NY", 10, 8)) for i in range(12)}
    out = simdata.build(G, cache, 2027)
    L = out["league"]
    assert abs(L["three"] - 6 / 17) < 1e-3 and abs(L["fg2"] - 6 / 11) < 1e-3 and abs(L["ft"] - .75) < 1e-3
    assert abs(L["pace"] - (8 * 17 + .44 * 8 * 4 - 8 + 16)) < .05 and set(out["teams"]) == {"BOS", "NY"}   # possessions per 48
    p = out["players"]["BOS0"]
    assert p["f3a"] == round(36 * 6 / 30, 2) and p["start"] == 1.0 and abs(out["teams"]["BOS"]["fg2"] - 1) < 1e-6
