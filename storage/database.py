"""
storage/database.py
===================
SQLite persistence layer. Tables:
  taxi_snapshots   — per-district counts every 60s (for ML training)
  predictions      — model forecasts (filled in; evaluated daily)
  anomaly_alerts   — LOW_TAXI / HIGH_FLUX / BUS_GAP events
  model_metrics    — daily MAE / RMSE from evaluation job
  bus_arrivals     — raw bus arrival snapshots per stop (NEW — previously
                     lived only in memory and was lost on every restart)
  monitored_stops  — which bus stops BusWorker should poll (NEW — persisted
                     so restarts don't reset back to "watching nothing")
"""
from __future__ import annotations

import sqlite3
import json
import logging
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta

SGT = timezone(timedelta(hours=8))
from pathlib import Path

from config import cfg

log = logging.getLogger(__name__)

DB_PATH = Path(cfg.db_path)


def init_db(db_path: Path = DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS taxi_snapshots (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                fetched_at  TEXT    NOT NULL,
                district    TEXT    NOT NULL,
                taxi_count  INTEGER NOT NULL,
                flux        REAL    DEFAULT 0,
                friction    REAL    DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS predictions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at      TEXT    NOT NULL,
                district        TEXT    NOT NULL,
                horizon_minutes INTEGER NOT NULL,
                predicted_count REAL    NOT NULL,
                actual_count    REAL,
                model_version   TEXT    DEFAULT 'v1'
            );
            CREATE TABLE IF NOT EXISTS anomaly_alerts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                triggered_at TEXT    NOT NULL,
                district     TEXT    NOT NULL,
                alert_type   TEXT    NOT NULL,
                value        REAL    NOT NULL,
                threshold    REAL    NOT NULL,
                message      TEXT
            );
            CREATE TABLE IF NOT EXISTS model_metrics (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                evaluated_at TEXT    NOT NULL,
                district     TEXT    NOT NULL,
                mae          REAL,
                rmse         REAL,
                n_samples    INTEGER
            );
            CREATE TABLE IF NOT EXISTS public_holidays (
                date    TEXT PRIMARY KEY,
                holiday TEXT
            );
            CREATE TABLE IF NOT EXISTS bus_arrivals (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                fetched_at    TEXT    NOT NULL,
                stop_code     TEXT    NOT NULL,
                services_json TEXT
            );
            CREATE TABLE IF NOT EXISTS monitored_stops (
                stop_code TEXT PRIMARY KEY,
                added_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_snap ON taxi_snapshots(district, fetched_at);
            CREATE INDEX IF NOT EXISTS idx_pred ON predictions(district, created_at);
            CREATE INDEX IF NOT EXISTS idx_bus  ON bus_arrivals(stop_code, fetched_at);
        """)
    log.info("Database ready at %s", db_path)


@contextmanager
def _connect(db_path: Path = DB_PATH):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Write ──────────────────────────────────────────────────────────────────────

def insert_snapshot(district: str, taxi_count: int,
                    flux: float = 0.0, friction: float = 0.0,
                    db_path: Path = DB_PATH) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO taxi_snapshots (fetched_at,district,taxi_count,flux,friction) "
            "VALUES (?,?,?,?,?)",
            (datetime.now(SGT).isoformat(), district, taxi_count, flux, friction),
        )


def insert_prediction(district: str, horizon: int, predicted: float,
                      version: str = "v1", db_path: Path = DB_PATH) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO predictions (created_at,district,horizon_minutes,predicted_count,model_version) "
            "VALUES (?,?,?,?,?)",
            (datetime.now(SGT).isoformat(), district, horizon, predicted, version),
        )


def insert_alert(district: str, alert_type: str, value: float,
                 threshold: float, message: str = "",
                 db_path: Path = DB_PATH) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO anomaly_alerts (triggered_at,district,alert_type,value,threshold,message) "
            "VALUES (?,?,?,?,?,?)",
            (datetime.now(SGT).isoformat(), district, alert_type, value, threshold, message),
        )


def insert_model_metrics(district: str, mae: float, rmse: float,
                         n_samples: int, db_path: Path = DB_PATH) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO model_metrics (evaluated_at,district,mae,rmse,n_samples) "
            "VALUES (?,?,?,?,?)",
            (datetime.now(SGT).isoformat(), district, mae, rmse, n_samples),
        )


def insert_bus_arrivals(stop_code: str, services: list[dict], db_path: Path = DB_PATH) -> None:
    """Persist a raw bus-arrival snapshot for one stop. Stored as JSON rather
    than parsed into individual columns — LTA's exact field names can vary,
    and this way nothing breaks if they do; downstream code parses services_json."""
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO bus_arrivals (fetched_at, stop_code, services_json) VALUES (?,?,?)",
            (datetime.now(SGT).isoformat(), stop_code, json.dumps(services)),
        )


def save_monitored_stops(codes: set[str], db_path: Path = DB_PATH) -> None:
    """Persist which stops BusWorker should be watching, so a restart doesn't
    reset back to 'watching nothing' — this was the actual root cause of
    every district showing a zeroed-out bus score after any restart."""
    now = datetime.now(SGT).isoformat()
    with _connect(db_path) as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO monitored_stops (stop_code, added_at) VALUES (?,?)",
            [(c, now) for c in codes],
        )


# ── Read ───────────────────────────────────────────────────────────────────────

def _parse_ts(s) -> datetime | None:
    """Rows are stored as datetime.now(SGT).isoformat(), but older rows used
    a plain space-separated format with no offset — parse both to a naive
    SGT datetime so callers can compare correctly regardless of format."""
    try:
        dt = datetime.fromisoformat(str(s))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(SGT).replace(tzinfo=None)
    return dt


def _window_cutoff(minutes: int) -> tuple[datetime, str]:
    """Real cutoff for exact filtering, plus a cheap date-only SQL prefilter
    that's a safe superset regardless of stored timestamp format (mixed
    'T'+offset / plain space-separated) — a bare "YYYY-MM-DD" string sorts
    before any timestamp on that date in either format. The 1-day buffer
    covers the max SGT/UTC skew (8h) plus the date boundary itself."""
    cutoff = datetime.now(SGT).replace(tzinfo=None) - timedelta(minutes=minutes)
    sql_floor = (cutoff - timedelta(days=1)).strftime("%Y-%m-%d")
    return cutoff, sql_floor


def fetch_snapshots(district: str, minutes: int = 120,
                    db_path: Path = DB_PATH) -> list[dict]:
    cutoff, sql_floor = _window_cutoff(minutes)
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT fetched_at,taxi_count,flux,friction FROM taxi_snapshots "
            "WHERE district=? AND fetched_at >= ? "
            "ORDER BY fetched_at ASC",
            (district, sql_floor),
        ).fetchall()
    out = []
    for r in rows:
        t = _parse_ts(r["fetched_at"])
        if t is not None and t >= cutoff:
            out.append(dict(r))
    return out


def fetch_predictions(district: str, limit: int = 50,
                      db_path: Path = DB_PATH) -> list[dict]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT created_at,horizon_minutes,predicted_count,actual_count "
            "FROM predictions WHERE district=? ORDER BY created_at DESC LIMIT ?",
            (district, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def fetch_alerts(district: str | None = None, limit: int = 50,
                 db_path: Path = DB_PATH) -> list[dict]:
    with _connect(db_path) as conn:
        if district:
            rows = conn.execute(
                "SELECT * FROM anomaly_alerts WHERE district=? "
                "ORDER BY triggered_at DESC LIMIT ?", (district, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM anomaly_alerts ORDER BY triggered_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
    return [dict(r) for r in rows]


def fetch_latest_metrics(db_path: Path = DB_PATH) -> list[dict]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT district,evaluated_at,mae,rmse,n_samples FROM model_metrics "
            "WHERE evaluated_at IN "
            "(SELECT MAX(evaluated_at) FROM model_metrics GROUP BY district)"
        ).fetchall()
    return [dict(r) for r in rows]


def fetch_bus_arrivals(stop_code: str, minutes: int = 60,
                       db_path: Path = DB_PATH) -> list[dict]:
    """Real persisted history for one stop — didn't exist before this change."""
    cutoff, sql_floor = _window_cutoff(minutes)
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT fetched_at, services_json FROM bus_arrivals "
            "WHERE stop_code=? AND fetched_at >= ? "
            "ORDER BY fetched_at DESC",
            (stop_code, sql_floor),
        ).fetchall()
    out = []
    for r in rows:
        t = _parse_ts(r["fetched_at"])
        if t is not None and t >= cutoff:
            out.append({"fetched_at": r["fetched_at"], "services": json.loads(r["services_json"])})
    return out


def load_monitored_stops(db_path: Path = DB_PATH) -> set[str]:
    """Reload the persisted monitored-stops list on startup — this is what
    actually stops restarts from resetting bus monitoring back to empty."""
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT stop_code FROM monitored_stops").fetchall()
    return {r["stop_code"] for r in rows}
