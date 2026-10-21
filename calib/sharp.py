"""DraftKings + FanDuel odds from SharpAPI (free tier: those two books, 60 s delay, 12 requests a minute).

Used by calib.odds when SHARP_API_KEY is set. One pass per league with games coming up pulls pre-game game lines and
the player markets the pages show, both books, paging 200 rows at a time (paced under the rate limit, capped per
league). From that it builds, per league:
  props  {player key: {"stat|line": american}}   the over ("N+") price: DraftKings' where it has the rung, else FanDuel's
  bk     {player key: {"stat|line": "FD"}}        rungs priced from FanDuel (DraftKings didn't hang them)
  fair   {player key: {"stat|line": p}}           chance of the over with the vig out, averaged over the books: no-vig
                                                  from both sides where a book posts the under, else 1/decimal less hold1()
  games  [{home, away, t, books, ml, spread, total}]  the same shape as calib.odds consensus lines
Never raises: any failure logs and returns what it has.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import re
import statistics
import time

import requests

BASE = "https://api.sharpapi.io/api/v1"
LG = {"NHL": "nhl", "NFL": "nfl", "NBA": "nba"}
MAIN = {"NHL": ("moneyline", "puck_line", "total_goals"), "NFL": ("moneyline", "point_spread", "total_points"),
        "NBA": ("moneyline", "point_spread", "total_points")}
PROPS = {   # SharpAPI market type -> the page's stat
    "NHL": {"anytime_goal_scorer": "goals", "player_goals": "goals", "player_points": "points", "player_assists": "assists",
            "player_shots_on_goal": "sog"},
    "NFL": {"anytime_touchdown_scorer": "td", "player_receiving_yards": "rec_yds", "player_rushing_yards": "rush_yds",
            "player_passing_yards": "pass_yds", "player_receptions": "rec"},
    "NBA": {"player_points": "pts", "player_rebounds": "reb", "player_assists": "ast", "player_made_threes": "fg3",
            "player_points_+_rebounds_+_assists": "pra", "player_double_double": "dd", "player_triple_double": "trip"},
}
YES_NO = ("dd", "trip")      # props with no line: a player does it or he doesn't
BOOKS = {"draftkings": "DK", "fanduel": "FD"}
PACE = float(os.environ.get("SHARP_PACE", "5.3"))      # seconds between calls: 12 a minute on the free tier
MAX_PAGES = int(os.environ.get("SHARP_MAX_PAGES", "40"))
def hold1(p: float) -> float:
    """A one-sided prop's hold, when there's no under to cancel it: about 5% near even money, rising to about 25% on
    long shots (books shade long odds hardest: the favourite-longshot bias)."""
    return 1.05 + 0.20 * max(0.0, 0.5 - p) / 0.5


def _p(a: float) -> float:
    return 100 / (a + 100) if a > 0 else -a / (-a + 100)


def _am(p: float) -> int:
    p = min(max(p, 0.01), 0.99)
    return round(-100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)


def _mid(prices: list) -> int | None:
    return _am(statistics.median(_p(x) for x in prices)) if prices else None


class Client:
    def __init__(self, key: str, log=print):
        self.key, self.log, self.calls, self.last = key, log, 0, 0.0

    def get(self, path: str, params: dict) -> dict:
        for attempt in range(3):
            wait = self.last + PACE - time.time()
            if wait > 0:
                time.sleep(wait)
            self.last = time.time(); self.calls += 1
            r = requests.get(f"{BASE}{path}", params=params, headers={"X-API-Key": self.key, "User-Agent": "Pikt odds"}, timeout=40)
            if r.status_code == 429:
                try:
                    ra = float((r.json().get("error") or {}).get("retry_after") or 20)
                except ValueError:
                    ra = 20
                time.sleep(min(ra, 65)); continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError("rate limited")

    def rows(self, params: dict, cap: int) -> tuple[list, bool]:
        """Every row for the query, following offset then cursor; (rows, complete)."""
        out, off, cur = [], 0, None
        for _ in range(cap):
            q = dict(params, limit=200, **({"cursor": cur} if cur else {"offset": off}))
            j = self.get("/odds", q)
            out += j.get("data") or []
            pg = j.get("pagination") or (j.get("meta") or {}).get("pagination") or {}
            if not pg.get("has_more"):
                return out, True
            cur = pg.get("next_cursor")
            if not cur:
                off = pg.get("next_offset") or off + 200
                if off > 500:
                    return out, False
        return out, False


def nm(s: str) -> str:
    from calib.odds import nm as _nm
    return _nm(s)


def _pairs(entries: list) -> list:
    """[(|no-vig over - 50%|, line, market)] for every line a market prices both ways."""
    by_m, out = {}, []
    for e in entries:
        by_m.setdefault(e["m"], []).append(e)
    for m, es in by_m.items():
        o = {e["line"]: e["a"] for e in es if e["side"] == "over"}; u = {e["line"]: e["a"] for e in es if e["side"] == "under"}
        for ln in set(o) & set(u):
            out.append((abs(_p(o[ln]) / (_p(o[ln]) + _p(u[ln])) - 0.5), ln, m))
    return out


def _clean(entries: list, center: float | None = None) -> list:
    """One book's rows for one player and stat -> the rows that belong to the full-game ladder.
    Feeds sometimes file a period market (DraftKings' 1st-quarter points or rebounds) under the full-game type. Every
    row of a market shares a market_id, so one market anchors the ladder and any other market whose over prices
    contradict it (a lower line must be likelier, a higher one less) goes. The anchor is the market priced both ways
    nearest the player's main line across both books (center), so a book whose only two-way market is a quarter
    market can't anchor on it."""
    over = [e for e in entries if e["side"] == "over"]
    by_m = {}
    for e in entries:
        by_m.setdefault(e["m"], []).append(e)
    pairs = _pairs(entries)
    if center is not None and over:
        near = min(over, key=lambda e: (abs(e["line"] - center), abs(_p(e["a"]) - 0.5)))
        cand = [x for x in pairs if abs(x[1] - center) <= max(1.0, 0.15 * center)]
        anchor = min(cand)[2] if cand else near["m"]
    elif pairs:
        anchor = min(pairs)[2]
    elif over:
        anchor = min(over, key=lambda e: abs(_p(e["a"]) - 0.5))["m"]
    else:
        return []
    A = sorted((e["line"], _p(e["a"])) for e in by_m[anchor] if e["side"] == "over")
    def fits(e):
        p = _p(e["a"])
        return all(p >= q - 0.02 for ln, q in A if ln > e["line"]) and all(p <= q + 0.02 for ln, q in A if ln < e["line"])
    keep = list(by_m[anchor])
    for m, es in by_m.items():
        if m != anchor and all(fits(e) for e in es if e["side"] == "over"):
            keep += es
    return keep


def build_props(league: str, rows: list) -> dict:
    """Rows -> {"props", "bk", "fair"} (see the module notes)."""
    kinds = PROPS[league]
    raw = {}   # (book, player, stat) -> [{line, side, a, m}]
    for r in rows:
        stat = kinds.get(r.get("market_type"))
        who = r.get("player_name") or (r.get("selection") if "scorer" in str(r.get("market_type")) or stat in YES_NO else None)
        bk = BOOKS.get(r.get("sportsbook"))
        a = r.get("odds_american")
        if not stat or not who or not bk or a is None or r.get("is_live") or str(who).lower().startswith("any "):
            continue
        a = int(a)
        if abs(a) < 100:
            continue
        side = str(r.get("selection_type") or "").lower()
        if "scorer" in r["market_type"]:
            line, side = 0.5, "over"
        elif stat in YES_NO:                     # yes / no: "yes" is the over of a 0.5 line
            yn = {"yes": "over", "over": "over", "no": "under", "under": "under"}   # the side sits in selection ("Yes", type "other")
            side = yn.get(side) or yn.get(str(r.get("selection") or "").strip().lower())
            if not side:
                continue
            line = 0.5
        else:
            line = r.get("line")
            if line is None or side not in ("over", "under"):
                continue
            line = float(line)
            if line != int(line) + 0.5:          # whole-number lines push; the page's "N+" rungs are half lines
                continue
        m = r.get("market_id") or r["market_type"]
        raw.setdefault((bk, nm(who), stat), []).append({"line": line, "side": side, "a": a, "m": f"{r['market_type']}:{m}"})
    q = {}   # (player, key) -> {book: {"over": am, "under": am}}
    # (player, stat) -> the main line: among the lines either book prices both ways near even money, the largest. A
    # period market (quarter, half) can only run lower than the full game, so when the books disagree the bigger
    # line is the full-game one.
    centers = {}
    for (bk, who, stat), es in raw.items():
        for x in _pairs(es):
            if x[0] <= 0.12 and x[1] > centers.get((who, stat), -1):
                centers[(who, stat)] = x[1]
    for (bk, who, stat), es in raw.items():
        c = centers.get((who, stat))
        for e in (es if stat in ("goals", "td", *YES_NO) and all(x["line"] == 0.5 for x in es) else _clean(es, c)):
            q.setdefault((who, f"{stat}|{e['line']:g}"), {}).setdefault(bk, {})[e["side"]] = e["a"]
    props, bk, fair = {}, {}, {}
    for (who, k), by in q.items():
        ps = {}
        for b, s in by.items():
            if "over" not in s:
                continue
            po = _p(s["over"])
            ps[b] = po / (po + _p(s["under"])) if "under" in s else min(0.99, po / hold1(po))
        if len(ps) == 2 and abs(ps["DK"] - ps["FD"]) > 0.2:     # the books disagree wildly: one of them is a misread
            continue
        dk, fd = (by.get("DK") or {}).get("over"), (by.get("FD") or {}).get("over")
        if dk is None and fd is None:
            continue
        props.setdefault(who, {})[k] = dk if dk is not None else fd
        if dk is None:
            bk.setdefault(who, {})[k] = "FD"
        fair.setdefault(who, {})[k] = round(sum(ps.values()) / len(ps), 4)
    for who, F in fair.items():
        for k in [k for k, v in F.items() if abs(_p(props[who][k]) - v) > 0.12]:   # a price must agree with its own fair chance
            for d in (props, bk, fair):
                (d.get(who) or {}).pop(k, None)
        for stat in {k.split("|")[0] for k in F}:   # each ladder, walked out from its rung nearest even money, must slope
            for src in (F, {k: _p(a) for k, a in props.get(who, {}).items()}):   # in fair chances and in the prices bet
                for k in ladder_drop({k: v for k, v in src.items() if k.startswith(stat + "|")}):
                    for d in (props, bk, fair):
                        (d.get(who) or {}).pop(k, None)
    if league == "NHL":   # small counts: every rung must sit near a Poisson fitted to the even-money rung
        for who, F in fair.items():
            for stat in {k.split("|")[0] for k in F}:
                for k in poisson_drop({k: v for k, v in F.items() if k.startswith(stat + "|")}):
                    for d in (props, bk, fair):
                        (d.get(who) or {}).pop(k, None)
    return {"props": props, "bk": bk, "fair": fair}


def _sf(line: float, lam: float) -> float:
    """P(X > line) for X ~ Poisson(lam)."""
    p, s = math.exp(-lam), 0.0
    for i in range(int(math.floor(line)) + 1):
        s += p; p *= lam / (i + 1)
    return max(1e-6, min(1 - 1e-6, 1 - s))


def poisson_drop(F: dict, tol: float = 1.0) -> list:
    """{"stat|line": chance} -> rungs whose chance is more than tol (log-odds) off a Poisson through the rung nearest
    50%. Catches a misfiled rung inside an otherwise sane ladder: 1+ points at -330 but 2+ at +790 (Poisson says ~+180)."""
    if len(F) < 2:
        return []
    k0 = min(F, key=lambda k: abs(F[k] - 0.5)); L0 = float(k0.split("|")[1])
    lo, hi = 1e-4, 60.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if _sf(L0, mid) < F[k0] else (lo, mid)
    lam = (lo + hi) / 2
    lg = lambda q: math.log(q / (1 - q))
    return [k for k, v in F.items() if 0 < v < 1 and abs(lg(v) - lg(_sf(float(k.split("|")[1]), lam))) > tol]


def ladder_drop(F: dict) -> list:
    """{"stat|line": chance} -> the rungs that break the slope (a higher line must be less likely), judged outward
    from the rung nearest 50% so one bad rung can't take the good ones with it."""
    L = sorted(F.items(), key=lambda kv: float(kv[0].split("|")[1]))
    if len(L) < 2:
        return []
    i = min(range(len(L)), key=lambda j: abs(L[j][1] - 0.5))
    bad, last = [], L[i][1]
    for k, v in L[i + 1:]:
        if v < last - 0.005: last = v
        else: bad.append(k)
    last = L[i][1]
    for k, v in reversed(L[:i]):
        if v > last + 0.005: last = v
        else: bad.append(k)
    return bad


def build_games(league: str, rows: list) -> list:
    """Rows -> consensus game lines (median over the two books, main lines only)."""
    ev = {}
    for r in rows:
        if r.get("is_live") or r.get("market_type") not in MAIN[league] or r.get("is_alternate_line") or r.get("odds_american") is None:
            continue
        e = ev.setdefault(r.get("event_id"), {"home": r.get("home_team"), "away": r.get("away_team"), "t": r.get("event_start_time"), "b": {}})
        side = str(r.get("selection_type") or "").lower()
        e["b"].setdefault(r.get("sportsbook"), {}).setdefault(r["market_type"], {})[side] = (int(r["odds_american"]), r.get("line"))
    out = []
    for e in ev.values():
        ml_h, ml_a, sp, tot = [], [], {}, {}
        for m in e["b"].values():
            for mt, s in m.items():
                if mt == "moneyline" and "home" in s and "away" in s:
                    ml_h.append(s["home"][0]); ml_a.append(s["away"][0])
                elif mt in ("puck_line", "point_spread") and "home" in s and "away" in s and s["home"][1] is not None:
                    sp.setdefault(float(s["home"][1]), []).append((s["home"][0], s["away"][0]))
                elif mt.startswith("total") and "over" in s and "under" in s and s["over"][1] is not None:
                    tot.setdefault(float(s["over"][1]), []).append((s["over"][0], s["under"][0]))
        g = {"home": e["home"], "away": e["away"], "t": (e["t"] or "").replace("Z", ":00Z") if re.search(r"T\d\d:\d\dZ$", e["t"] or "") else e["t"],
             "books": len(e["b"]), "src": "sharp"}
        if ml_h:
            g["ml"] = {"home": _mid(ml_h), "away": _mid(ml_a)}
        if sp:
            pt, L = max(sp.items(), key=lambda kv: (len(kv[1]), -abs(kv[0])))
            g["spread"] = {"home": pt, "home_price": _mid([x[0] for x in L]), "away_price": _mid([x[1] for x in L])}
        if tot:
            pt, L = max(tot.items(), key=lambda kv: (len(kv[1]), -abs(kv[0] - statistics.median(tot))))
            g["total"] = {"line": pt, "over": _mid([x[0] for x in L]), "under": _mid([x[1] for x in L])}
        if len(g) > 5:
            out.append(g)
    return out


def pull(leagues: list, key: str, log=print) -> dict:
    """{league: {"fetched_at", "games", "props", "bk", "fair", "complete"}} for the leagues asked for."""
    if not key:
        return {}
    c, out = Client(key, log), {}
    for lg in leagues:
        try:
            base = {"league": LG[lg], "is_live": "false", "sportsbook": ",".join(BOOKS)}
            g_rows, _ = c.rows(dict(base, market=",".join(MAIN[lg])), 6)
            p_rows, done = c.rows(dict(base, market=",".join(k for k, v in PROPS[lg].items() if v not in YES_NO)), MAX_PAGES)
        except Exception as e:
            log(f"odds: SharpAPI {lg} failed ({str(e)[:160]})"); continue
        yn = [k for k, v in PROPS[lg].items() if v in YES_NO]
        if yn:   # asked apart: an unknown market name must not cost the main props
            try:
                y_rows, _ = c.rows(dict(base, market=",".join(yn)), 4)
                p_rows += y_rows
                log(f"odds: SharpAPI {lg} yes/no props: {len(y_rows)} rows ({', '.join(sorted({str(r.get('market_type')) for r in y_rows})) or 'none'})")
            except Exception as e:
                log(f"odds: SharpAPI {lg} yes/no props failed ({str(e)[:160]})")
        P = build_props(lg, p_rows)
        out[lg] = {"fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "games": build_games(lg, g_rows),
                   "complete": done, **P}
        n_fd = sum(len(v) for v in P["bk"].values())
        log(f"odds: SharpAPI {lg}: {len(out[lg]['games'])} games, props for {len(P['props'])} players "
            f"({sum(len(v) for v in P['props'].values())} rungs, {n_fd} from FanDuel){'' if done else ' (page cap hit)'} · {c.calls} calls")
    return out
