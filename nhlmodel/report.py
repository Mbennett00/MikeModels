"""Plain-text / markdown reports written every run."""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from .config import ModelConfig
from .pricing import format_american


def _md(df: pd.DataFrame, floatfmt=4) -> str:
    if df is None or df.empty:
        return "_(none)_\n"
    d = df.copy()
    for c in d.columns:
        if d[c].dtype.kind == "f":
            d[c] = d[c].round(floatfmt)
    cols = list(d.columns)
    lines = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    for r in d.itertuples(index=False):
        lines.append("| " + " | ".join("" if (isinstance(v, float) and np.isnan(v)) else str(v) for v in r) + " |")
    return "\n".join(lines) + "\n"


def validation_markdown(summary: pd.DataFrame, calib: dict, bets_summary: pd.DataFrame, fit_log: pd.DataFrame,
                        consistency: pd.DataFrame, cfg: ModelConfig, title: str, notes: list[str]) -> str:
    out = [f"# {title}\n"]
    if notes:
        out.append("## Assumptions / missing data\n" + "\n".join(f"- {n}" for n in notes) + "\n")
    out.append("## Market summary (walk-forward, out-of-sample)\n")
    out.append("Log loss / Brier vs naive baseline. `logloss_model_on_base_rows` is the model on exactly the rows "
               "that have a baseline, so the comparison is like for like.\n")
    out.append(_md(summary))
    warn = summary[summary.low_sample_buckets > 0]
    if len(warn):
        out.append(f"\n**WARNING: buckets with fewer than {cfg.min_bucket_n} samples** in: "
                   + ", ".join(f"{r.market} {r.line} ({r.low_sample_buckets})" for r in warn.itertuples()) + "\n")
    bad = summary[summary.status != "OK"]
    if len(bad):
        out.append("\n**Markets to drop or downweight:** "
                   + ", ".join(f"{r.market} {r.line}: {r.status}" for r in bad.itertuples()) + "\n")
    out.append("\n## Calibration tables\n")
    for (m, line), tab in calib.items():
        out.append(f"\n### {m} — line {line}\n")
        out.append(_md(tab))
    out.append("\n## Flagged bets: closing line value and results\n")
    out.append("clv_prob = closing no-vig prob minus bet-time no-vig prob; clv_ev = EV of the bet price at the "
               "closing no-vig probability.\n")
    out.append(_md(bets_summary))
    if consistency is not None and len(consistency):
        c = consistency
        out.append("\n## Consistency check (Section 7)\n")
        out.append(f"- team-games checked: {len(c)}\n"
                   f"- goals: mean gap {c.gap_goals.mean():+.2%}, |gap|>{cfg.consistency_tol:.0%} rescaled in "
                   f"{c.rescaled_goals.mean():.1%} of team-games\n"
                   f"- assists: mean gap {c.gap_ast.mean():+.2%}, rescaled in {c.rescaled_ast.mean():.1%}\n")
    if fit_log is not None and len(fit_log):
        out.append("\n## Fitted parameters over the walk-forward\n")
        out.append(_md(fit_log.drop(columns=["notes"]).astype({"rest": str})))
        last = fit_log.notes.iloc[-1]
        if last:
            out.append(f"\nLatest fit notes: {last}\n")
    return "\n".join(out)


def slate_markdown(plays: pd.DataFrame, consistency: pd.DataFrame, warnings: list[str], date) -> str:
    out = [f"# Slate {pd.Timestamp(date).date()}\n"]
    if warnings:
        out.append("## Warnings / assumptions\n" + "\n".join(f"- {w}" for w in warnings) + "\n")
    unconf = plays[~plays.confirmed.astype(bool)]
    if len(unconf):
        who = sorted(set(unconf.player[unconf.player != ""]))
        out.append(f"**Unconfirmed lineup (never flagged):** {', '.join(who) if who else 'goalie(s) unconfirmed'}\n")
    cols = ["matchup", "market", "selection", "line", "player", "projection", "p_model", "fair", "book_novig",
            "best_price", "edge", "confidence", "flags"]
    p = plays.copy()
    p["fair"] = p.fair_odds.map(format_american)
    p["book_novig"] = p.book_novig_odds.map(format_american)
    p["best_price"] = p.best_price.map(lambda x: format_american(x) if not pd.isna(x) else "n/a")
    flagged = p[p.flag].sort_values("edge", ascending=False)
    out.append(f"## Flagged plays ({len(flagged)})\n")
    out.append(_md(flagged[cols]))
    if consistency is not None and len(consistency):
        out.append("\n## Consistency check\n")
        out.append(_md(consistency[["team", "lam_team", "target_goals", "sum_player_goals", "gap_goals",
                                    "rescaled_goals", "target_ast", "sum_player_ast", "gap_ast", "rescaled_ast"]]))
    out.append("\nFull priced board (every play) is in `plays.csv`.\n")
    return "\n".join(out)


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
