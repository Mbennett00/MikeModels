"""Prediction database (SQLite file next to the rest of the model state, synced to the data-latest release).

Tables
    predictions     one row per projection per run. Append-only: triggers block UPDATE and DELETE, so history
                    can't be rewritten. inputs_json holds the component values known at prediction time.
    results         actual outcome per (sport, game_id, projection_type, subject_id). Insert-only; recorded
                    after the game, kept separate so predictions are never touched.
    model_versions  every calibration version (baseline, applied, rejected) with weights before / after,
                    reason, sample size, and performance before / after. Append-only.

Evaluation uses the last prediction made before the game started (pre_game view), so a projection that
changed during the day is graded on what was published last before kickoff.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager

import numpy as np
import pandas as pd

FILE = "model_db.sqlite"
SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sport TEXT NOT NULL,
    pred_key TEXT NOT NULL,              -- sport|game_id|projection_type|subject_id
    source TEXT NOT NULL,                -- live | backtest (walk-forward, made with earlier data only)
    model_version TEXT NOT NULL,
    created_at TEXT NOT NULL,            -- when the projection was made (UTC ISO)
    game_start TEXT,                     -- scheduled start (UTC ISO) or the game date
    game_date TEXT NOT NULL,
    season INTEGER,
    game_id TEXT NOT NULL,
    home TEXT, away TEXT, team TEXT, opponent TEXT, is_home INTEGER,
    subject_type TEXT NOT NULL,          -- team | game | player
    subject_id TEXT NOT NULL,
    subject_name TEXT,
    projection_type TEXT NOT NULL,       -- team_goals, home_win_prob, player_sog, team_points, ...
    projection REAL NOT NULL,            -- the model's number as published (after any calibration then active)
    original REAL,                       -- the uncalibrated model's number
    confidence REAL,                     -- win probability of the projected side (0.5-1), where defined
    inputs_json TEXT                     -- component values at prediction time
);
CREATE INDEX IF NOT EXISTS ix_pred_key ON predictions(sport, pred_key);
CREATE INDEX IF NOT EXISTS ix_pred_type ON predictions(sport, projection_type, game_date);
CREATE UNIQUE INDEX IF NOT EXISTS ux_pred_backtest ON predictions(pred_key, source, model_version, created_at);
CREATE TRIGGER IF NOT EXISTS predictions_no_update BEFORE UPDATE ON predictions
    BEGIN SELECT RAISE(ABORT, 'predictions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS predictions_no_delete BEFORE DELETE ON predictions
    BEGIN SELECT RAISE(ABORT, 'predictions are immutable'); END;

CREATE TABLE IF NOT EXISTS results (
    sport TEXT NOT NULL, game_id TEXT NOT NULL, projection_type TEXT NOT NULL, subject_id TEXT NOT NULL,
    actual REAL NOT NULL, recorded_at TEXT NOT NULL,
    PRIMARY KEY (sport, game_id, projection_type, subject_id)
);
CREATE TRIGGER IF NOT EXISTS results_no_update BEFORE UPDATE ON results
    BEGIN SELECT RAISE(ABORT, 'results are immutable'); END;

CREATE TABLE IF NOT EXISTS model_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sport TEXT NOT NULL, version TEXT NOT NULL, created_at TEXT NOT NULL,
    status TEXT NOT NULL,                -- baseline | applied | rejected | insufficient
    parent TEXT, params_json TEXT, prev_params_json TEXT, reason TEXT, n_obs INTEGER,
    metrics_before_json TEXT, metrics_after_json TEXT, summary_json TEXT
);
CREATE TRIGGER IF NOT EXISTS versions_no_update BEFORE UPDATE ON model_versions
    BEGIN SELECT RAISE(ABORT, 'model versions are never overwritten'); END;
CREATE TRIGGER IF NOT EXISTS versions_no_delete BEFORE DELETE ON model_versions
    BEGIN SELECT RAISE(ABORT, 'model versions are never overwritten'); END;
"""
PRED_COLS = ["sport", "pred_key", "source", "model_version", "created_at", "game_start", "game_date", "season",
             "game_id", "home", "away", "team", "opponent", "is_home", "subject_type", "subject_id", "subject_name",
             "projection_type", "projection", "original", "confidence", "inputs_json"]


def path(site: str) -> str:
    return os.path.join(site, FILE)


@contextmanager
def connect(site: str):
    os.makedirs(site, exist_ok=True)
    con = sqlite3.connect(path(site))
    try:
        con.executescript(SCHEMA)
        yield con
        con.commit()
    finally:
        con.close()


def now_iso() -> str:
    return pd.Timestamp.now(tz="UTC").isoformat()


def key(sport, game_id, ptype, subject_id) -> str:
    return f"{sport}|{game_id}|{ptype}|{subject_id}"


def _clean(v):
    if v is None:
        return None
    if isinstance(v, (np.floating, float)):
        return None if not np.isfinite(v) else float(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (pd.Timestamp,)):
        return v.isoformat()
    return v


