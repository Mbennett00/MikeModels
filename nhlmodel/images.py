"""Team logos and player headshots: find a URL that actually works (ESPN or NHL).

Run in the daily job (which has internet access) and written to site/images.json, so the
dashboard only uses verified URLs. ESPN is tried first for logos, NHL first for headshots
(its roster endpoint gives the current-season photo), with ESPN matched by name as backup.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import requests

from .data.teams import norm_name

ESPN_ABBR = {"LAK": "la", "NJD": "nj", "SJS": "sj", "TBL": "tb", "UTA": "utah"}
ESPN_API = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl"
UA = {"User-Agent": "Mozilla/5.0 (nhlmodel dashboard image check)"}


def espn_logo(team: str) -> str:
    return f"https://a.espncdn.com/i/teamlogos/nhl/500/{ESPN_ABBR.get(team, team.lower())}.png"


def nhl_logo(team: str) -> str:
    return f"https://assets.nhle.com/logos/nhl/svg/{team}_light.svg"


def _ok(url: str) -> bool:
    if not url:
        return False
    try:
        r = requests.get(url, headers=UA, timeout=10, stream=True)
        ok = r.status_code == 200 and r.headers.get("content-type", "").startswith("image")
        r.close()
        return ok
    except requests.RequestException:
        return False


def _first_ok(urls):
    for u in urls:
        if _ok(u):
            return u
    return ""


def espn_headshots(teams) -> dict:
    """ESPN headshot URL keyed by normalised player name, for the given NHL team abbreviations."""
    out = {}
    try:
        tj = requests.get(f"{ESPN_API}/teams", headers=UA, timeout=15).json()
        teams_list = tj["sports"][0]["leagues"][0]["teams"]
    except Exception:
        return out
    want = {ESPN_ABBR.get(t, t.lower()) for t in teams}
    for t in teams_list:
        tm = t.get("team", {})
        if str(tm.get("abbreviation", "")).lower() not in want:
            continue
        try:
            rj = requests.get(f"{ESPN_API}/teams/{tm['id']}/roster", headers=UA, timeout=15).json()
        except Exception:
            continue
        groups = rj.get("athletes", [])
        items = [a for g in groups for a in (g.get("items", []) if isinstance(g, dict) and "items" in g else [g])]
        for a in items:
            name = a.get("fullName") or a.get("displayName")
            href = (a.get("headshot") or {}).get("href") or (
                f"https://a.espncdn.com/i/headshots/nhl/players/full/{a['id']}.png" if a.get("id") else "")
            if name and href:
                out[norm_name(name)] = href
    return out


def resolve(teams, players, log=print) -> dict:
    """players: iterable of dicts with player_id, name, headshot (NHL url or '')."""
    teams = sorted(set(teams))
    players = list(players)
    espn = espn_headshots(teams)
    with ThreadPoolExecutor(max_workers=16) as ex:
        logos = dict(zip(teams, ex.map(lambda t: _first_ok([espn_logo(t), nhl_logo(t)]), teams)))
        heads = list(ex.map(lambda p: _first_ok([p.get("headshot") or "", espn.get(norm_name(p["name"]), "")]),
                            players))
    faces = {str(int(p["player_id"])): h for p, h in zip(players, heads) if h}
    log(f"images: {sum(bool(v) for v in logos.values())}/{len(teams)} logos, {len(faces)}/{len(players)} headshots "
        f"({len(espn)} ESPN roster photos found)")
    return {"logos": logos, "headshots": faces}
