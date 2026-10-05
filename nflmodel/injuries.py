"""Missing players: how much of each position group a team is without this week, relative to its ratings.

The team ratings are a recency-weighted average of past games, so a player matters to them in proportion to how
much he played in those games. For each player, his baseline = his snap share (offense or defense) in each of the
team's games over the last year, weighted exactly like the ratings weight games (half-life 140 days), zero for
games he missed. An injured player removes his baseline from his group, scaled by how likely he is to sit:

    Out / IR / suspended 1.0   Doubtful 0.99   Questionable 0.33

(measured on 2021-25 official reports against snap counts: 99.9% of Out, 99.3% of Doubtful and 33% of
Questionable players sat). So a starter who has played every week counts fully; one already out for weeks counts
only for what is left of him in the ratings; a player just traded in counts for the games he has played here.

Groups: offense RB, receivers (WR/TE), line; defense front (DL/edge), linebackers, secondary.
QBs are handled separately (a ruled-out starter is swapped for the backup in the QB adjustment).
How many points a missing group costs is fitted with the rest of the game model on past seasons, using the
official injury report that was published before each game (nflverse), so the backtest sees only what was known.

Live statuses come from ESPN's injury list (updated through the week); nflverse's copy of the official report
fills in when ESPN can't be reached.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
import requests

from .teams import FULL

GROUP = {"QB": "QB", "RB": "RB", "FB": "RB", "HB": "RB", "WR": "REC", "TE": "REC",
         "T": "OL", "G": "OL", "C": "OL", "OL": "OL", "OT": "OL", "OG": "OL",
         "DE": "DL", "DT": "DL", "NT": "DL", "DL": "DL", "EDGE": "DL",
         "LB": "LB", "ILB": "LB", "OLB": "LB", "MLB": "LB",
         "CB": "DB", "S": "DB", "SS": "DB", "FS": "DB", "DB": "DB", "SAF": "DB"}
OFF, DEF = ("RB", "REC", "OL"), ("DL", "LB", "DB")
GROUPS = OFF + DEF
LABEL = {"RB": "RB", "REC": "WR/TE", "OL": "O-line", "DL": "D-line", "LB": "LB", "DB": "secondary"}
MISS = {"out": 1.0, "injured reserve": 1.0, "ir": 1.0, "suspension": 1.0, "suspended": 1.0, "pup": 1.0,
        "physically unable to perform": 1.0, "non-football injury": 1.0, "doubtful": 0.99, "questionable": 0.33}
HALF_LIFE, MIN_BASE = 140.0, 0.10   # days (same as the team ratings); smallest baseline worth listing
ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries"
ESPN_FIX = {"LAR": "LA", "WSH": "WAS"}


def norm(name) -> str:
    n = re.sub(r"[^a-z ]", "", str(name).lower().replace("-", " "))
    return " ".join(w for w in n.split() if w not in ("jr", "sr", "ii", "iii", "iv", "v"))


def miss_weight(status) -> float:
    s = str(status or "").strip().lower()
    for k, v in MISS.items():
        if s.startswith(k):
            return v
    return 0.0


def prep_snaps(snaps: pd.DataFrame, sched: pd.DataFrame) -> pd.DataFrame:
    s = snaps.merge(sched[["game_id", "gameday"]], on="game_id", how="inner")
    s["group"] = s.position.map(GROUP)
    s = s[s.group.notna()].copy()
    s["share"] = np.where(s.group.isin(DEF), s.defense_pct, s.offense_pct).astype(float)
    s["key"] = s.player.map(norm)
    return s[["game_id", "gameday", "team", "player", "key", "position", "group", "share"]]


def regulars(snaps: pd.DataFrame, team: str, asof, half_life: float = HALF_LIFE, min_base: float = MIN_BASE) -> pd.DataFrame:
    """Players built into `team`'s ratings before `asof`: key -> player, group, share (baseline), usual, presence.

    baseline = sum over the team's games of weight x his snap share / sum of weights (missed games count 0),
    usual    = his average share in the games he played, presence = baseline / usual."""
    asof = pd.Timestamp(asof)
    t = snaps[(snaps.team == team) & (snaps.gameday < asof) & (snaps.gameday >= asof - pd.Timedelta(days=400))]
    if t.empty:
        return pd.DataFrame(columns=["player", "group", "share", "usual", "presence", "last"])
    games = t.groupby("game_id").gameday.first()
    w = 0.5 ** ((asof - games).dt.days.astype(float) / half_life)
    tot = float(w.sum())
    t = t[t.share > 0].assign(w=t.game_id.map(w))
    g = t.assign(ws=t.w * t.share).groupby("key").agg(player=("player", "last"), group=("group", "last"),
                                                      ws=("ws", "sum"), wp=("w", "sum"), usual=("share", "mean"))
    g["share"] = g.ws / tot
    g["presence"] = g.wp / tot
    g["last"] = g.index.isin(t[t.game_id == games.idxmax()].key)
    return g[g.share >= min_base][["player", "group", "share", "usual", "presence", "last"]]


def contract_values(contracts: pd.DataFrame) -> pd.DataFrame:
    """Contracts as rows key, team, start, end, cap_pct (share of the salary cap per year, OverTheCap via nflverse),
    plus whether it's a first-round rookie deal."""
    c = contracts[contracts.apy_cap_pct.notna() & contracts.year_signed.notna()].copy()
    c["key"] = c.player.map(norm)
    c["start"] = c.year_signed.astype(int)
    c["end"] = c.start + c.years.fillna(1).clip(lower=1).astype(int) - 1
    c["team"] = c.get("team", pd.Series("", index=c.index)).fillna("").astype(str)
    r1 = (c.get("draft_round", pd.Series(np.nan, index=c.index)) == 1) & (c.get("draft_year", pd.Series(np.nan, index=c.index)) == c.start)
    c["rookie_r1"] = r1.fillna(False)
    return c[["key", "team", "position", "start", "end", "apy_cap_pct", "rookie_r1"]]


