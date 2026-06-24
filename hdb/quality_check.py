"""
hdb/quality_check.py
====================
Data quality checks for the HDB geocoding pipeline.
Run after geocoding to verify data integrity.

Run:
    python hdb/quality_check.py           # just check
    python hdb/quality_check.py --fix     # check + fix issues
"""
from __future__ import annotations

import os
import sys
import time
import argparse
import requests
import duckdb
import pandas as pd
from pathlib import Path

DB_PATH    = Path("data/hdb.duckdb")
ONEMAP_URL = "https://www.onemap.gov.sg/api/common/elastic/search"

# Singapore bounding box
SG_LAT_MIN, SG_LAT_MAX = 1.15, 1.48
SG_LNG_MIN, SG_LNG_MAX = 103.6, 104.1


def get_token() -> str:
    return os.environ.get("ONEMAP_TOKEN", "")


def geocode_address(block: str, street: str, token: str) -> tuple:
    """Geocode a single address using OneMap Search API."""
    headers = {"Authorization": token} if token else {}
    queries = [f"{block} {street}", f"{street} {block}", street]

    for query in queries:
        try:
            r = requests.get(
                ONEMAP_URL,
                headers=headers,
                params={
                    "searchVal":      query,
                    "returnGeom":     "Y",
                    "getAddrDetails": "Y",
                    "pageNum":        1,
                },
                timeout=10,
            ).json()
            for res in r.get("results", []):
                lat = float(res.get("LATITUDE", 0))
                lng = float(res.get("LONGITUDE", 0))
                if SG_LAT_MIN <= lat <= SG_LAT_MAX and SG_LNG_MIN <= lng <= SG_LNG_MAX:
                    return lat, lng, res.get("POSTAL", "")
        except Exception:
            pass
        time.sleep(0.1)
    return None, None, None