def add_predictions(site: str, rows: list[dict], dedupe_live: bool = True) -> int:
    """Append predictions. Live rows are skipped when the projection is unchanged since the last row for the
    same key (so six runs a day don't store six copies); backtest rows are inserted once."""
    if not rows:
        return 0
    n = 0
    with connect(site) as con:
        last = {}
        if dedupe_live:
            keys = list({r["pred_key"] for r in rows if r.get("source") == "live"})
            for i in range(0, len(keys), 500):
                part = keys[i:i + 500]
                q = f"""SELECT pred_key, projection FROM predictions WHERE id IN (
                        SELECT MAX(id) FROM predictions WHERE pred_key IN ({','.join('?' * len(part))}) GROUP BY pred_key)"""
                last.update(dict(con.execute(q, part).fetchall()))
        for r in rows:
            r = {c: _clean(r.get(c)) for c in PRED_COLS}
            if r["projection"] is None:
                continue
            if r["source"] == "live" and r["pred_key"] in last and abs(last[r["pred_key"]] - r["projection"]) < 1e-6:
                continue
            if isinstance(r["inputs_json"], dict):
                r["inputs_json"] = json.dumps({k: _clean(v) for k, v in r["inputs_json"].items()})
            cur = con.execute(f"INSERT OR IGNORE INTO predictions ({','.join(PRED_COLS)}) VALUES ({','.join('?' * len(PRED_COLS))})",
                              [r[c] for c in PRED_COLS])
            n += cur.rowcount
    return n


def add_results(site: str, rows: list[dict]) -> int:
    """Record actual outcomes (insert-only: an existing result is never changed)."""
    if not rows:
        return 0
    n = 0
    with connect(site) as con:
        for r in rows:
            if r.get("actual") is None or (isinstance(r["actual"], float) and not np.isfinite(r["actual"])):
                continue
            cur = con.execute("INSERT OR IGNORE INTO results VALUES (?,?,?,?,?,?)",
                              (r["sport"], str(r["game_id"]), r["projection_type"], str(r["subject_id"]),
                               float(r["actual"]), now_iso()))
            n += cur.rowcount
    return n


def graded(site: str, sport: str, ptype: str | None = None) -> pd.DataFrame:
    """Last pre-game prediction per key joined with its result (one row per graded projection)."""
    if not os.path.exists(path(site)):
        return pd.DataFrame()
    with connect(site) as con:
        q = """
        WITH pre AS (
            SELECT p.*, ROW_NUMBER() OVER (PARTITION BY p.pred_key ORDER BY p.created_at DESC, p.id DESC) AS rn
            FROM predictions p
            WHERE p.sport = ? {t}
              AND (p.game_start IS NULL OR p.created_at <= p.game_start OR p.source = 'backtest')
        )
        SELECT pre.*, r.actual FROM pre
        JOIN results r ON r.sport = pre.sport AND r.game_id = pre.game_id
             AND r.projection_type = pre.projection_type AND r.subject_id = pre.subject_id
        WHERE pre.rn = 1
        """.format(t="AND p.projection_type = ?" if ptype else "")
        args = [sport] + ([ptype] if ptype else [])
        d = pd.read_sql_query(q, con, params=args)
    if d.empty:
        return d
    d["game_date"] = pd.to_datetime(d.game_date)
    d["error"] = d.projection - d.actual
    d["inputs"] = d.inputs_json.map(lambda s: json.loads(s) if isinstance(s, str) and s else {})
    return d.sort_values(["game_date", "id"]).reset_index(drop=True)


def counts(site: str) -> dict:
    if not os.path.exists(path(site)):
        return {}
    with connect(site) as con:
        p = dict(con.execute("SELECT sport, COUNT(*) FROM predictions GROUP BY sport").fetchall())
        r = dict(con.execute("SELECT sport, COUNT(*) FROM results GROUP BY sport").fetchall())
    return {s: dict(predictions=p.get(s, 0), results=r.get(s, 0)) for s in set(p) | set(r)}


def predicted_games(site: str, sport: str) -> set:
    if not os.path.exists(path(site)):
        return set()
    with connect(site) as con:
        return {r[0] for r in con.execute("SELECT DISTINCT game_id FROM predictions WHERE sport=?", (sport,))}


def has_backtest(site: str, sport: str) -> bool:
    if not os.path.exists(path(site)):
        return False
    with connect(site) as con:
        return con.execute("SELECT 1 FROM predictions WHERE sport=? AND source='backtest' LIMIT 1", (sport,)).fetchone() is not None


# ---------- versions ----------

def versions(site: str, sport: str) -> list[dict]:
    if not os.path.exists(path(site)):
        return []
    with connect(site) as con:
        cur = con.execute("SELECT * FROM model_versions WHERE sport=? ORDER BY id", (sport,))
        cols = [c[0] for c in cur.description]
        out = []
        for row in cur.fetchall():
            d = dict(zip(cols, row))
            for k in ("params_json", "prev_params_json", "metrics_before_json", "metrics_after_json", "summary_json"):
                d[k.replace("_json", "")] = json.loads(d.pop(k)) if d.get(k) else None
            out.append(d)
    return out


def active(site: str, sport: str) -> dict:
    """The version in force: the latest applied (or the baseline)."""
    vs = [v for v in versions(site, sport) if v["status"] in ("applied", "baseline")]
    return vs[-1] if vs else dict(version="1.0", params={}, status="baseline")


def add_version(site: str, sport: str, version: str, status: str, params: dict, prev: dict, reason: str, n_obs: int,
                before: dict | None, after: dict | None, summary: dict | None, parent: str | None) -> None:
    with connect(site) as con:
        con.execute("""INSERT INTO model_versions (sport, version, created_at, status, parent, params_json,
                       prev_params_json, reason, n_obs, metrics_before_json, metrics_after_json, summary_json)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (sport, version, now_iso(), status, parent, json.dumps(params), json.dumps(prev), reason, int(n_obs),
                     json.dumps(before), json.dumps(after), json.dumps(summary)))


def next_version(site: str, sport: str) -> str:
    """Next number after every version ever recorded (rejected attempts keep their number too)."""
    vs = versions(site, sport) or [dict(version="1.0")]
    best = max(tuple(int(x) for x in (v["version"].split(".") + ["0"])[:2]) for v in vs)
    return f"{best[0]}.{best[1] + 1}"