def skill_shares(pg: pd.DataFrame, team: str, asof, games: int = 8) -> dict:
    """'first-initial last' -> (target share, carry share) over the team's last few games (box scores)."""
    if pg is None or pg.empty:
        return {}
    x = pg[(pg.team == team) & (pg.date < pd.Timestamp(asof)) & (pg.date >= pd.Timestamp(asof) - pd.Timedelta(days=300))]
    gids = x.drop_duplicates("game_id").sort_values("date").game_id.tail(games)
    x = x[x.game_id.isin(gids)]
    if x.empty:
        return {}
    T, C = max(x.tgt.sum(), 1), max(x.car.sum(), 1)
    g = x.groupby("name").agg(tgt=("tgt", "sum"), car=("car", "sum"))
    return {short(n): (r.tgt / T, r.car / C) for n, r in g.iterrows()}


def short(name) -> str:
    """'Puka Nacua' / 'P.Nacua' -> 'p nacua' (how box scores and snap counts can be matched)."""
    n = norm(str(name).replace(".", " "))
    p = n.split()
    return f"{p[0][0]} {p[-1]}" if len(p) >= 2 else n


def team_values(cv: pd.DataFrame | None, season: int, team: str, power: float, shares: dict | None = None,
                ref: float = 0.03, lo: float = 0.5, hi: float = 2.5) -> dict:
    """key -> how much a player matters relative to an average starter, for one team:
       contract  (cap% / 3%) ** power  (same-name players told apart by team),
       usage     receivers / backs: target share / 16% or carry share / 45% (stars on rookie deals),
       first-round rookie deals at least 1.25; the largest of these, clipped to [0.5, 2.5]."""
    if power == 0:
        return {}
    out = {}
    if cv is not None and len(cv):
        from .teams import TEAMS
        nick = TEAMS.get(team, (team, team))[1]
        x = cv[(cv.start <= season) & (cv.end >= season)].copy()
        x["mine"] = x.team.str.contains(nick, case=False, regex=False) | x.team.str.contains(rf"\b{team}\b", regex=True)
        x = x.sort_values(["mine", "start", "apy_cap_pct"]).drop_duplicates("key", keep="last")
        for r in x.itertuples():
            v = (max(r.apy_cap_pct, 0.004) / ref) ** power
            if r.rookie_r1:
                v = max(v, 1.25)
            out[r.key] = v
    return _with_usage(out, shares, lo, hi)


