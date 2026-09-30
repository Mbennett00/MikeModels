import pandas as pd

from nhlmodel.data import moneypuck
from nhlmodel.data.nhl_api import parse_pbp, parse_starting_goalies


def _goal(period, ptype, owner, sc):
    return {"typeDescKey": "goal", "periodDescriptor": {"number": period, "periodType": ptype},
            "situationCode": sc, "details": {"eventOwnerTeamId": owner, "scoringPlayerId": 1}}


def test_parse_pbp_en_and_periods():
    js = {"id": 2024020001, "gameDate": "2024-10-10", "season": 20242025,
          "homeTeam": {"id": 6, "abbrev": "BOS", "score": 4}, "awayTeam": {"id": 10, "abbrev": "TOR", "score": 2},
          "gameOutcome": {"lastPeriodType": "REG"},
          "plays": [_goal(1, "REG", 6, "1551"), _goal(1, "REG", 10, "1541"), _goal(2, "REG", 6, "1551"),
                    _goal(3, "REG", 10, "1551"), _goal(3, "REG", 6, "1551"),
                    _goal(3, "REG", 6, "0651")]}   # away goalie pulled -> EN goal for home
    row, goals = parse_pbp(js)
    assert (row["home_reg_nonen"], row["away_reg_nonen"]) == (3, 2)
    assert row["home_en_reg"] == 1 and row["away_en_reg"] == 0
    assert (row["home_p1"], row["away_p1"]) == (1, 1)
    assert row["season"] == 2024 and sum(g["empty_net"] for g in goals) == 1


def test_starting_goalies():
    box = {"id": 1, "homeTeam": {"abbrev": "BOS"}, "awayTeam": {"abbrev": "TOR"},
           "playerByGameStats": {"homeTeam": {"goalies": [{"playerId": 5, "starter": True, "name": {"default": "X"}},
                                                          {"playerId": 6, "starter": False}]},
                                 "awayTeam": {"goalies": [{"playerId": 7, "starter": True}]}}}
    g = parse_starting_goalies(box)
    assert [x["player_id"] for x in g] == [5, 7]


def test_moneypuck_skaters_and_line_inference():
    rows = []
    for pid in range(12):
        for sit, toi in (("all", 1200 - pid * 40), ("5on5", 1000 - pid * 40), ("5on4", 120 if pid < 5 else 0),
                         ("4on5", 0)):
            rows.append({"gameId": 1, "playerId": pid, "name": f"p{pid}", "position": "C", "playerTeam": "BOS",
                         "opposingTeam": "TOR", "home_or_away": "HOME", "gameDate": 20241010, "season": 2024,
                         "situation": sit, "icetime": toi, "I_F_xGoals": 0.1, "I_F_goals": 0,
                         "I_F_shotsOnGoal": 1, "I_F_primaryAssists": 0, "I_F_secondaryAssists": 0})
    pg = moneypuck.player_games(pd.DataFrame(rows), None)
    assert set(pg.line) == {"F1", "F2", "F3", "F4"}
    assert pg.set_index("player_id").loc[0, "line"] == "F1"
    assert (pg.pp_unit == 1).sum() == 5
    assert pg.toi_5v5.iloc[0] > 0
