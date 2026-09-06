"""
scripts/publish_local_snapshot.py
==================================
Merge recently-collected LOCAL taxi data into the `pipeline-data` branch that
GitHub Actions maintains, so a short local run (e.g. "run local for 10
minutes before a demo") ends up as fresh, dense data on GitHub — without
clobbering what GitHub Actions has already collected independently.

Why this is needed: local polls every 60s, GitHub Actions polls 3x per ~30min
(README). Both write to `taxi_snapshots.source` ('local' / 'github_actions',
see storage/database.py — auto-detected via the GITHUB_ACTIONS env var, no
call-site changes needed). They never collide as literal duplicate rows
since timestamps differ, but on overlapping time spans for the same
district, LOCAL WINS: any github_actions rows inside the exact span this
local session covers are dropped before the local rows are inserted, since
local's denser samples are strictly better information for that window.

This never touches your local data/transport.db or your current git branch —
it works in a disposable temp clone and only pushes the merged result to
`pipeline-data`.

Usage:
    python scripts/publish_local_snapshot.py              # last 60 min
    python scripts/publish_local_snapshot.py --minutes 15  # last 15 min
    python scripts/publish_local_snapshot.py --dry-run     # merge + prune, skip push

Requires: git remote 'origin' with push access (same one main.py already
pushes to).
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

SGT = timezone(timedelta(hours=8))
REPO_ROOT = Path(__file__).resolve().parent.parent
LOCAL_DB = REPO_ROOT / "data" / "transport.db"
RETENTION_DAYS = 14


def run(cmd: list[str], cwd: Path | None = None, check: bool = True):
    print("+", " ".join(cmd))
    result = subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)
    if result.stdout.strip():
        print(result.stdout.strip())
    if check and result.returncode != 0 and result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    return result


def merge_local_into(target_db: Path, cutoff_iso: str) -> int:
    """Copy local's rows (source='local') from cutoff onward into target_db,
    dropping any github_actions rows in the same district/time span first."""
    src = sqlite3.connect(f"file:{LOCAL_DB.as_posix()}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    rows = src.execute(
        "SELECT fetched_at,district,taxi_count,flux,friction FROM taxi_snapshots "
        "WHERE source='local' AND fetched_at >= ?", (cutoff_iso,),
    ).fetchall()
    src.close()

    if not rows:
        print(f"No local rows since {cutoff_iso} — nothing to merge.")
        return 0

    dst = sqlite3.connect(target_db)
    cols = {r[1] for r in dst.execute("PRAGMA table_info(taxi_snapshots)")}
    if "source" not in cols:
        dst.execute("ALTER TABLE taxi_snapshots ADD COLUMN source TEXT DEFAULT 'github_actions'")
    dst.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_snap_dedup "
                "ON taxi_snapshots(district, fetched_at, source)")

    by_district: dict[str, list[str]] = {}
    for r in rows:
        by_district.setdefault(r["district"], []).append(r["fetched_at"])

    for district, timestamps in by_district.items():
        lo, hi = min(timestamps), max(timestamps)
        dst.execute(
            "DELETE FROM taxi_snapshots WHERE source='github_actions' AND district=? "
            "AND fetched_at BETWEEN ? AND ?",
            (district, lo, hi),
        )

    dst.executemany(
        "INSERT OR IGNORE INTO taxi_snapshots "
        "(fetched_at,district,taxi_count,flux,friction,source) VALUES (?,?,?,?,?,'local')",
        [(r["fetched_at"], r["district"], r["taxi_count"], r["flux"], r["friction"]) for r in rows],
    )
    dst.commit()
    dst.close()
    print(f"Merged {len(rows)} local rows across {len(by_district)} districts "
          f"(dropped overlapping github_actions rows first)")
    return len(rows)


def prune(target_db: Path) -> None:
    """Mirrors scripts/batch_collect.py's retention logic so the branch stays small."""
    cutoff = datetime.now(SGT).replace(tzinfo=None) - timedelta(days=RETENTION_DAYS)
    con = sqlite3.connect(target_db)
    for table, col in [("taxi_snapshots", "fetched_at"),
                       ("predictions", "created_at"),
                       ("anomaly_alerts", "triggered_at"),
                       ("bus_arrivals", "fetched_at"),
                       ("model_metrics", "evaluated_at")]:
        try:
            rows = con.execute(f"SELECT rowid, {col} FROM {table}").fetchall()
        except sqlite3.OperationalError as e:
            print(f"skip prune {table}: {e}")
            continue
        stale_ids = []
        for rowid, ts in rows:
            try:
                dt = datetime.fromisoformat(str(ts))
            except (ValueError, TypeError):
                continue
            if dt.tzinfo is not None:
                dt = dt.astimezone(SGT).replace(tzinfo=None)
            if dt < cutoff:
                stale_ids.append(rowid)
        if stale_ids:
            con.executemany(f"DELETE FROM {table} WHERE rowid=?", [(i,) for i in stale_ids])
        print(f"pruned {len(stale_ids)} rows from {table}")
    con.commit()
    con.execute("VACUUM")
    con.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=int, default=60,
                    help="Publish local rows from the last N minutes (default 60)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Merge + prune but skip the actual push, just report sizes")
    args = ap.parse_args()

    if not LOCAL_DB.exists():
        sys.exit(f"No local database at {LOCAL_DB} — run the pipeline first.")

    cutoff_iso = (datetime.now(SGT) - timedelta(minutes=args.minutes)).isoformat()
    print(f"Publishing local rows since {cutoff_iso} ({args.minutes} min window)")

    with tempfile.TemporaryDirectory(prefix="sg-transit-publish-") as tmp_str:
        clone = Path(tmp_str) / "repo"
        run(["git", "clone", "--quiet", str(REPO_ROOT), str(clone)])
        origin_url = run(["git", "-C", str(REPO_ROOT), "remote", "get-url", "origin"]).stdout.strip()
        run(["git", "-C", str(clone), "remote", "set-url", "origin", origin_url])

        fetch = run(["git", "-C", str(clone), "fetch", "origin", "pipeline-data", "--depth", "1"], check=False)
        target_db = clone / "data" / "transport.db"
        if fetch.returncode == 0:
            run(["git", "-C", str(clone), "checkout", "-b", "pipeline-data-work", "origin/pipeline-data"])
        else:
            print("No existing pipeline-data branch — starting fresh from local data.")
            run(["git", "-C", str(clone), "checkout", "--orphan", "pipeline-data-work"])
            run(["git", "-C", str(clone), "rm", "-rf", "--cached", "."], check=False)
            target_db.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(LOCAL_DB, target_db)

        merge_local_into(target_db, cutoff_iso)
        prune(target_db)

        size_mb = target_db.stat().st_size / 1e6
        print(f"Result: {target_db} = {size_mb:.1f} MB")

        run(["git", "-C", str(clone), "add", "-f", "data/transport.db"])
        status = run(["git", "-C", str(clone), "status", "--porcelain"])
        if not status.stdout.strip():
            print("Nothing changed — nothing to publish.")
            return

        run(["git", "-C", str(clone),
             "-c", "user.name=local-publish",
             "-c", "user.email=local-publish@users.noreply.github.com",
             "commit", "-m", f"local publish {datetime.now(SGT).isoformat()}"])

        if args.dry_run:
            print("--dry-run: skipping push.")
            return

        run(["git", "-C", str(clone), "push", "origin", "pipeline-data-work:pipeline-data", "--force"])
        print("Published to origin/pipeline-data")


if __name__ == "__main__":
    main()
