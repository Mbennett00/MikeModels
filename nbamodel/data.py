"""ESPN's free NBA feeds: schedule and scores, box scores, teams, rosters and injuries.

Everything is cached in the state folder, so a run only fetches what is new: recent days' scoreboards and box
scores of games that finished since the last run. Nothing here needs a key or costs credits.
"""
from __future__ import annotations

import datetime as dt
import time

import pandas as pd
import requests

SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
UA = {"User-Agent": "Mozilla/5.0 (Blitzed NBA model)"}
HEADSHOT = "https://a.espncdn.com/i/headshots/nba/players/full/{}.png"
ET = "America/New_York"
_S = requests.Session()
_S.headers.update(UA)


def _get(url: str, params: dict | None = None, tries: int = 3, timeout: int = 20) -> dict:
    for k in range(tries):
        try:
            r = _S.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r.json()
        except (requests.RequestException, ValueError):
            pass
        time.sleep(0.6 * (k + 1))
    return {}


def _team(c: dict) -> dict:
    t = c.get("team") or {}
    return dict(abbr=t.get("abbreviation", ""), name=t.get("shortDisplayName") or t.get("name", ""),
                city=t.get("location", ""), color="#" + (t.get("color") or "556070"), logo=t.get("logo", ""), espn_id=str(t.get("id", "")))


def parse_scoreboard(js: dict) -> list[dict]:
    """Scoreboard JSON -> one row per game."""
    out = []
    for ev in js.get("events", []):
        comp = (ev.get("competitions") or [{}])[0]
        side = {c.get("homeAway"): c for c in comp.get("competitors", [])}
        if "home" not in side or "away" not in side:
            continue
        st = (ev.get("status") or {}).get("type") or {}
        h, a = _team(side["home"]), _team(side["away"])
        start = pd.Timestamp(ev.get("date"))
        sc = lambda c: pd.to_numeric(c.get("score"), errors="coerce")
        out.append(dict(game_id=str(ev.get("id")), start_utc=start.isoformat(), date=str(start.tz_convert(ET).date()),
                        season_type=int((ev.get("season") or {}).get("type") or 2), season=int((ev.get("season") or {}).get("year") or 0),
                        state=st.get("state", "pre"), detail=st.get("shortDetail", ""), neutral=bool(comp.get("neutralSite")),
                        home=h["abbr"], away=a["abbr"], home_score=sc(side["home"]), away_score=sc(side["away"]),
                        home_name=h["name"], away_name=a["name"], home_city=h["city"], away_city=a["city"],
                        home_color=h["color"], away_color=a["color"], home_logo=h["logo"], away_logo=a["logo"],
                        home_tid=h["espn_id"], away_tid=a["espn_id"]))
    return out


def scoreboard(day: dt.date) -> list[dict]:
    return parse_scoreboard(_get(f"{SITE}/scoreboard", {"dates": day.strftime("%Y%m%d"), "limit": 50}))


def _num(v) -> float:
    try:
        return float(str(v).split("-")[0])
    except ValueError:
        return float("nan")


def parse_box(js: dict, game_id: str) -> list[dict]:
    """Game summary JSON -> one row per player who appeared (minutes, points, rebounds, assists, threes)."""
    rows = []
    for team in (js.get("boxscore") or {}).get("players", []):
        abbr = (team.get("team") or {}).get("abbreviation", "")
        for grp in team.get("statistics", []):
            labels = [str(x).upper() for x in grp.get("labels", [])]
            ix = {k: labels.index(k) for k in ("MIN", "PTS", "REB", "AST", "3PT") if k in labels}
            if "MIN" not in ix or "PTS" not in ix:
                continue
            for a in grp.get("athletes", []):
                ath, st = a.get("athlete") or {}, a.get("stats") or []
                if not st or a.get("didNotPlay"):
                    continue
                g = lambda k: _num(st[ix[k]]) if k in ix and ix[k] < len(st) else float("nan")
                mins = g("MIN")
                if not (mins > 0):
                    continue
                rows.append(dict(game_id=game_id, team=abbr, player_id=str(ath.get("id", "")), name=ath.get("displayName", ""),
                                 pos=(ath.get("position") or {}).get("abbreviation", ""), starter=bool(a.get("starter")),
                                 min=mins, pts=g("PTS"), reb=g("REB"), ast=g("AST"), fg3=g("3PT")))
    return rows


def box(game_id: str) -> list[dict]:
    return parse_box(_get(f"{SITE}/summary", {"event": game_id}), game_id)


def rosters(team_ids: dict) -> pd.DataFrame:
    """Current rosters (who plays where right now, after trades and signings): player_id, name, team, pos, headshot."""
    rows = []
    for abbr, tid in team_ids.items():
        js = _get(f"{SITE}/teams/{tid}/roster")
        for a in js.get("athletes", []):
            for p in (a.get("items", []) if isinstance(a, dict) and "items" in a else [a]):
                if not p.get("id"):
                    continue
                rows.append(dict(player_id=str(p["id"]), name=p.get("displayName") or p.get("fullName", ""), team=abbr,
                                 pos=(p.get("position") or {}).get("abbreviation", ""),
                                 headshot=((p.get("headshot") or {}).get("href")) or HEADSHOT.format(p["id"])))
    return pd.DataFrame(rows)


def injuries() -> pd.DataFrame:
    """League injury report: player_id, name, team, status (Out / Day-To-Day / ...), detail."""
    js, rows = _get(f"{SITE}/injuries"), []
    for t in js.get("injuries", []):
        abbr = ""
        for it in t.get("injuries", []):
            ath = it.get("athlete") or {}
            abbr = ((ath.get("team") or {}).get("abbreviation")) or abbr
            pid = str(ath.get("id") or "") or (ath.get("links") or [{}])[0].get("href", "").rstrip("/").split("/")[-1]
            rows.append(dict(player_id=pid, name=ath.get("displayName", ""), team=abbr, status=it.get("status", ""),
                             detail=(it.get("shortComment") or it.get("details", {}).get("type", "") if isinstance(it.get("details"), dict) else it.get("shortComment", "")) or ""))
    return pd.DataFrame(rows)
