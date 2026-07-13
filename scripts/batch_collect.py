"""
scripts/batch_collect.py
========================
One-shot pipeline batch for GitHub Actions (or any cron host).

Instead of the 24/7 service in main.py, this runs the same real pipeline
code once per invocation:

  1. poll LTA Taxi-Availability a few times (60s apart) → per-district
     snapshots for all 55 planning areas (same persistence path as
     TaxiWorker → DataStore.push_taxi_snapshot)
  2. run ML predictions + anomaly checks (ml.batch_jobs)
  3. at 08:00 SGT (or BATCH_FORCE_TRAIN=1): daily train + evaluate
  4. prune rows older than BATCH_RETENTION_DAYS and VACUUM, so the DB the
     workflow publishes to the `pipeline-data` branch stays small

Env vars:
  LTA_API_KEY           required
  BATCH_POLLS           taxi polls per run (default 3)
  BATCH_POLL_GAP_S      seconds between polls (default 60)
  BATCH_RETENTION_DAYS  rows kept in the published DB (default 14)
  BATCH_FORCE_TRAIN     "1" forces the daily train/evaluate step
"""
import os
import sys
import time
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

SGT = timezone(timedelta(hours=8))

POLLS = int(os.environ.get("BATCH_POLLS", "3"))
POLL_GAP_S = int(os.environ.get("BATCH_POLL_GAP_S", "60"))
RETENTION_DAYS = int(os.environ.get("BATCH_RETENTION_DAYS", "14"))


def main() -> None:
    from storage.database import init_db, DB_PATH
    from hdb.planning_areas import seed_planning_areas
    from ingestion.workers import DataStore
    from ingestion.client import get_paginated
    from ml import batch_jobs

    if not os.environ.get("LTA_API_KEY"):
        raise SystemExit("LTA_API_KEY is not set — aborting.")

    init_db()
    seed_planning_areas()

    store = DataStore()
    successful = 0
    for i in range(POLLS):
        records = get_paginated("Taxi-Availability")
        if records:
            store.push_taxi_snapshot(records)
            successful += 1
            print(f"poll {i + 1}/{POLLS}: {len(records)} taxis citywide")
        else:
            print(f"poll {i + 1}/{POLLS}: empty payload")
        if i < POLLS - 1:
            time.sleep(POLL_GAP_S)
    if not successful:
        raise SystemExit("No taxi data collected — check LTA_API_KEY / API status.")

    print("running predictions + anomaly checks …")
    batch_jobs.job_predict_and_check()

    now_sgt = datetime.now(SGT)
    if os.environ.get("BATCH_FORCE_TRAIN") == "1" or now_sgt.hour == 8:
        print("daily window — training + evaluating all districts …")
        batch_jobs.job_train_all()
        batch_jobs.job_evaluate_all()

    # Prune so the published DB stays a few MB, not gigabytes.
    cutoff = (now_sgt - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    con = sqlite3.connect(DB_PATH)
    for table, col in [("taxi_snapshots", "fetched_at"),
                       ("predictions", "created_at"),
                       ("anomaly_alerts", "triggered_at"),
                       ("bus_arrivals", "fetched_at"),
                       ("model_metrics", "evaluated_at")]:
        try:
            cur = con.execute(f"DELETE FROM {table} WHERE {col} < ?", (cutoff,))
            print(f"pruned {cur.rowcount} rows from {table}")
        except sqlite3.OperationalError as e:
            print(f"skip prune {table}: {e}")
    con.commit()
    con.execute("VACUUM")
    con.close()

    size_mb = Path(DB_PATH).stat().st_size / 1e6
    print(f"batch complete · {DB_PATH} = {size_mb:.1f} MB · {now_sgt.strftime('%H:%M SGT')}")


if __name__ == "__main__":
    main()
