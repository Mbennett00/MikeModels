"""calib.odds: matching market lines to page games, carrying the last good odds."""
import datetime as dt
import json

from calib import odds


def test_market_games_attach_to_page_ids(tmp_path):
    (tmp_path / "data.json").write_text(json.dumps({"games": [
        {"game_id": 2026020022, "start_utc": "2026-10-20T23:00:00Z", "home": {"abbr": "BOS", "name": "Bruins"}, "away": {"abbr": "BUF", "name": "Sabres"}}]}))
    lines = {"NHL": {"games": [{"home": "Boston Bruins", "away": "Buffalo Sabres", "t": "2026-10-20T23:10:00Z"},
                               {"home": "Boston Bruins", "away": "Buffalo Sabres", "t": "2026-11-20T23:10:00Z"}]}}
    odds.attach_gids(lines, str(tmp_path), log=lambda *_: None)
    assert lines["NHL"]["games"][0]["gid"] == "2026020022" and "gid" not in lines["NHL"]["games"][1]   # a month later is another game


def test_run_keeps_recent_props_and_future_lines(tmp_path, monkeypatch):
    site = tmp_path / "site"; site.mkdir()
    now = dt.datetime.now(dt.timezone.utc)
    t = lambda h: (now + dt.timedelta(hours=h)).isoformat(timespec="seconds")
    (site / "odds.json").write_text(json.dumps({
        "lines": {"NHL": {"games": [{"home": "A", "away": "B", "t": t(-1)}, {"home": "C", "away": "D", "t": t(5)}]}},
        "props": {"NHL": {"fetched_at": t(-2), "fair": {}, "players": {"x": {"goals|0.5": 200}}},
                  "NBA": {"fetched_at": t(-30), "fair": {}, "players": {"y": {"pts|9.5": 100}}},    # too old
                  "NFL": {"fetched_at": t(-1), "players": {"z": {"td|0.5": 150}}}}}))               # an old ESPN set: no fair
    from calib import sharp
    monkeypatch.setattr(sharp, "pull", lambda leagues, key, log: {})
    odds.run(str(tmp_path), log=lambda *_: None)
    out = json.loads((site / "odds.json").read_text())
    assert [g["home"] for g in out["lines"]["NHL"]["games"]] == ["C"]
    assert set(out["props"]) == {"NHL"}

