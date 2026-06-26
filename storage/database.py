"""
storage/database.py
===================
SQLite persistence layer. Tables:
  taxi_snapshots  — per-district counts every 60s (for ML training)
  predictions     — model forecasts (filled in; evaluated daily)
  anomaly_alerts  — LOW_TAXI / HIGH_FLUX / BUS_GAP events
  model_metrics   — daily MAE / RMSE from evaluation job
"""
from __future__ import annotations

import sqlite3
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
            CREATE INDEX IF NOT EXISTS idx_snap ON taxi_snapshots(district, fetched_at);
            CREATE INDEX IF NOT EXISTS idx_pred ON predictions(district, created_at);
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


# ── Read ───────────────────────────────────────────────────────────────────────

def fetch_snapshots(district: str, minutes: int = 120,
                    db_path: Path = DB_PATH) -> list[dict]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT fetched_at,taxi_count,flux,friction FROM taxi_snapshots "
            "WHERE district=? AND fetched_at >= datetime('now',? || ' minutes') "
            "ORDER BY fetched_at ASC",
            (district, f"-{minutes}"),
        ).fetchall()
    return [dict(r) for r in rows]


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
