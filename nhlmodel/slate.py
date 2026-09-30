"""Price a slate: every play gets projection, model probability, fair odds, no-vig book price, edge."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .backtest import GAME_LINES, PLAYER_LINES, _goalie, game_market_probs
from .book import novig_table
from .config import ModelConfig
from .fitting import fit_params
from .params import FittedParams
from .player_model import player_market_prob, project_team_players
from .pricing import fair_american
from .ratings import build_snapshot
from .team_model import TeamModel


def season_of(date) -> int:
    d = pd.Timestamp(date)
    return d.year if d.month >= 8 else d.year - 1


def _game_prob(gp, market, selection, line):
    if market == "moneyline":
        return gp.moneyline()[selection]
    if market == "puckline":
        return gp.puckline(line, selection)
    if market == "total":
        return gp.total(line)[selection]
    if market == "team_total":
        side, ou = selection.split("_")
        return gp.team_total(side, line)[ou]
    if market == "p1_total":
        return gp.p1_total(line)[selection]
    if market == "p1_3way":
        return gp.p1_3way()[selection]
    raise ValueError(market)


def _game_projection(gp, market, selection):
    if market in ("moneyline", "puckline", "p1_3way"):
        return f"{gp.home} {gp.lam_home:.2f} - {gp.lam_away:.2f} {gp.away} (regulation goal λ)"
    if market == "total":
        return f"{float((np.arange(len(gp.total_dist())) * gp.total_dist()).sum()):.2f} goals"
    if market == "team_total":
        side = selection.split("_")[0]
        d = gp.team_total_dist(side)
        return f"{float((np.arange(len(d)) * d).sum()):.2f} goals"
    if market == "p1_total":
        h, a = np.meshgrid(np.arange(gp.p1_matrix.shape[0]), np.arange(gp.p1_matrix.shape[0]), indexing="ij")
        return f"{float(((h + a) * gp.p1_matrix).sum()):.2f} goals (P1)"
    return ""


def price_slate(tables: dict, schedule: pd.DataFrame, lineups: pd.DataFrame, odds: pd.DataFrame | None,
                cfg: ModelConfig, history_preds: dict | None = None, date=None):
    date = pd.Timestamp(date or schedule.date.min()).normalize()
    season = season_of(date)
    snap = build_snapshot(tables, date, season, cfg.half_life_games, cfg.seasons_back, cfg.toi_window)
    hp = history_preds or {}
    params = fit_params(tables, date, season, cfg, hp.get("games"), hp.get("players"), snap.league)
    tm = TeamModel(cfg, snap, params)
    rows, cons, warnings = [], [], list(params.notes)
    if not hp:
        warnings.append("no backtest predictions supplied: lam3, OT slope, rest and NB dispersion use defaults")
    for g in schedule.itertuples(index=False):
        lu = lineups[lineups.game_id == g.game_id]
        hg, hconf = _goalie(lu, g.home)
        ag, aconf = _goalie(lu, g.away)
        gp = tm.project(g.home, g.away, hg, ag, date, (hconf, aconf))
        matchup = f"{g.away} @ {g.home}"
        gflags = "; ".join(gp.flags)
        confirmed_game = hconf and aconf
        # game markets: standard lines + any line the books post
        wanted = {(m["market"], m["selection"], m["line"]) for m in game_market_probs(gp)}
        if odds is not None and len(odds):
            og = odds[(odds.game_id == g.game_id) & odds.player_id.isna()]
            for r in og.itertuples():
                sel = str(r.selection).lower()
                wanted.add((r.market, sel, float(r.line) if not pd.isna(r.line) else np.nan))
        for market, sel, line in sorted(wanted, key=lambda x: (x[0], x[1], -1e9 if pd.isna(x[2]) else x[2])):
            try:
                p = _game_prob(gp, market, sel, line)
            except (ValueError, KeyError):
                continue
            rows.append(dict(game_id=g.game_id, matchup=matchup, market=market, selection=sel, line=line,
                             player_id=np.nan, player="", projection=_game_projection(gp, market, sel),
                             p_model=p, confirmed=confirmed_game, player_confirmed=True,
                             goalies_confirmed=confirmed_game, flags=gflags))
        for side, team in (("home", g.home), ("away", g.away)):
            df, rep = project_team_players(tm, gp, side, lu[lu.team == team], params, cfg)
            cons.append(dict(game_id=g.game_id, **rep))
            for pr in df.to_dict("records"):
                lines = {m: set(v) for m, v in PLAYER_LINES.items()}
                if odds is not None and len(odds):
                    po = odds[(odds.game_id == g.game_id) & (odds.player_id == pr["player_id"])]
                    for r in po.itertuples():
                        lines.setdefault(r.market, set()).add(float(r.line))
                for market, lns in lines.items():
                    lam = pr[{"goals": "lam_goals", "sog": "lam_sog", "assists": "lam_ast", "points": "lam_pts"}[market]]
                    for ln in sorted(lns):
                        p_over = player_market_prob(pr, market, ln, params)
                        for sel, p in (("over", p_over), ("under", 1 - p_over)):
                            rows.append(dict(game_id=g.game_id, matchup=matchup, market=market, selection=sel,
                                             line=ln, player_id=pr["player_id"], player=pr["name"],
                                             projection=f"{lam:.3f}", p_model=p, confirmed=pr["confirmed"] and confirmed_game,
                                             player_confirmed=pr["confirmed"], goalies_confirmed=confirmed_game,
                                             flags="; ".join(x for x in (pr["flags"], gflags) if x)))
    out = pd.DataFrame(rows)
    out["fair_odds"] = out.p_model.map(fair_american)
    if odds is not None and len(odds):
        snap_name = "bet" if (odds.snapshot == "bet").any() else ("open" if (odds.snapshot == "open").any() else "close")
        book = novig_table(odds, cfg, snap_name)
        keys = ["game_id", "market", "selection", "line", "player_id"]
        out["player_id"] = pd.to_numeric(out.player_id, errors="coerce")
        out = out.merge(book[keys + ["p_novig", "best_price", "n_books", "thin"]], on=keys, how="left")
    else:
        out["p_novig"], out["best_price"], out["n_books"], out["thin"] = np.nan, np.nan, 0, True
        warnings.append("no odds supplied: book no-vig price and edge are blank")
    out["book_novig_odds"] = out.p_novig.map(lambda p: fair_american(p) if not pd.isna(p) else np.nan)
    out["edge"] = out.p_model - out.p_novig
    out["threshold"] = out.market.map(cfg.edge_threshold).fillna(0.03)
    out["flag"] = (out.edge >= out.threshold) & (out.confirmed | (not cfg.require_confirmed))
    out["confidence"] = np.where(out.thin.fillna(True).astype(bool) | ~out.confirmed, "low", "normal")
    return out, pd.DataFrame(cons), warnings, params
