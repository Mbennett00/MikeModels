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
    monkeypatch.setattr(sharp, "pull", lambda leagues, key, log, props=True: {})
    odds.run(str(tmp_path), log=lambda *_: None)
    out = json.loads((site / "odds.json").read_text())
    assert [g["home"] for g in out["lines"]["NHL"]["games"]] == ["C"]
    assert set(out["props"]) == {"NHL"}



def test_line_history_keeps_opener_and_moves_only():
    now = dt.datetime(2026, 10, 22, 15, 0, tzinfo=dt.timezone.utc)
    g = {"home": "Boston Celtics", "away": "New York Knicks", "t": "2026-10-22T23:30:00Z", "gid": "401",
         "spread": {"home": -3.5, "home_price": -110, "away_price": -110}, "total": {"line": 221.5, "over": -110, "under": -110},
         "ml": {"home": -160, "away": 135}}
    H = odds.update_hist({}, {"NBA": {"games": [g]}}, now)
    H = odds.update_hist(H, {"NBA": {"games": [g]}}, now + dt.timedelta(hours=1))                  # nothing moved
    g2 = dict(g, spread={"home": -4.5, "home_price": -105, "away_price": -115})
    H = odds.update_hist(H, {"NBA": {"games": [g2]}}, now + dt.timedelta(hours=2))
    e = next(iter(H["NBA"].values()))
    assert e["gid"] == "401" and len(e["s"]) == 2
    assert e["s"][0][1] == -3.5 and e["s"][-1][1] == -4.5 and e["seen"] == e["s"][-1][0]
    late = now + dt.timedelta(hours=9)                                                             # started: no new snapshot
    H = odds.update_hist(H, {"NBA": {"games": [dict(g, spread={"home": -6.5, "home_price": -110, "away_price": -110})]}}, late)
    assert next(iter(H["NBA"].values()))["s"][-1][1] == -4.5
    assert odds.update_hist(H, {}, now + dt.timedelta(days=3)) == {}                                 # old games drop off
