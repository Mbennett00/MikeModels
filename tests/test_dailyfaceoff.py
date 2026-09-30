import pandas as pd

from nhlmodel.daily import projected_lineups
from nhlmodel.data import dailyfaceoff as dfo


def _goalies_js():
    return {"props": {"pageProps": {"data": [
        {"homeTeamSlug": "toronto-maple-leafs", "homeGoalieName": "Anthony Stolarz", "homeNewsStrengthName": "Confirmed",
         "homeNewsDetails": "Stolarz will start.", "awayTeamSlug": "new-york-islanders", "awayGoalieName": "Ilya Sorokin",
         "awayNewsStrengthName": "Likely", "awayNewsDetails": "", "dateGmt": "2026-09-30T23:30:00.000Z"}]}}}


def test_parse_goalies():
    rows = dfo.parse_goalies(_goalies_js())
    by = {r["team"]: r for r in rows}
    assert by["TOR"]["status"] == "Confirmed" and by["NYI"]["goalie"] == "Ilya Sorokin"
    assert dfo.ABBR["utah-mammoth"] == "UTA"


def _lines_js_from(tables, team, day):
    lu = tables["lineups"]
    last = lu[(lu.team == team) & (lu.date < day)]
    last = last[last.date == last.date.max()]
    players = []
    for r in last[last.pos != "G"].itertuples():
        players.append({"name": r.name, "categoryIdentifier": "ev", "groupIdentifier": r.line.lower(),
                        "positionIdentifier": "c", "injuryStatus": None, "gameTimeDecision": False})
        if r.pp_unit:
            players.append({"name": r.name, "categoryIdentifier": "pp", "groupIdentifier": f"pp{r.pp_unit}",
                            "positionIdentifier": "sk1", "injuryStatus": None, "gameTimeDecision": False})
    g = last[last.pos == "G"]
    players.append({"name": g.name.iloc[0], "categoryIdentifier": "ev", "groupIdentifier": "g",
                    "positionIdentifier": "g1", "injuryStatus": None, "gameTimeDecision": False})
    players.append({"name": "Hurt Guy", "categoryIdentifier": "oi", "groupIdentifier": "ir",
                    "positionIdentifier": "ir1", "injuryStatus": "out", "gameTimeDecision": False})
    return {"props": {"pageProps": {"combinations": {"players": players}}}}


def test_dfo_lineup_is_used_and_confirmed_follows_goalie(league):
    tables, _ = league
    day = pd.Timestamp("2024-12-10")
    g = tables["games"][tables["games"].date == day].iloc[0]
    sched = pd.DataFrame([dict(game_id=g.game_id, date=day, home=g.home, away=g.away)])
    lu = tables["lineups"]
    ros = []
    for t in (g.home, g.away):
        last = lu[(lu.team == t) & (lu.date < day)]
        ros.append(last[["team", "player_id", "name", "pos"]].drop_duplicates("player_id"))
    ros = pd.concat(ros).assign(headshot="")
    lines = dfo.parse_lines(_lines_js_from(tables, g.home, day), g.home)
    home_g = [r["name"] for r in lines if r["slot"] == "g1"][0]
    data = {"goalies": [dict(team=g.home, goalie=home_g, status="Confirmed", note="", updated=None, start_utc=None)],
            "lines": lines}
    out, _ = projected_lineups(tables, sched, None, day, ros, data)
    home = out[out.team == g.home]
    assert (home.source == "Daily Faceoff").all()
    assert home.confirmed.all()                        # confirmed goalie => team confirmed
    assert (home.pos == "G").sum() == 1 and home[home.pos == "G"].status.iloc[0] == "Confirmed"
    assert "Hurt Guy" not in set(home.name)
    assert set(home[home.pos == "F"].line) == {"F1", "F2", "F3", "F4"}
    away = out[out.team == g.away]
    assert "source" not in away or away.source.isna().all() or not (away.source == "Daily Faceoff").any()
    assert not away.confirmed.any()                    # no DFO data for the away team => projection