def _with_usage(out: dict, shares: dict | None, lo: float, hi: float) -> dict:
    res = {k: float(np.clip(v, lo, hi)) for k, v in out.items()}
    for k_short, (ts, cs) in (shares or {}).items():
        u = max(ts / 0.16, cs / 0.45)
        res[("~", k_short)] = float(np.clip(u, lo, hi))
    return res


def value_of(values: dict, key: str) -> float:
    v = values.get(key)
    u = values.get(("~", short(key)))
    if v is None and u is None:
        return 1.0
    return max(x for x in (v, u) if x is not None)


def value_mult(cv, season, power, **kw) -> dict:   # kept for older callers: contract part only, no team
    if cv is None or cv.empty or power == 0:
        return {}
    x = cv[(cv.start <= season) & (cv.end >= season)].sort_values("start").drop_duplicates("key", keep="last")
    return dict(zip(x.key, np.clip((x.apy_cap_pct.clip(lower=0.004) / 0.03) ** power, 0.5, 2.5)))


def missing(regs: pd.DataFrame, report: pd.DataFrame, value: dict | None = None) -> tuple[dict, list]:
    """report: rows with key, status (for this team). Returns (group -> missing starter-equivalents, details)."""
    out = {g: 0.0 for g in GROUPS}
    det = []
    if report is None or report.empty or regs.empty:
        return out, det
    report = (report.assign(_w=report.status.map(miss_weight)).sort_values("_w", ascending=False)
              .drop_duplicates("key"))
    for r in report.itertuples():
        w = miss_weight(r.status)
        if w <= 0 or r.key not in regs.index:
            continue
        p = regs.loc[r.key]
        if p.group not in out:
            continue
        v = value_of(value or {}, r.key)
        out[p.group] += w * p.share * v
        det.append(dict(name=p.player, key=r.key, group=p.group, pos=getattr(r, "pos", None) or p.group,
                        status=str(r.status), share=round(float(p.share), 2), usual=round(float(p.usual), 2),
                        presence=round(float(p.presence), 2), w=w, value=round(float(v), 2)))
    det.sort(key=lambda d: -d["w"] * d["share"] * d["value"])
    return out, det


def long_term(status) -> bool:
    s = str(status or "").lower()
    return any(k in s for k in ("reserve", "pup", "physically unable", "non-football", "suspen")) or s.strip() == "ir"


def history_reports(inj: pd.DataFrame) -> pd.DataFrame:
    """Official game-status report (pre-game) as rows: season, week, team, key, status, pos."""
    r = inj[inj.report_status.notna()].copy()
    r["key"] = r.full_name.map(norm)
    r = r.rename(columns={"report_status": "status", "position": "pos"})
    return r[["season", "week", "team", "key", "status", "pos", "full_name"]]


def vector(m: dict) -> np.ndarray:
    return np.array([m[g] for g in GROUPS], float)


# ---------- live ----------

def fetch_espn(log=print) -> pd.DataFrame | None:
    """ESPN's league-wide injury list -> rows team, key, status, pos, name, detail. None if unreachable."""
    try:
        r = requests.get(ESPN_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0 (nflmodel)"})
        r.raise_for_status()
        js = r.json()
    except Exception as e:
        log(f"espn injuries: {e}")
        return None
    rows = []
    for tm in js.get("injuries", []):
        abbr = ((tm.get("team") or {}).get("abbreviation") or tm.get("abbreviation")
                or FULL.get(tm.get("displayName") or (tm.get("team") or {}).get("displayName")))
        for it in tm.get("injuries", []):
            a = it.get("athlete") or {}
            team = abbr or (a.get("team") or {}).get("abbreviation")
            if not team:
                continue
            det = it.get("details") or {}
            rows.append(dict(team=ESPN_FIX.get(team, team), name=a.get("displayName"), key=norm(a.get("displayName")),
                             pos=(a.get("position") or {}).get("abbreviation"),
                             status=it.get("status") or (it.get("type") or {}).get("description"),
                             detail=det.get("type") or it.get("shortComment"), date=it.get("date")))
    d = pd.DataFrame(rows)
    log(f"espn injuries: {len(d)} players on {d.team.nunique() if len(d) else 0} teams")
    return d if len(d) else None
