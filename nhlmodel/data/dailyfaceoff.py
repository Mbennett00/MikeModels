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
