"""calib.odds: consensus lines and the monthly credit cap."""
import json

from calib import odds


def _book(key, h, a, sp, sph, spa, tot, o, u):
    return {"key": key, "markets": [
        {"key": "h2h", "outcomes": [{"name": "Boston Bruins", "price": h}, {"name": "Buffalo Sabres", "price": a}]},
        {"key": "spreads", "outcomes": [{"name": "Boston Bruins", "price": sph, "point": sp}, {"name": "Buffalo Sabres", "price": spa, "point": -sp}]},
        {"key": "totals", "outcomes": [{"name": "Over", "price": o, "point": tot}, {"name": "Under", "price": u, "point": tot}]}]}


EV = {"home_team": "Boston Bruins", "away_team": "Buffalo Sabres", "commence_time": "2026-10-20T23:00:00Z", "bookmakers": [
    _book("dk", -150, 130, -1.5, 160, -190, 6.5, 105, -125),
    _book("fd", -145, 125, -1.5, 165, -200, 6.5, 100, -120),
    _book("mgm", -155, 135, -1.5, 155, -185, 5.5, -140, 120)]}


def test_prop_markets_map_to_page_stats():
    k = odds.prop_kind
    assert k("NBA", "Points Milestones") == ("pts", False)
    assert k("NBA", "Points + Rebounds + Assists Milestones") == ("pra", False)
    assert k("NBA", "Rebounds + Assists Milestones") is None          # no such stat on the page
    assert k("NBA", "Total Points") is None                           # two-way over/under: skipped
    assert k("NFL", "Anytime Touchdown Scorer") == ("td", True)
    assert k("NFL", "Rushing + Receiving Yards Milestones") is None
    assert k("NHL", "Anytime Goalscorer") == ("goals", True)
    assert k("NHL", "Shots on Goal Milestones") == ("sog", False)
    assert k("NHL", "Points Milestones") == ("points", False)
    for other in ("Power Play Points Milestones", "Blocked Shots Milestones", "Shorthanded Points Milestones", "Saves Milestones", "Team Total Points Milestones"):
        assert k("NHL", other) is None, other                          # same keyword, different stat (MacKinnon "2+ points" came out +850)


def test_market_games_attach_to_page_ids(tmp_path):
    (tmp_path / "data.json").write_text(json.dumps({"games": [
        {"game_id": 2026020022, "start_utc": "2026-10-20T23:00:00Z", "home": {"abbr": "BOS", "name": "Bruins"}, "away": {"abbr": "BUF", "name": "Sabres"}}]}))
    lines = {"NHL": {"games": [{"home": "Boston Bruins", "away": "Buffalo Sabres", "t": "2026-10-20T23:10:00Z"},
                               {"home": "Boston Bruins", "away": "Buffalo Sabres", "t": "2026-11-20T23:10:00Z"}]}}
    odds.attach_gids(lines, str(tmp_path), log=lambda *_: None)
    assert lines["NHL"]["games"][0]["gid"] == "2026020022" and "gid" not in lines["NHL"]["games"][1]   # a month later is another game


def test_nhl_two_goal_market():
    assert odds.prop_kind("NHL", "To Score 2+ Goals") == ("goals", 1.5)
    assert odds.prop_kind("NHL", "First Goalscorer") is None
