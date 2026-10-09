"""DraftKings NFL player-prop prices from ESPN's free API (no key, no Odds API credits).

Same feed as nhlmodel.espn_props: the slate run fetches it (ESPN blocks browsers) and publishes the prices with
the page. One-sided markets are always safe to read: Anytime TD (= over 0.5) and the yardage / receptions
milestones ("N+" = over N - 0.5). A two-sided "Total ..." market is used only when the item names its side.
"""
from __future__ import annotations

import datetime as dt
import re
from collections import Counter

import requests

UA = {"User-Agent": "Mozilla/5.0 (MikeModels odds)"}
SITE = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
CORE = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl"
PROVIDER = "100"   # DraftKings
ESPN_TEAM = {"WSH": "WAS", "LAR": "LA"}   # ESPN abbreviation -> nflverse
STATS = [("receiving yards", "rec_yds"), ("rushing yards", "rush_yds"), ("passing yards", "pass_yds"), ("receptions", "rec")]


def _odds(v) -> int | None:
    s = str(v or "").strip().upper()
    if s in ("EVEN", "EV"):
        return 100
    try:
        x = int(float(s.replace("+", "")))
    except ValueError:
        return None
    return x if abs(x) >= 100 else None


def market(type_name: str) -> tuple[str | None, bool]:
    """ESPN prop type -> (market, one_sided)."""
    t = type_name.lower()
    if "anytime" in t and "touchdown" in t:
        return "td", True
    if "+" in t or " and " in t or "longest" in t or "quarter" in t or "half" in t:
        return None, False          # combos (rush + rec), longest-play and period markets are not modelled
    for words, mk in STATS:
        if words in t:
            if "milestone" in t:
                return mk, True
            if t.startswith("total") or t == words or "over/under" in t:
                return mk, False
    return None, False


def _side_prices(it: dict) -> dict:
    """Over / under prices for a two-sided item, when the item says which is which."""
    od = it.get("odds") or {}
    out = {}
    for side, key in (("over", "o"), ("under", "u")):
        v = od.get(side)
        if isinstance(v, dict):
            p = _odds((v.get("american") or {}).get("value") if isinstance(v.get("american"), dict) else v.get("american") or v.get("value"))
            if p is not None:
                out[key] = p
    return out


def parse(items: list, names: dict, seen: Counter | None = None) -> dict:
    """propBets items -> {normalised name: {"market|line": {"o": over, "u": under}}} (DraftKings)."""
    out: dict = {}
    for it in items:
        tname = ((it.get("type") or {}).get("name") or "").strip()
        if seen is not None:
            seen[tname] += 1
        mk, one = market(tname)
        ref = (it.get("athlete") or {}).get("$ref", "")
        m = re.search(r"/athletes/(\d+)", ref)
        if not mk or not m or m.group(1) not in names:
            continue
        tgt = ((it.get("current") or {}).get("target") or {}).get("value")
        if mk == "td":
            line = 0.5
        elif tgt is None:
            continue
        else:
            line = float(tgt) - 0.5 if one else float(tgt)
        if one:
            price = _odds(((it.get("odds") or {}).get("american") or {}).get("value"))
            if price is None:
                continue
            px = {"o": price}
        else:
            px = _side_prices(it)
            if not px:
                continue
        d = out.setdefault(names[m.group(1)], {}).setdefault(f"{mk}|{line:g}", {})
        d.update(px)
        if mk == "td":
            d.update(n=1, best=d["o"], src="DK")
    return out


def fetch(norm, log=print) -> dict:
    """This week's prices: {"games": {"AWAY@HOME": {"players": {...}}}, ...}. Never raises: {} when ESPN is down."""
    try:
        sb = requests.get(f"{SITE}/scoreboard", headers=UA, timeout=20).json()
    except Exception as e:
        log(f"nfl espn props: scoreboard failed ({e})")
        return {}
    names: dict = {}
    teams_done: set = set()
    games: dict = {}
    seen: Counter = Counter()
    for ev in sb.get("events", []):
        if ((ev.get("status") or {}).get("type") or {}).get("state") == "post":
            continue
        comp = (ev.get("competitions") or [{}])[0]
        side = {}
        for c in comp.get("competitors", []):
            t = c.get("team") or {}
            ab = ESPN_TEAM.get(t.get("abbreviation", ""), t.get("abbreviation", ""))
            side[c.get("homeAway")] = ab
            tid = t.get("id")
            if not tid or tid in teams_done:
                continue
            teams_done.add(tid)
            try:
                rj = requests.get(f"{SITE}/teams/{tid}/roster", headers=UA, timeout=15).json()
                for g in rj.get("athletes", []):
                    for a in (g.get("items", []) if isinstance(g, dict) and "items" in g else [g]):
                        if a.get("id") and (a.get("fullName") or a.get("displayName")):
                            names[str(a["id"])] = norm(a.get("fullName") or a.get("displayName"))
            except Exception:
                continue
        eid = ev.get("id")
        try:
            pb = requests.get(f"{CORE}/events/{eid}/competitions/{eid}/odds/{PROVIDER}/propBets?limit=1000", headers=UA, timeout=25).json()
        except Exception as e:
            log(f"nfl espn props: event {eid} failed ({e})")
            continue
        got = parse(pb.get("items", []), names, seen)
        if got:
            games[f"{side.get('away')}@{side.get('home')}"] = dict(commence=ev.get("date"), players=got)
    n = sum(len(g["players"]) for g in games.values())
    log(f"nfl espn props: DraftKings prices for {n} players in {len(games)} games (free); "
        f"prop types seen: {', '.join(f'{k} ({v})' for k, v in seen.most_common(12)) or 'none'}")
    return {"book": "DraftKings", "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "games": games}