def run_quality_check(fix: bool = False):
    token = get_token()
    con   = duckdb.connect(str(DB_PATH))

    print("\n" + "=" * 60)
    print("  HDB GEOCODING DATA QUALITY REPORT")
    print("=" * 60 + "\n")

    # ── 1. Overall coverage ────────────────────────────────────────────────────
    total_raw = con.execute(
        "SELECT COUNT(DISTINCT block || street_name) FROM stg_hdb_raw"
    ).fetchone()[0]

    total_cached = con.execute(
        "SELECT COUNT(*) FROM geo_cache"
    ).fetchone()[0]

    has_coords = con.execute(
        "SELECT COUNT(*) FROM geo_cache WHERE latitude IS NOT NULL"
    ).fetchone()[0]

    missing_coords = con.execute(
        "SELECT COUNT(*) FROM geo_cache WHERE latitude IS NULL"
    ).fetchone()[0]

    not_in_cache = total_raw - total_cached

    print(f"📊 COVERAGE")
    print(f"  Total unique addresses : {total_raw:,}")
    print(f"  In geo_cache           : {total_cached:,}")
    print(f"  Has coordinates        : {has_coords:,} ({has_coords/total_raw*100:.1f}%)")
    print(f"  Missing coordinates    : {missing_coords:,} ({missing_coords/total_raw*100:.1f}%)")
    print(f"  Not in cache at all    : {not_in_cache:,}")

    # ── 2. Postal code coverage ────────────────────────────────────────────────
    has_postal = con.execute(
        "SELECT COUNT(*) FROM geo_cache WHERE postal_code IS NOT NULL AND postal_code != ''"
    ).fetchone()[0]

    missing_postal = con.execute(
        "SELECT COUNT(*) FROM geo_cache WHERE postal_code IS NULL OR postal_code = ''"
    ).fetchone()[0]

    print(f"\n📮 POSTAL CODES")
    print(f"  Has postal code        : {has_postal:,} ({has_postal/total_cached*100:.1f}%)")
    print(f"  Missing postal code    : {missing_postal:,} ({missing_postal/total_cached*100:.1f}%)")

    # ── 3. Suspicious coordinates ──────────────────────────────────────────────
    outside_sg = con.execute(f"""
        SELECT COUNT(*) FROM geo_cache
        WHERE latitude IS NOT NULL
          AND (latitude  < {SG_LAT_MIN} OR latitude  > {SG_LAT_MAX}
            OR longitude < {SG_LNG_MIN} OR longitude > {SG_LNG_MAX})
    """).fetchone()[0]

    print(f"\n🗺️  COORDINATE QUALITY")
    print(f"  Outside Singapore bbox : {outside_sg:,}")
    print(f"  Valid coordinates      : {has_coords - outside_sg:,}")

    # ── 4. Per-town coverage ───────────────────────────────────────────────────
    print(f"\n🏘️  COVERAGE BY TOWN")
    town_df = con.execute("""
        SELECT
            r.town,
            COUNT(DISTINCT r.block || r.street_name)                    AS total,
            COUNT(DISTINCT CASE WHEN g.latitude IS NOT NULL
                           THEN r.block || r.street_name END)           AS geocoded,
            ROUND(100.0 * COUNT(DISTINCT CASE WHEN g.latitude IS NOT NULL
                           THEN r.block || r.street_name END) /
                  COUNT(DISTINCT r.block || r.street_name), 1)          AS pct
        FROM stg_hdb_raw r
        LEFT JOIN geo_cache g
            ON r.block = g.block AND r.street_name = g.street_name
        GROUP BY r.town
        ORDER BY pct ASC
    """).df()

    for _, row in town_df.iterrows():
        emoji = "✅" if row["pct"] >= 90 else "🟡" if row["pct"] >= 70 else "🔴"
        print(f"  {emoji} {row['town']:25s} {row['geocoded']:,}/{row['total']:,} ({row['pct']}%)")

    # ── 5. Fix issues if requested ─────────────────────────────────────────────
    if fix:
        print(f"\n🔧 FIXING ISSUES...")

        # Fix 1: Remove outside-Singapore coordinates
        if outside_sg > 0:
            con.execute(f"""
                UPDATE geo_cache
                SET latitude = NULL, longitude = NULL
                WHERE latitude IS NOT NULL
                  AND (latitude  < {SG_LAT_MIN} OR latitude  > {SG_LAT_MAX}
                    OR longitude < {SG_LNG_MIN} OR longitude > {SG_LNG_MAX})
            """)
            con.commit()
            print(f"  ✅ Cleared {outside_sg} outside-Singapore coordinates")

        # Fix 2: Re-geocode missing postal codes for existing coords
        missing_postal_df = con.execute("""
            SELECT block, street_name FROM geo_cache
            WHERE latitude IS NOT NULL
              AND (postal_code IS NULL OR postal_code = '')
        """).df()

        if len(missing_postal_df) > 0 and token:
            print(f"  🔄 Re-geocoding {len(missing_postal_df):,} addresses missing postal codes...")
            fixed = 0
            for i, (_, row) in enumerate(missing_postal_df.iterrows()):
                _, _, postal = geocode_address(row["block"], row["street_name"], token)
                if postal:
                    con.execute(
                        "UPDATE geo_cache SET postal_code = ? WHERE block = ? AND street_name = ?",
                        [postal, row["block"], row["street_name"]],
                    )
                    fixed += 1
                if (i + 1) % 100 == 0:
                    con.commit()
                    print(f"    {i+1:,} / {len(missing_postal_df):,}  fixed={fixed}")
                time.sleep(0.15)
            con.commit()
            print(f"  ✅ Fixed postal codes for {fixed:,} addresses")

        # Fix 3: Re-geocode addresses with no coordinates
        no_coords_df = con.execute("""
            SELECT block, street_name FROM geo_cache
            WHERE latitude IS NULL
        """).df()

        if len(no_coords_df) > 0 and token:
            print(f"  🔄 Re-geocoding {len(no_coords_df):,} addresses with no coordinates...")
            fixed = 0
            for i, (_, row) in enumerate(no_coords_df.iterrows()):
                lat, lng, postal = geocode_address(row["block"], row["street_name"], token)
                if lat:
                    con.execute(
                        "UPDATE geo_cache SET latitude=?, longitude=?, postal_code=? "
                        "WHERE block=? AND street_name=?",
                        [lat, lng, postal, row["block"], row["street_name"]],
                    )
                    fixed += 1
                if (i + 1) % 100 == 0:
                    con.commit()
                    print(f"    {i+1:,} / {len(no_coords_df):,}  fixed={fixed}")
                time.sleep(0.15)
            con.commit()
            print(f"  ✅ Fixed coordinates for {fixed:,} addresses")

        print(f"\n✅ All fixes applied! Run quality_check.py again to verify.")

    else:
        issues = missing_coords + outside_sg + missing_postal
        if issues > 0:
            print(f"\n⚠️  Found {issues:,} issues.")
            print(f"   Run with --fix to automatically fix them:")
            print(f"   python hdb/quality_check.py --fix")
        else:
            print(f"\n✅ All checks passed! Data looks clean.")

    con.close()
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HDB Geocoding Quality Check")
    parser.add_argument("--fix", action="store_true",
                        help="Automatically fix issues found")
    args = parser.parse_args()
    run_quality_check(fix=args.fix)