"""The game simulators' data builders: league tables, team and player profiles from play-by-play and shot tables."""
import json
import os

import numpy as np
import pandas as pd

from nflmodel import simdata as nflsim
from nhlmodel import simdata as nhlsim


def _nfl_plays(n=6000, seed=1):
    rng = np.random.default_rng(seed)
    teams = ["IND", "WAS", "BUF", "NE"]
    pos = rng.choice(teams, n)
    dfn = np.array([teams[(teams.index(t) + 1) % 4] for t in pos])
    kind = rng.choice(["pass", "run", "punt", "field_goal", "kickoff", "extra_point"], n, p=[.5, .38, .04, .03, .03, .02])
    sack = (kind == "pass") & (rng.random(n) < .065)
    comp = (kind == "pass") & ~sack & (rng.random(n) < .64)
    ryds = np.where(kind == "run", np.round(rng.gamma(1.5, 3, n) - 1), np.nan)
    pyds = np.where(comp, np.round(rng.gamma(2, 5.5, n)), np.where(kind == "pass", 0, np.nan))
    d = pd.DataFrame(dict(
        game_id=[f"2026_{1 + i // 150:02d}_X" for i in range(n)], season=np.where(np.arange(n) < n // 3, 2025, 2026), week=1 + (np.arange(n) // 1000),
        season_type="REG", posteam=pos, defteam=dfn, home_team=pos, away_team=dfn, play_id=np.arange(n), qtr=rng.integers(1, 5, n), down=rng.integers(1, 5, n).astype(float),
        ydstogo=rng.integers(1, 15, n), yardline_100=rng.integers(1, 99, n), game_seconds_remaining=3600 - (np.arange(n) % 150) * 24, half_seconds_remaining=1800 - (np.arange(n) % 75) * 24,
        score_differential=rng.integers(-14, 15, n), wp=rng.random(n), play_type=kind, qb_dropback=(kind == "pass").astype(float), qb_scramble=((kind == "run") & (rng.random(n) < .05)).astype(float),
        qb_kneel=0.0, qb_spike=0.0, sack=sack.astype(float), interception=((kind == "pass") & ~sack & ~comp & (rng.random(n) < .06)).astype(float),
        fumble_lost=(rng.random(n) < .006).astype(float), complete_pass=comp.astype(float), pass_attempt=(kind == "pass").astype(float), rush_attempt=(kind == "run").astype(float),
        air_yards=np.where(kind == "pass", rng.normal(8, 9, n), np.nan), yards_after_catch=np.where(comp, rng.gamma(1.4, 4, n), np.nan),
        yards_gained=np.where(sack, -7, np.nan_to_num(ryds) + np.nan_to_num(pyds)), passing_yards=pyds, rushing_yards=ryds, receiving_yards=pyds,
        pass_oe=rng.normal(0, 30, n), no_huddle=0.0, penalty=(rng.random(n) < .05).astype(float), penalty_team=pos, penalty_type=rng.choice(["False Start", "Offensive Holding", "Defensive Pass Interference"], n),
        penalty_yards=10.0, first_down_penalty=0.0, third_down_converted=(rng.random(n) < .15).astype(float), third_down_failed=(rng.random(n) < .2).astype(float),
        field_goal_attempt=(kind == "field_goal").astype(float), field_goal_result=np.where(rng.random(n) < .85, "made", "missed"), kick_distance=np.where(kind == "field_goal", rng.integers(20, 58, n), np.where(kind == "punt", rng.integers(30, 60, n), np.nan)),
        extra_point_attempt=(kind == "extra_point").astype(float), extra_point_result="good", two_point_attempt=0.0, two_point_conv_result=None, touchdown=(rng.random(n) < .03).astype(float),
        punt_attempt=(kind == "punt").astype(float), kickoff_attempt=(kind == "kickoff").astype(float), touchback=(rng.random(n) < .3).astype(float), return_yards=rng.integers(0, 40, n).astype(float),
        punt_fair_catch=0.0, punt_inside_twenty=0.0, kicker_player_name="K.Kicker", punter_player_name="P.Punter", kickoff_returner_player_name="R.Returner", punt_returner_player_name="R.Returner",
        passer_player_id="QB1", rusher_player_id=np.where(kind == "run", "RB1", None), receiver_player_id=np.where(kind == "pass", rng.choice(["WR1", "WR2"], n), None),
        solo_tackle_1_player_name=rng.choice(["D.One", "D.Two", "D.Three"], n), solo_tackle_2_player_name=None, assist_tackle_1_player_name=None, assist_tackle_2_player_name=None,
        tackle_with_assist_1_player_name=None, tackle_with_assist_2_player_name=None, sack_player_name=np.where(sack, "D.One", None), half_sack_1_player_name=None, half_sack_2_player_name=None,
        interception_player_name=None, pass_defense_1_player_name=None, pass_defense_2_player_name=None, qb_hit_1_player_name=None,
        fixed_drive=np.arange(n) // 6, fixed_drive_result=rng.choice(["Touchdown", "Field goal", "Punt"], n), drive_inside20=(rng.random(n) < .3).astype(float),
        home_coach="Coach H", away_coach="Coach A", timeout=0.0, two_point=0))
    return d


def test_nfl_build_profiles_are_sane():
    out = nflsim.clean(nflsim.build(_nfl_plays(), 2026))
    L = out["league"]
    assert .02 < L["rates"]["sack"] < .15 and .5 < L["rates"]["cmp"] < .8
    assert L["fg"]["b"] < 0                                   # longer kicks miss more
    assert len(L["q"]["run"]) == len(L["qp"]) and L["q"]["run"] == sorted(L["q"]["run"])
    assert L["pass_dd"] and all(0 <= v <= 1 for v in L["pass_dd"].values())
    t = out["teams"]["IND"]
    assert {"o", "d", "defs", "k", "p"} <= set(t) and t["k"]["name"] == "K.Kicker"
    assert all(.3 < t["o"][k] < 3 for k in ("sack", "int", "cmp", "ypa", "ypc"))
    assert abs(sum(d[1] for d in t["defs"]) - 1) < .01        # tackle shares add up
    assert "QB1" in out["players"] and "scr" in out["players"]["QB1"]
    json.dumps(out)                                           # JSON-safe (no NaN)


def test_nhl_build_profiles_are_sane(tmp_path):
    rng = np.random.default_rng(2)
    games = pd.DataFrame(dict(game_id=range(1, 41), date="2026-10-10", season=[2025] * 20 + [2026] * 20, home="TOR", away="MTL",
                              home_reg_nonen=2, away_reg_nonen=2, home_en_reg=0, away_en_reg=0, home_final=3, away_final=2, decision="REG", home_p1=1, away_p1=0))
    n = 4000
    team = rng.choice(["TOR", "MTL"], n)
    shots = pd.DataFrame(dict(game_id=rng.integers(1, 41, n), season=2026, team=team, is_home=(team == "TOR").astype(int), shooter=np.where(team == "TOR", rng.choice([11, 12, 13], n), rng.choice([21, 22], n)),
                              t=rng.integers(0, 1200, n), period=rng.integers(1, 4, n), period_type="REG", x=rng.integers(-99, 99, n), y=rng.integers(-40, 40, n),
                              shot_type=rng.choice(["wrist", "snap", "slap", "tip-in"], n), strength=rng.choice(["5v5", "pp", "pk"], n, p=[.8, .15, .05]), en_target=False,
                              goal=rng.random(n) < .05, on_goal=rng.random(n) < .5, unblocked=rng.random(n) < .75, rebound=rng.random(n) < .1, lead=0, goalie=np.where(team == "TOR", 99, 98)))
    shots.loc[shots.goal, "on_goal"] = True
    goals = pd.DataFrame(dict(game_id=[1, 2], team="TOR", scorer=[11, 12], a1=[12, 11], a2=[13, np.nan], strength="5v5", en_target=False, period_type="REG"))
    pens = pd.DataFrame(dict(game_id=rng.integers(1, 41, 120), team=rng.choice(["TOR", "MTL"], 120), t=1))
    ptoi = pd.DataFrame([dict(game_id=g, player_id=p, team="TOR" if p < 20 else "MTL", all=18.0, **{"5v5": 15.0, "pp": 2.0, "pk": 1.0}) for g in range(1, 41) for p in (11, 12, 13, 21, 22)])
    ttoi = pd.DataFrame([dict(game_id=g, team=t, toi_all=60.0, toi_5v5=50.0, toi_pp=5.0, toi_pk=5.0) for g in range(1, 41) for t in ("TOR", "MTL")])
    gtoi = pd.DataFrame([dict(game_id=g, player_id=pid, team=t, toi=60.0, starter=True) for g in range(1, 41) for pid, t in ((99, "TOR"), (98, "MTL"))])
    roster = pd.DataFrame([dict(game_id=1, player_id=p, team="TOR" if p < 20 or p == 99 else "MTL", name=f"P{p}", pos_code="G" if p > 90 else "C") for p in (11, 12, 13, 21, 22, 98, 99)])
    for name, d in dict(games=games, shots=shots, goals=goals, penalties=pens, player_toi=ptoi, team_toi=ttoi, goalie_toi=gtoi, roster=roster).items():
        d.to_csv(os.path.join(tmp_path, f"{name}.csv.gz"), index=False)
    out = nhlsim.clean(nhlsim.build(str(tmp_path), 2026))
    L = out["league"]
    assert set(L["xg"]["tab"]) >= {"wrist", "snap"} and abs(L["att"]["on"] + L["att"]["blocked"] + L["att"]["miss"] - 1) < 1e-6
    assert {"TOR", "MTL"} <= set(out["teams"]) and all(.3 < out["teams"]["TOR"][k] < 3 for k in ("cf60", "ca60", "on", "blk"))
    p = out["players"]["11"]
    assert p["pos"] == "C" and len(p["toi"]) == 3 and p["loc"] and p["ast"] == {"12": 1, "13": 1}
    assert "99" in out["goalies"] and 0 < out["goalies"]["99"]["sv"] < 1
    json.dumps(out)
