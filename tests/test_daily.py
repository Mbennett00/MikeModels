import pandas as pd

from nhlmodel.daily import log_flagged, projected_lineups


def test_projected_lineups_and_overrides(league, tmp_path):
    tables, _ = league
    day = pd.Timestamp("2024-12-10")
    sched = tables["games"][tables["games"].date == day][["game_id", "date", "home", "away"]]
    lu, roster = projected_lineups(tables, sched, None, day)
    assert not lu.confirmed.any()
    assert (lu.pos == "G").sum() == 2 * len(sched)
    team = sched.home.iloc[0]
    other_goalie = roster[(roster.team == team) & (roster.pos == "G")].name.iloc[-1]
    ov = pd.DataFrame([dict(team=team, goalie=other_goalie, lineup_confirmed=True)])
    lu2, _ = projected_lineups(tables, sched, ov, day)
    g = lu2[(lu2.team == team) & (lu2.pos == "G")]
    assert g.name.iloc[0] == other_goalie and g.confirmed.iloc[0]
    assert lu2[(lu2.team == team) & (lu2.pos != "G")].confirmed.all()
    assert not lu2[lu2.team != team].confirmed.any()


def test_bet_log_keeps_first_price(tmp_path):
    base = dict(game_id=1, market="sog", selection="over", line=2.5, player_id=9, matchup="A @ B", player="X",
                projection="3.1", p_model=0.6, fair_odds=-150, p_novig=0.5, edge=0.1, confidence="normal", flag=True)
    log_flagged(str(tmp_path), pd.DataFrame([dict(base, best_price=120)]), pd.Timestamp("2026-10-10"))
    log_flagged(str(tmp_path), pd.DataFrame([dict(base, best_price=105)]), pd.Timestamp("2026-10-10"))
    log = pd.read_csv(tmp_path / "bets_log.csv")
    assert len(log) == 1 and log.best_price.iloc[0] == 120
