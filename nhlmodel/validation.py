"""Section 9 reports: calibration tables, log loss / Brier vs baseline, CLV, market grading."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from .book import novig_table
from .config import ModelConfig
from .pricing import american_to_decimal

# one canonical selection per (market, line) so complementary rows are not double counted
CANONICAL = {"moneyline": ["home"], "puckline": ["home", "away"], "total": ["over"],
             "team_total": ["home_over", "away_over"], "p1_total": ["over"], "p1_3way": ["home", "draw", "away"],
             "goals": ["over"], "sog": ["over"], "assists": ["over"], "points": ["over"]}

EPS = 1e-6


def logloss(p, y):
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS); y = np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def brier(p, y):
    return float(np.mean((np.asarray(p, float) - np.asarray(y, float)) ** 2))


def calibration_table(p, y, edges) -> pd.DataFrame:
    p = np.asarray(p, float); y = np.asarray(y, float)
    b = np.clip(np.digitize(p, edges[1:-1]), 0, len(edges) - 2)
    rows = []
    for i in range(len(edges) - 1):
        m = b == i
        n = int(m.sum())
        if n == 0:
            continue
        mp, hr = float(p[m].mean()), float(y[m].mean())
        se = np.sqrt(max(mp * (1 - mp), 1e-9) / n)
        rows.append(dict(bucket=f"{edges[i]:.0%}-{edges[i+1]:.0%}", n=n, mean_pred=mp, hit_rate=hr,
                         gap=hr - mp, z=(hr - mp) / se, low_sample=n < 200))
    return pd.DataFrame(rows)


def ece(tab: pd.DataFrame) -> float:
    if tab.empty:
        return float("nan")
    return float((tab.n * tab.gap.abs()).sum() / tab.n.sum())


def player_baselines(tables: dict) -> pd.DataFrame:
    """Naive baseline: the player's season-to-date per-game rate (games before this one only).

    Falls back to the previous season's rate, then to the position average to date.
    """
    pg = tables["player_games"].sort_values(["date", "game_id"]).copy()
    out = pg[["game_id", "player_id", "season", "pos", "date"]].copy()
    for s in ("goals", "sog", "assists", "points"):
        grp = pg.groupby(["player_id", "season"])[s]
        cnt = grp.cumcount()
        mean_std = (grp.cumsum() - pg[s]) / cnt.replace(0, np.nan)
        prev = pg.groupby(["player_id", "season"])[s].mean().rename("prev").reset_index()
        prev["season"] += 1
        prev_rate = pg[["player_id", "season"]].merge(prev, on=["player_id", "season"], how="left").prev.to_numpy()
        pos_cum = pg.groupby("pos")[s].cumsum() - pg[s]
        pos_n = pg.groupby("pos").cumcount()
        pos_rate = pos_cum / pos_n.replace(0, np.nan)
        out[f"base_{s}"] = mean_std.fillna(pd.Series(prev_rate, index=pg.index)).fillna(pos_rate).fillna(0.1)
    return out


def attach_baselines(bt: dict, tables: dict, cfg: ModelConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    pm = bt["player_markets"].copy()
    base = player_baselines(tables)
    pm = pm.merge(base[["game_id", "player_id"] + [c for c in base if c.startswith("base_")]],
                  on=["game_id", "player_id"], how="left")
    lam_b = np.select([pm.market == m for m in ("goals", "sog", "assists", "points")],
                      [pm.base_goals, pm.base_sog, pm.base_assists, pm.base_points])
    pm["p_base"] = stats.poisson.sf(np.floor(pm.line), np.clip(lam_b, 1e-4, None))
    pm["baseline"] = "player season per-game rate"

    gm = bt["game_markets"].copy()
    gm = gm.sort_values("date")
    # naive: frequency of this outcome in prior backtest rows (expanding, excludes the current date)
    grp = gm.groupby(["market", "selection", "line"], dropna=False)
    day_sum = gm.groupby(["market", "selection", "line", "date"], dropna=False).y.agg(["sum", "count"])
    day_sum = day_sum.groupby(level=[0, 1, 2], dropna=False).cumsum() - day_sum
    day_sum["freq"] = (day_sum["sum"] + 1) / (day_sum["count"] + 2)
    gm = gm.merge(day_sum["freq"].reset_index(), on=["market", "selection", "line", "date"], how="left")
    gm["p_base"] = gm.freq
    gm["baseline"] = "historical frequency"
    del grp
    odds = tables.get("odds")
    if odds is not None and len(odds):
        close = novig_table(odds[odds.player_id.isna()] if "player_id" in odds else odds, cfg, "close")
        if len(close):
            close = close[close.player_id.isna()].drop(columns=["player_id"])
            gm = gm.merge(close[["game_id", "market", "selection", "line", "p_novig"]].rename(
                columns={"p_novig": "p_close"}), on=["game_id", "market", "selection", "line"], how="left")
            has = gm.p_close.notna()
            gm.loc[has, "p_base"] = gm.loc[has, "p_close"]
            gm.loc[has, "baseline"] = "closing line (no-vig)"
    return gm, pm


def market_report(df: pd.DataFrame, cfg: ModelConfig) -> tuple[pd.DataFrame, dict]:
    """Per-market metrics + calibration tables. df has market, selection, line, p_model, p_base, y."""
    df = df[df.y.notna()]
    summary, tables = [], {}
    for market, sels in CANONICAL.items():
        d = df[(df.market == market) & df.selection.isin(sels)]
        if d.empty:
            continue
        groups = [("all", d)]
        if d.line.nunique(dropna=False) > 1:
            groups += list(d.groupby("line", dropna=False))
        for line, dl in groups:
            has_base = dl.p_base.notna()
            tab = calibration_table(dl.p_model, dl.y, cfg.calib_edges)
            ll, llb = logloss(dl.p_model, dl.y), logloss(dl.p_base[has_base], dl.y[has_base]) if has_base.any() else np.nan
            ll_m_on_b = logloss(dl.p_model[has_base], dl.y[has_base]) if has_base.any() else np.nan
            row = dict(market=market, line=line, n=len(dl), logloss=ll, brier=brier(dl.p_model, dl.y),
                       n_baseline=int(has_base.sum()), logloss_model_on_base_rows=ll_m_on_b,
                       logloss_base=llb,
                       brier_base=brier(dl.p_base[has_base], dl.y[has_base]) if has_base.any() else np.nan,
                       baseline=" + ".join(sorted(dl.baseline.dropna().unique())) if "baseline" in dl else "",
                       ece=ece(tab), low_sample_buckets=int(tab.low_sample.sum()),
                       worst_bucket_z=float(tab.z.abs().max()) if len(tab) else np.nan)
            row["status"] = grade(row, tab, cfg)
            summary.append(row)
            tables[(market, line)] = tab
    return pd.DataFrame(summary), tables


def grade(row, tab, cfg) -> str:
    if not np.isnan(row["logloss_base"]) and row["logloss_model_on_base_rows"] >= row["logloss_base"]:
        return "DROP (no better than baseline)"
    big = tab[(tab.n >= cfg.min_bucket_n) & (tab.z.abs() > 3) & (tab.gap.abs() > 0.02)]
    if row["ece"] > cfg.max_ece or len(big):
        return "DOWNWEIGHT (calibration)"
    return "OK"


def flagged_bets(preds: pd.DataFrame, odds: pd.DataFrame, cfg: ModelConfig, thresholds: dict | None = None,
                 bet_snapshot: str = "open") -> pd.DataFrame:
    """Every model selection with a bet-time price: edge vs no-vig, flag, CLV vs close, result."""
    thresholds = thresholds or cfg.edge_threshold
    if bet_snapshot not in set(odds.snapshot) and "bet" in set(odds.snapshot):
        bet_snapshot = "bet"
    bet = novig_table(odds, cfg, bet_snapshot)
    close = novig_table(odds, cfg, "close")
    if bet.empty:
        return pd.DataFrame()
    keys = ["game_id", "market", "selection", "line", "player_id"]
    p = preds.drop(columns=[c for c in ("p_close", "p_novig") if c in preds]).copy()
    p["player_id"] = pd.to_numeric(p.get("player_id"), errors="coerce")
    m = p.merge(bet, on=keys, how="inner", suffixes=("", "_bet"))
    if not close.empty:
        m = m.merge(close[keys + ["p_novig"]].rename(columns={"p_novig": "p_close"}), on=keys, how="left")
    else:
        m["p_close"] = np.nan
    m["edge"] = m.p_model - m.p_novig
    m["threshold"] = m.market.map(thresholds).fillna(0.03)
    m["flag"] = (m.edge >= m.threshold) & (m.confirmed.astype(bool) | (not cfg.require_confirmed))
    dec = m.best_price.map(american_to_decimal)
    m["clv_prob"] = m.p_close - m.p_novig
    m["clv_ev"] = m.p_close * dec - 1
    m["profit"] = np.where(m.y == 1, dec - 1, np.where(m.y == 0, -1.0, 0.0))
    m["confidence"] = np.where(m.thin, "low", "normal")
    return m


def bet_summary(bets: pd.DataFrame) -> pd.DataFrame:
    f = bets[bets.flag & bets.y.notna()]
    if f.empty:
        return pd.DataFrame()
    return f.groupby("market").agg(bets=("edge", "size"), avg_edge=("edge", "mean"),
                                   avg_clv_prob=("clv_prob", "mean"), avg_clv_ev=("clv_ev", "mean"),
                                   pct_beat_close=("clv_prob", lambda s: float((s > 0).mean())),
                                   roi=("profit", "mean"), low_conf_share=("confidence", lambda s: float((s == "low").mean()))
                                   ).reset_index()


def tune_edge_thresholds(bets: pd.DataFrame, grid=(0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10),
                         min_bets: int = 50) -> tuple[dict, pd.DataFrame]:
    """Pick, per market, the smallest threshold that maximises mean CLV (EV at closing no-vig).

    CLV is used rather than ROI because it is far less noisy. Needs bet-time and closing prices.
    """
    rows, best = [], {}
    d = bets[bets.confirmed.astype(bool) & bets.p_close.notna()]
    for market, dm in d.groupby("market"):
        for t in grid:
            s = dm[dm.edge >= t]
            rows.append(dict(market=market, threshold=t, bets=len(s),
                             clv_ev=float(s.clv_ev.mean()) if len(s) else np.nan,
                             roi=float(s.profit.mean()) if len(s) else np.nan))
        cand = [r for r in rows if r["market"] == market and r["bets"] >= min_bets and not np.isnan(r["clv_ev"])]
        if cand:
            best[market] = max(cand, key=lambda r: (round(r["clv_ev"], 4), -r["threshold"]))["threshold"]
    return best, pd.DataFrame(rows)
