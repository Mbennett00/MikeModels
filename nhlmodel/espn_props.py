"""DraftKings player-prop prices from ESPN's free API (no key), for tonight's NHL games.

ESPN's core odds feed blocks browsers (no CORS), so the slate run fetches it and publishes the prices with the page.
Only one-sided markets are used, so there is never a doubt about which side a price belongs to:
Anytime Goalscorer (= over 0.5 goals) and the Shots on Goal / Points / Assists milestones ("N+" = over N - 0.5).
"""
from __future__ import annotations

import datetime as dt
import re

import requests

from .data.teams import norm_name

UA = {"User-Agent": "Mozilla/5.0 (MikeModels odds)"}
SITE = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl"
CORE = "https://sports.core.api.espn.com/v2/sports/hockey/leagues/nhl"
TYPES = {"Anytime Goalscorer": "goals", "Shots on Goal Milestones": "sog", "Points Milestones": "points", "Assists Milestones": "assists"}
PROVIDER = "100"   # DraftKings


def _odds(v) -> int | None:
    s = str(v or "").strip().upper()
    if s in ("EVEN", "EV"):
        return 100
    try:
        x = int(float(s.replace("+", "")))
    except ValueError:
        return None
    return x if abs(x) >= 100 else None


def parse(items: list, names: dict) -> dict:
    """propBets items -> {normalised name: {"market|line": american odds}}."""
    out: dict = {}
    for it in items:
        mk = TYPES.get(((it.get("type") or {}).get("name") or "").strip())
        ref = (it.get("athlete") or {}).get("$ref", "")
        m = re.search(r"/athletes/(\d+)", ref)
        if not mk or not m or m.group(1) not in names:
            continue
        price = _odds(((it.get("odds") or {}).get("american") or {}).get("value"))
        if price is None:
            continue
        if mk == "goals":
            line = 0.5
        else:
            tgt = ((it.get("current") or {}).get("target") or {}).get("value")
            if tgt is None:
                continue
            line = float(tgt) - 0.5
        out.setdefault(names[m.group(1)], {})[f"{mk}|{line:g}"] = price
    return out


def fetch(date, log=print) -> dict:
    """Prices for every game on `date` (YYYY-MM-DD). Never raises: returns {} when ESPN is unavailable."""
    day = str(date).replace("-", "")[:8]
    try:
        sb = requests.get(f"{SITE}/scoreboard?dates={day}", headers=UA, timeout=20).json()
    except Exception as e:
        log(f"espn props: scoreboard failed ({e})")
        return {}
    names: dict = {}
    teams_done: set = set()
    out: dict = {}
    for ev in sb.get("events", []):
        comp = (ev.get("competitions") or [{}])[0]
        if ((ev.get("status") or {}).get("type") or {}).get("state") == "post":
            continue
        for c in comp.get("competitors", []):
            tid = (c.get("team") or {}).get("id")
            if not tid or tid in teams_done:
                continue
            teams_done.add(tid)
            try:
                rj = requests.get(f"{SITE}/teams/{tid}/roster", headers=UA, timeout=15).json()
                for g in rj.get("athletes", []):
                    for a in (g.get("items", []) if isinstance(g, dict) and "items" in g else [g]):
                        if a.get("id") and (a.get("fullName") or a.get("displayName")):
                            names[str(a["id"])] = norm_name(a.get("fullName") or a.get("displayName"))
            except Exception:
                continue
        eid = ev.get("id")
        try:
            pb = requests.get(f"{CORE}/events/{eid}/competitions/{eid}/odds/{PROVIDER}/propBets?limit=1000", headers=UA, timeout=25).json()
        except Exception as e:
            log(f"espn props: event {eid} failed ({e})")
            continue
        for k, v in parse(pb.get("items", []), names).items():
            out.setdefault(k, {}).update(v)
    log(f"espn props: DraftKings prices for {len(out)} players")
    return {"book": "DraftKings", "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "players": out}
