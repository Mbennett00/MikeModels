"""Daily Faceoff scraper: starting goalies, line combinations, PP units, injuries.

Daily Faceoff has no API; its pages are Next.js and embed their data as JSON in
<script id="__NEXT_DATA__">. We read that JSON (no HTML parsing), a few pages a few times a day.
"""
from __future__ import annotations

import json
import re
import time

import requests

BASE = "https://www.dailyfaceoff.com"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

SLUG = {
    "ANA": "anaheim-ducks", "BOS": "boston-bruins", "BUF": "buffalo-sabres", "CGY": "calgary-flames",
    "CAR": "carolina-hurricanes", "CHI": "chicago-blackhawks", "COL": "colorado-avalanche",
    "CBJ": "columbus-blue-jackets", "DAL": "dallas-stars", "DET": "detroit-red-wings", "EDM": "edmonton-oilers",
    "FLA": "florida-panthers", "LAK": "los-angeles-kings", "MIN": "minnesota-wild", "MTL": "montreal-canadiens",
    "NSH": "nashville-predators", "NJD": "new-jersey-devils", "NYI": "new-york-islanders",
    "NYR": "new-york-rangers", "OTT": "ottawa-senators", "PHI": "philadelphia-flyers",
    "PIT": "pittsburgh-penguins", "SJS": "san-jose-sharks", "SEA": "seattle-kraken", "STL": "st-louis-blues",
    "TBL": "tampa-bay-lightning", "TOR": "toronto-maple-leafs", "UTA": "utah-mammoth",
    "VAN": "vancouver-canucks", "VGK": "vegas-golden-knights", "WSH": "washington-capitals", "WPG": "winnipeg-jets",
}
ALT_SLUG = {"UTA": ["utah-hockey-club"]}


def next_data(url: str, session: requests.Session | None = None, sleep: float = 1.5) -> dict:
    s = session or requests.Session()
    r = s.get(url, headers=HEADERS, timeout=30)
    time.sleep(sleep)            # be polite
    r.raise_for_status()
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
    if not m:
        raise ValueError(f"{url}: no __NEXT_DATA__ block (status {r.status_code}, {len(r.text)} bytes)")
    return json.loads(m.group(1))


def goalies_url(date) -> str:
    import pandas as pd
    return f"{BASE}/starting-goalies/{pd.Timestamp(date).strftime('%Y-%m-%d')}"


def lines_url(team: str, slug: str | None = None) -> str:
    return f"{BASE}/teams/{slug or SLUG[team]}/line-combinations"


ABBR = {v: k for k, v in SLUG.items()} | {s: k for k, alts in ALT_SLUG.items() for s in alts}
INJURY_LABEL = {"ir": "IR", "ltir": "LTIR", "out": "Out", "dtd": "Day-to-day"}


def parse_goalies(js: dict) -> list[dict]:
    """One row per team on the starting-goalies page: goalie name and Confirmed / Likely / Unconfirmed."""
    rows = []
    for g in js.get("props", {}).get("pageProps", {}).get("data", []) or []:
        for side in ("home", "away"):
            team = ABBR.get(g.get(f"{side}TeamSlug", ""))
            if not team:
                continue
            rows.append(dict(team=team, goalie=g.get(f"{side}GoalieName") or "",
                             status=g.get(f"{side}NewsStrengthName") or "Unconfirmed",
                             note=(g.get(f"{side}NewsDetails") or "").strip(),
                             updated=g.get(f"{side}NewsCreatedAt"), start_utc=g.get("dateGmt")))
    return rows


def parse_lines(js: dict, team: str) -> list[dict]:
    """Every player listed on a team's line-combinations page with his slot and injury status."""
    players = js.get("props", {}).get("pageProps", {}).get("combinations", {}).get("players", []) or []
    return [dict(team=team, name=p.get("name") or "", category=p.get("categoryIdentifier"),
                 group=p.get("groupIdentifier"), slot=p.get("positionIdentifier"),
                 injury=p.get("injuryStatus"), gtd=bool(p.get("gameTimeDecision")),
                 news=((p.get("latestNews") or {}).get("details") or "").strip())
            for p in players]


def fetch_day(date, teams, log=print) -> dict:
    """Starting goalies for the date plus line combinations for each team (one page per team)."""
    s = requests.Session()
    out = {"goalies": [], "lines": [], "errors": []}
    try:
        out["goalies"] = parse_goalies(next_data(goalies_url(date), s))
    except Exception as e:
        out["errors"].append(f"starting goalies: {e}")
    for t in sorted(set(teams)):
        for slug in [SLUG.get(t)] + ALT_SLUG.get(t, []):
            if not slug:
                continue
            try:
                out["lines"] += parse_lines(next_data(lines_url(t, slug), s), t)
                break
            except Exception as e:
                err = f"{t} lines ({slug}): {e}"
        else:
            out["errors"].append(err)
    log(f"daily faceoff: {len(out['goalies'])} goalie entries, {len(out['lines'])} player slots, "
        f"{len(out['errors'])} errors {out['errors'][:3]}")
    return out
