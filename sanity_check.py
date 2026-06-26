"""
sanity_check.py
===============
System health check — runs automatically on pipeline startup.
Also callable standalone: python sanity_check.py

Checks all connections, data freshness and service availability.
Does NOT expose any API keys or secrets.
"""
import os
import sys
import requests
import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta

SGT = timezone(timedelta(hours=8))

PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "

_results = []

def check(name: str, passed: bool, detail: str = ""):
    status = PASS if passed else FAIL
    _results.append((status, name, detail))
    print(f"  {status} {name}" + (f" — {detail}" if detail else ""))

def now_sgt() -> str:
    return datetime.now(SGT).strftime("%H:%M:%S SGT")


def run_checks() -> bool:
    """
    Run all sanity checks.
    Returns True if all critical checks pass, False otherwise.
    """
    _results.clear()

    print("\n" + "=" * 55)
    print("  SG Transit Liveability — System Ready Check")
    print(f"  {datetime.now(SGT).strftime('%Y-%m-%d %H:%M:%S SGT')}")
    print("=" * 55)

    # ── 1. Environment Variables ───────────────────────────────────────────
    print("\n🔑 Environment Variables")
    lta_key    = os.environ.get("LTA_API_KEY", "")
    onemap_tok = os.environ.get("ONEMAP_TOKEN", "")
    check("LTA_API_KEY",   bool(lta_key),    "configured" if lta_key else "NOT SET — get from datamall.lta.gov.sg")
    check("ONEMAP_TOKEN",  bool(onemap_tok), "configured" if onemap_tok else "NOT SET — get from developers.onemap.gov.sg")

    # ── 2. Storage ─────────────────────────────────────────────────────────
    print("\n💾 Storage")
    try:
        con = sqlite3.connect("data/transport.db")

        # Row counts
        snap_count  = con.execute("SELECT COUNT(*) FROM taxi_snapshots").fetchone()[0]
        latest_snap = con.execute("SELECT MAX(fetched_at) FROM taxi_snapshots").fetchone()[0]
        districts   = con.execute("SELECT COUNT(DISTINCT district) FROM taxi_snapshots").fetchone()[0]
        areas       = con.execute("SELECT COUNT(*) FROM planning_areas").fetchone()[0]
        pred_count  = con.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
        latest_pred = con.execute("SELECT MAX(created_at) FROM predictions").fetchone()[0]

        check("transport.db",    snap_count > 0,
              f"{snap_count:,} rows | last write: {latest_snap[:19] if latest_snap else 'none'}")
        check("Districts active", districts >= 3,
              f"{districts}/55 districts collecting data")
        check("Planning areas",  areas == 55,
              f"{areas}/55 areas loaded")
        check("ML predictions",  pred_count > 0,
              f"{pred_count:,} predictions | last: {latest_pred[:19] if latest_pred else 'none'}")
        con.close()
    except Exception as e:
        check("transport.db", False, str(e))

    # DuckDB
    try:
        import duckdb
        con      = duckdb.connect("data/hdb.duckdb", read_only=True)
        hdb_count = con.execute("SELECT COUNT(*) FROM stg_hdb_raw").fetchone()[0]
        geo_count = con.execute("SELECT COUNT(*) FROM geo_cache WHERE latitude IS NOT NULL").fetchone()[0]
        con.close()
        check("hdb.duckdb",      hdb_count > 0,
              f"{hdb_count:,} HDB transactions | {geo_count:,} geocoded blocks")
    except Exception as e:
        check("hdb.duckdb", False, f"not found or error — {e}")

    # ML models
    model_dir = Path("data/models")
    models    = list(model_dir.glob("*.pkl")) if model_dir.exists() else []
    check("ML model files",  len(models) >= 3,
          f"{len(models)} model files in data/models/")

    # ── 3. External APIs ───────────────────────────────────────────────────
    print("\n🌐 External APIs (live ping)")

    # LTA DataMall
    try:
        if lta_key:
            t0   = datetime.now()
            resp = requests.get(
                "https://datamall2.mytransport.sg/ltaodataservice/Taxi-Availability",
                headers={"AccountKey": lta_key, "accept": "application/json"},
                timeout=10,
            )
            ms        = int((datetime.now() - t0).total_seconds() * 1000)
            taxi_live = len(resp.json().get("value", []))
            check("LTA DataMall",    resp.status_code == 200,
                  f"{taxi_live} taxis island-wide | {ms}ms | ping: {now_sgt()}")
        else:
            check("LTA DataMall", False, "skipped — LTA_API_KEY not set")
    except Exception as e:
        check("LTA DataMall", False, str(e))

    # OneMap
    try:
        if onemap_tok:
            t0   = datetime.now()
            resp = requests.get(
                "https://www.onemap.gov.sg/api/common/elastic/search",
                headers={"Authorization": onemap_tok},
                params={"searchVal": "83139", "returnGeom": "Y", "getAddrDetails": "Y"},
                timeout=15,
            )
            ms = int((datetime.now() - t0).total_seconds() * 1000)
            check("OneMap API",      resp.status_code == 200,
                  f"responding | {ms}ms | ping: {now_sgt()}")
        else:
            check("OneMap API", False, "skipped — ONEMAP_TOKEN not set")
    except Exception as e:
        check("OneMap API", False, str(e))

    # ── 4. Pipeline API ────────────────────────────────────────────────────
    print("\n🚀 Pipeline API (port 8000)")
    try:
        t0   = datetime.now()
        resp = requests.get("http://127.0.0.1:8000/health", timeout=3)
        ms   = int((datetime.now() - t0).total_seconds() * 1000)
        data = resp.json()
        check("FastAPI health",  resp.status_code == 200,
              f"snapshots={data.get('snapshots')} | {ms}ms")
    except requests.exceptions.ConnectionError:
        check("FastAPI health", True, "will start after this check ✅")
    except Exception as e:
        check("FastAPI health", False, str(e))

    # ── Summary ────────────────────────────────────────────────────────────
    print("\n" + "=" * 55)
    passed   = sum(1 for r in _results if r[0] == PASS)
    failed   = sum(1 for r in _results if r[0] == FAIL)
    total    = len(_results)
    critical = [r for r in _results if r[0] == FAIL and r[1] in
                ("LTA_API_KEY", "ONEMAP_TOKEN", "transport.db")]

    print(f"  Results: {passed}/{total} passed  |  {failed} failed")

    if failed == 0:
        print("  🎉 All systems go! Pipeline starting...")
    elif critical:
        print(f"  🚨 Critical issues found — pipeline may not work correctly!")
    else:
        print(f"  ⚠️  {failed} non-critical issue(s) — pipeline will start anyway")

    print("=" * 55 + "\n")

    return len(critical) == 0


if __name__ == "__main__":
    ok = run_checks()
    sys.exit(0 if ok else 1)
