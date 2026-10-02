"""NFL player props: anytime TD, receptions, receiving / rushing / passing yards, passing TDs.

    volume      team targets and carries per game (recent games weighted, half-life 5 games), moved by game
                script: a team expected to lead runs more and throws less
    share       the player's recency-weighted share of team targets / carries (over games he played), shrunk
                for small samples; when teammates are out, the available players' shares are scaled up
    efficiency  catch rate, yards per target, yards per carry, yards per attempt, shrunk toward his role
                (QB / RB / receiver) average, then adjusted for the opponent's pass / run defence
    touchdowns  team offensive TDs follow the game model's projected points; they're split pass / rush by the
                team's mix, and each player's slice uses his red-zone (inside the 10) share blended with his
                overall share, since red-zone touches predict TDs better than past TDs do

Distributions (fitted on 2022-23 projections, checked on 2024-26): receptions negative binomial; receiving
yards zero when he has no catch, otherwise a shifted gamma; rushing and passing yards shifted gamma; passing TDs
Poisson; anytime TD 1 - exp(-rate) with the rate recalibrated. Means carry small calibration scales.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

STATS = ["tgt", "rz_tgt", "rec", "rec_yds", "rec_td", "car", "rz_car", "rush_yds", "rush_td", "att", "cmp",
         "pass_yds", "pass_td"]


@dataclass
class PropConfig:
    half_life: float = 5.0         # team games
    window: int = 20
    prev_season: float = 0.7       # extra weight factor on last season's games
    k_share: float = 1.5           # games of prior on usage shares
    k_ypt: float = 40.0            # targets of prior on yards / target and catch rate
    k_ypc: float = 60.0
    k_ypa: float = 150.0
    script_t: float = 0.35         # targets per point of projected margin (fewer when leading)
    script_c: float = 0.40         # carries per point of projected margin (more when leading)
    opp_pass: float = 1.2          # yards multiplier = exp(opp_pass * opponent EPA/dropback allowed)
    opp_rush: float = 0.8
    rz_blend: float = 0.6          # weight on red-zone share for TDs
    td_per_pt: float = 0.118       # offensive TDs per point scored
    max_boost: float = 1.35        # cap on share scale-up when teammates are out
    # fitted on 2022-23 walk-forward projections, checked on 2024-26 (see README)
    scale: dict = field(default_factory=lambda: dict(rec=1.061, rec_yds=1.075, rush_yds=1.111, pass_yds=0.969,
                                                     pass_td=0.889))
    td_a: float = 0.677            # anytime TD rate recalibration: rate' = a * rate ** b
    td_b: float = 0.671
    r_rec: float = 9.2             # receptions NB size
    cv_rec_yds: float = 0.60       # shifted gamma: Y + shift ~ Gamma(mean + shift, cv)
    sh_rec_yds: float = 10.0
    cv_rush_yds: float = 0.50
    sh_rush_yds: float = 20.0
    cv_pass_yds: float = 0.25
    sh_pass_yds: float = 50.0
    priors: dict = field(default_factory=dict)


def role(r) -> str:
    if r.att >= 8:
        return "QB"
    return "RB" if r.car > r.tgt else "REC"


def team_games(pg: pd.DataFrame) -> pd.DataFrame:
    t = pg.groupby(["game_id", "team"]).agg(date=("date", "first"), season=("season", "first"),
                                            **{c: (c, "sum") for c in STATS}).reset_index()
    t["off_td"] = t.rec_td + t.rush_td
    return t


def fit_priors(pg: pd.DataFrame) -> dict:
    """Role averages (efficiency) from the data."""
    d = pg.assign(role=[role(r) for r in pg.itertuples()])
    out = {}
    for rl, x in d.groupby("role"):
        out[rl] = dict(catch=x.rec.sum() / max(x.tgt.sum(), 1), ypt=x.rec_yds.sum() / max(x.tgt.sum(), 1),
                       ypc=x.rush_yds.sum() / max(x.car.sum(), 1))
    q = d[d.att > 0]
    out["pass"] = dict(ypa=q.pass_yds.sum() / q.att.sum(), td_att=q.pass_td.sum() / q.att.sum())
    return out


def _weights(tg_hist: pd.DataFrame, season: int, cfg: PropConfig):
    """Weight of each team game: by how many team games ago it was (per team)."""
    t = tg_hist.sort_values("date", ascending=False).copy()
    t["k"] = t.groupby("team").cumcount()
    t = t[t.k < cfg.window]
    t["w"] = 0.5 ** (t.k / cfg.half_life) * np.where(t.season < season, cfg.prev_season, 1.0)
    return t


def project(pg: pd.DataFrame, tg: pd.DataFrame, asof, games: pd.DataFrame, cfg: PropConfig,
            dfn: dict | None = None, available: dict | None = None, roles_now: dict | None = None,
            starters: dict | None = None) -> pd.DataFrame:
    """Projections for every player likely to touch the ball in `games`.

    games: rows team, opp, game_id, pts (team's projected points), margin (team's projected margin).
    dfn: {'pass': {team: EPA/dropback allowed vs average}, 'rush': {...}} from the team ratings.
    available: team -> set of player ids who can play (None = everyone who played recently).
    """
    asof = pd.Timestamp(asof)
    season = asof.year if asof.month >= 3 else asof.year - 1
    P = cfg.priors
    th = tg[(tg.date < asof) & (tg.date >= asof - pd.Timedelta(days=420))]
    W = _weights(th, season, cfg)
    ph = pg.merge(W[["game_id", "team", "w"] + [c for c in STATS + ["off_td"]]], on=["game_id", "team"],
                  suffixes=("", "_T"))
    out = []
    for g in games.itertuples():
        team = g.team
        Wt = W[W.team == team]
        if Wt.empty:
            continue
        sw = Wt.w.sum()
        vol_t = (Wt.w * Wt.tgt).sum() / sw - cfg.script_t * g.margin
        vol_c = (Wt.w * Wt.car).sum() / sw + cfg.script_c * g.margin
        vol_a = (Wt.w * Wt.att).sum() / sw - cfg.script_t * g.margin
        rz_t, rz_c = (Wt.w * Wt.rz_tgt).sum() / sw, (Wt.w * Wt.rz_car).sum() / sw
        pass_share_td = ((Wt.w * Wt.rec_td).sum() + 0.6 * 6) / ((Wt.w * Wt.off_td).sum() + 6)
        lam_team = max(g.pts, 3.0) * cfg.td_per_pt
        x = ph[ph.team == team]
        if x.empty:
            continue
        grp = x.assign(**{f"w_{c}": x.w * x[c] for c in STATS}, **{f"wT_{c}": x.w * x[f"{c}_T"] for c in STATS})
        pl = grp.groupby("player_id").agg(name=("name", "last"), last=("date", "max"), gp=("game_id", "nunique"),
                                          **{f"w_{c}": (f"w_{c}", "sum") for c in STATS},
                                          **{f"wT_{c}": (f"wT_{c}", "sum") for c in STATS})
        recent = set(x[x.date >= Wt.date.nlargest(3).min()].player_id) if len(Wt) else set()
        pl = pl[pl.index.isin(recent) | (pl["last"] >= asof - pd.Timedelta(days=200))]
        if pl.empty:
            continue

        def share(c):
            Tbar = (Wt.w * Wt[c]).sum() / sw
            return (pl[f"w_{c}"] + 0.0) / (pl[f"wT_{c}"] + cfg.k_share * max(Tbar, 1e-6))
        sh = {c: share(c) for c in ("tgt", "car", "rz_tgt", "rz_car", "att")}
        # who plays: drop players out, scale the rest up to the share the full group used to have
        avail = available.get(team) if available else None
        keep = pl.index.isin(avail) if avail is not None else pl.index.isin(recent)
        for c in sh:
            full = sh[c][pl.index.isin(recent)].sum()
            have = sh[c][keep].sum()
            scale = min(full / have, cfg.max_boost) if have > 0 and full > have else 1.0
            sh[c] = sh[c] * scale
        rl = pd.Series({p: (roles_now or {}).get(p) or ("QB" if pl.loc[p, "w_att"] > 3 * max(pl.loc[p, "w_car"], 1)
                                                         else "RB" if pl.loc[p, "w_car"] > pl.loc[p, "w_tgt"] else "REC")
                        for p in pl.index})
        # passer: the available QB with the most recent attempts gets all the dropbacks
        qbs = pl[keep & (pl.w_att > 0)].sort_values("w_att")
        starter = (starters or {}).get(team)
        if starter not in pl.index or not keep[pl.index.get_loc(starter)]:
            starter = qbs.index[-1] if len(qbs) else None
        dp = (dfn or {}).get("pass", {}).get(g.opp, 0.0)
        dr = (dfn or {}).get("rush", {}).get(g.opp, 0.0)
        mp, mr = np.exp(cfg.opp_pass * dp), np.exp(cfg.opp_rush * dr)
        for pid in pl.index[keep]:
            r = pl.loc[pid]
            ro = rl[pid]
            pr = P.get(ro if ro in P else "REC", P.get("REC"))
            tgt = max(vol_t, 10) * sh["tgt"][pid]
            car = max(vol_c, 8) * sh["car"][pid]
            catch = (r.w_rec + cfg.k_ypt * pr["catch"]) / (r.w_tgt + cfg.k_ypt)
            ypt = (r.w_rec_yds + cfg.k_ypt * pr["ypt"]) / (r.w_tgt + cfg.k_ypt)
            ypc = (r.w_rush_yds + cfg.k_ypc * pr["ypc"]) / (r.w_car + cfg.k_ypc)
            rec = tgt * catch
            rec_yds = tgt * ypt * mp
            rush_yds = car * ypc * mr
            s_rz_t = cfg.rz_blend * sh["rz_tgt"][pid] + (1 - cfg.rz_blend) * sh["tgt"][pid]
            s_rz_c = cfg.rz_blend * sh["rz_car"][pid] + (1 - cfg.rz_blend) * sh["car"][pid]
            lam_td = lam_team * (pass_share_td * s_rz_t + (1 - pass_share_td) * s_rz_c)
            sc = cfg.scale
            row = dict(game_id=g.game_id, team=team, opp=g.opp, player_id=pid, name=r["name"], role=ro,
                       tgt=tgt, rec=rec * sc["rec"], rec_yds=rec_yds * sc["rec_yds"], car=car,
                       rush_yds=rush_yds * sc["rush_yds"], lam_td=cfg.td_a * max(lam_td, 1e-6) ** cfg.td_b,
                       rz=s_rz_t + s_rz_c)
            if pid == starter:
                ypa = (r.w_pass_yds + cfg.k_ypa * P["pass"]["ypa"]) / (r.w_att + cfg.k_ypa)
                att = max(vol_a, 15)
                row.update(att=att, pass_yds=att * ypa * mp * sc["pass_yds"],
                           lam_pass_td=lam_team * pass_share_td * sc["pass_td"])
            out.append(row)
    return pd.DataFrame(out)


# ---------- distributions ----------

def nb_sf(line: float, mu: float, r: float) -> float:
    """P(X > line) for negative binomial with mean mu, size r."""
    p = r / (r + mu)
    return float(stats.nbinom.sf(np.floor(line), r, p))


def gamma_sf(line: float, mu: float, cv: float, shift: float = 0.0) -> float:
    """P(Y > line) where Y + shift ~ Gamma(mean mu + shift, coefficient of variation cv)."""
    if mu + shift <= 0:
        return 0.0
    k = 1.0 / cv ** 2
    return float(stats.gamma.sf(line + shift, k, scale=(mu + shift) / k))


def p_over(row, market: str, line: float, cfg: PropConfig) -> float:
    if market == "rec":
        return nb_sf(line, row["rec"], cfg.r_rec)
    if market == "rec_yds":
        p0 = (cfg.r_rec / (cfg.r_rec + row["rec"])) ** cfg.r_rec       # no catch
        return (1 - p0) * gamma_sf(line, row["rec_yds"] / max(1 - p0, 1e-6), cfg.cv_rec_yds, cfg.sh_rec_yds)
    if market == "rush_yds":
        return gamma_sf(line, row["rush_yds"], cfg.cv_rush_yds, cfg.sh_rush_yds)
    if market == "pass_yds":
        return gamma_sf(line, row["pass_yds"], cfg.cv_pass_yds, cfg.sh_pass_yds)
    if market == "pass_td":
        return float(stats.poisson.sf(np.floor(line), row["lam_pass_td"]))
    if market == "td":
        return float(1 - np.exp(-row["lam_td"]))
    raise ValueError(market)


def fair_line(mu: float, market: str) -> float:
    """A round line near the projection (x.5) for the card."""
    if market in ("rec_yds", "rush_yds", "pass_yds"):
        return np.floor(mu * 0.95) + 0.5          # medians sit a bit under the mean (right skew)
    return np.floor(mu) + 0.5


# ---------- walk-forward test ----------

def backtest(pg: pd.DataFrame, game_preds: pd.DataFrame, cfg: PropConfig, seasons, ratings_fn=None, log=print) -> pd.DataFrame:
    """Project every played week with earlier data only; players who actually played (as if the injury
    report were known). game_preds: game_id, home, away, m_model, t_model, season, week, gameday."""
    tg = team_games(pg)
    out = []
    gp = game_preds[game_preds.season.isin(seasons)]
    for (s, w), wk in gp.groupby(["season", "week"]):
        asof = wk.gameday.min()
        rows = []
        for x in wk.itertuples():
            ph, pa = (x.t_model + x.m_model) / 2, (x.t_model - x.m_model) / 2
            rows += [dict(game_id=x.game_id, team=x.home, opp=x.away, pts=ph, margin=x.m_model),
                     dict(game_id=x.game_id, team=x.away, opp=x.home, pts=pa, margin=-x.m_model)]
        games = pd.DataFrame(rows)
        played = pg[pg.game_id.isin(wk.game_id)]
        avail = {t: set(d.player_id) for t, d in played.groupby("team")}
        dfn = ratings_fn(asof) if ratings_fn else None
        pr = project(pg, tg, asof, games, cfg, dfn=dfn, available=avail)
        if pr.empty:
            continue
        act = played.set_index(["game_id", "player_id"])
        pr = pr.join(act[["rec", "rec_yds", "rush_yds", "pass_yds", "pass_td", "rec_td", "rush_td", "car", "tgt"]],
                     on=["game_id", "player_id"], rsuffix="_a")
        pr["season"], pr["week"] = s, w
        out.append(pr)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()
