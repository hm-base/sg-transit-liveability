"""
Regression test for the fetch_snapshots/fetch_bus_arrivals window bug:
comparing SGT-offset ISO timestamps against SQLite's UTC datetime('now')
silently returned the wrong (~8h inflated) window. fetch_snapshots must
return exactly the rows within `minutes` of now, using real datetime
comparison rather than the mismatched string formats found in the DB
(mixed 'T'+offset and legacy plain space-separated rows).
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.database import init_db, fetch_snapshots

SGT = timezone(timedelta(hours=8))


def _seed(db_path, rows):
    import sqlite3
    init_db(db_path)
    con = sqlite3.connect(db_path)
    con.executemany(
        "INSERT INTO taxi_snapshots (fetched_at, district, taxi_count, flux, friction) "
        "VALUES (?, 'ang-mo-kio', ?, 0, 0)",
        rows,
    )
    con.commit()
    con.close()


def test_fetch_snapshots_excludes_rows_outside_window(tmp_path):
    db_path = tmp_path / "test.db"
    now = datetime.now(SGT)
    _seed(db_path, [
        (now.isoformat(), 10),                              # now — in window
        ((now - timedelta(minutes=30)).isoformat(), 20),    # 30min ago — in window
        ((now - timedelta(hours=5)).isoformat(), 30),        # 5h ago — outside 60min window
    ])
    rows = fetch_snapshots("ang-mo-kio", minutes=60, db_path=db_path)
    assert sorted(r["taxi_count"] for r in rows) == [10, 20]


def test_fetch_snapshots_handles_legacy_space_separated_rows(tmp_path):
    db_path = tmp_path / "test.db"
    now = datetime.now(SGT)
    legacy_recent = now.strftime("%Y-%m-%d %H:%M:%S")
    legacy_old = (now - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")
    _seed(db_path, [(legacy_recent, 40), (legacy_old, 50)])
    rows = fetch_snapshots("ang-mo-kio", minutes=60, db_path=db_path)
    assert [r["taxi_count"] for r in rows] == [40]
