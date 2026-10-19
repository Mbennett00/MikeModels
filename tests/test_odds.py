"""calib.odds: consensus lines and the monthly credit cap."""
import datetime as dt
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


def test_consensus_takes_the_common_line_and_median_price():
    c = odds.consensus(EV)
    assert c["books"] == 3 and c["home"] == "Boston Bruins"
    assert c["ml"]["home"] == -150 and c["ml"]["away"] == 130
    assert c["spread"]["home"] == -1.5 and c["spread"]["home_price"] == 160
    assert c["total"]["line"] == 6.5                      # two books hang 6.5, one 5.5
    assert c["total"]["over"] in (102, 103) and c["total"]["under"] in (-122, -123)


def test_cap_skips_paid_pulls(tmp_path, monkeypatch):
    web = tmp_path / "web"; web.mkdir()
    soon = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5)).isoformat()
    for f in ("data.json", "nba.json", "nfl.json"):
        (web / f).write_text(json.dumps({"games": [{"start_utc": soon}]}))
    calls = []
    monkeypatch.setenv("ODDS_PULL", "1")                   # inside the pull window
    monkeypatch.setattr(odds, "usage", lambda key: 478)
    monkeypatch.setattr(odds.requests, "get", lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(AssertionError("paid call")))
    out = odds.pull_lines({}, str(web), "KEY", log=lambda *_: None)
    assert calls == [] and out["lines"] == {}              # 478 + 3 > 480: nothing pulled


def test_recent_pull_is_not_repeated(tmp_path, monkeypatch):
    web = tmp_path / "web"; web.mkdir()
    soon = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5)).isoformat()
    (web / "nba.json").write_text(json.dumps({"games": [{"start_utc": soon}]}))
    monkeypatch.setattr(odds, "usage", lambda key: (_ for _ in ()).throw(AssertionError("no usage check needed")))
    prev = {"pulled": {"NBA": dt.datetime.now(dt.timezone.utc).isoformat()}, "lines": {"NBA": {"games": []}}}
    out = odds.pull_lines(prev, str(web), "KEY", log=lambda *_: None)
    assert out["lines"] == prev["lines"]


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


class _R:
    def __init__(self, data, used=200):
        self._d, self.headers, self.ok = data, {"x-requests-used": str(used)}, True
    def json(self):
        return self._d
    def raise_for_status(self):
        pass


def test_nfl_props_once_per_game_over_sides_only(monkeypatch):
    soon = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=30)).isoformat().replace("+00:00", "Z")
    late = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=6)).isoformat().replace("+00:00", "Z")
    events = [{"id": "e1", "commence_time": soon, "home_team": "Cleveland Browns", "away_team": "Pittsburgh Steelers"},
              {"id": "e2", "commence_time": late, "home_team": "A", "away_team": "B"}]       # too far out
    odds_e1 = {"bookmakers": [{"key": "draftkings", "markets": [
        {"key": "player_anytime_td", "outcomes": [{"name": "Yes", "description": "Jaylen Warren", "price": 160}, {"name": "No", "description": "Jaylen Warren", "price": -220}]},
        {"key": "player_rush_yds", "outcomes": [{"name": "Over", "description": "Jaylen Warren", "price": -115, "point": 58.5}, {"name": "Under", "description": "Jaylen Warren", "price": -105, "point": 58.5}]}]}]}
    calls = []
    def get(url, params=None, timeout=None):
        calls.append(url)
        return _R(events) if url.endswith("/events") else _R(odds_e1, used=203)
    monkeypatch.setenv("ODDS_PULL", "1")
    monkeypatch.setattr(odds.requests, "get", get)
    st, players, used = odds.pull_nfl_props({}, "KEY", 200, log=lambda *_: None)
    assert players == {"jaylenwarren": {"td|0.5": 160, "rush_yds|58.5": -115}} and used == 203
    assert sum("/events/e1/odds" in c for c in calls) == 1 and not any("e2/odds" in c for c in calls)
    calls.clear()
    st2, players2, _ = odds.pull_nfl_props({"nflp": st}, "KEY", 203, log=lambda *_: None)
    assert players2 == players and not any("/odds" in c for c in calls)           # already pulled: no second charge
