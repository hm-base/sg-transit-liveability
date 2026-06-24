"""
hdb/geocoder.py
===============
Geocodes all unique HDB block+street addresses using OneMap Search API
with authentication token for higher rate limits and better accuracy.

Run once:
    python hdb/geocoder.py

Safe to re-run — skips already cached addresses.
Requires ONEMAP_TOKEN environment variable.
"""
from __future__ import annotations

import os
import re
import time
import requests
import duckdb
from pathlib import Path

DB_PATH    = Path("data/hdb.duckdb")
ONEMAP_URL = "https://www.onemap.gov.sg/api/common/elastic/search"


def get_token() -> str:
    token = os.environ.get("ONEMAP_TOKEN", "")
    if not token:
        print("⚠️  ONEMAP_TOKEN not set — running without auth (lower rate limits)")
    return token


def geocode_address(block: str, street: str, token: str = "") -> tuple:
    """
    Search OneMap with multiple query formats.
    Uses auth token if available for better results.
    Returns (latitude, longitude, postal_code) or (None, None, None).
    """
    headers = {"Authorization": token} if token else {}

    # Try formats from most to least specific
    queries = [
        f"{block} {street}",     # "406 ANG MO KIO AVE 10"
        f"{street} {block}",     # "ANG MO KIO AVE 10 406"
        street,                  # just street as last resort
    ]

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

            results = r.get("results", [])
            for res in results:
                lat = float(res.get("LATITUDE", 0))
                lng = float(res.get("LONGITUDE", 0))
                # Singapore bounding box check
                if 1.15 <= lat <= 1.48 and 103.6 <= lng <= 104.1:
                    postal = res.get("POSTAL", "")
                    return lat, lng, postal

        except Exception:
            pass
        time.sleep(0.1)

    return None, None, None


def run_geocoding():
    token = get_token()
    con   = duckdb.connect(str(DB_PATH))

    con.execute("""
        CREATE TABLE IF NOT EXISTS geo_cache (
            block        VARCHAR,
            street_name  VARCHAR,
            latitude     DOUBLE,
            longitude    DOUBLE,
            postal_code  VARCHAR,
            PRIMARY KEY (block, street_name)
        )
    """)

    unique = con.execute(
        "SELECT DISTINCT block, street_name FROM stg_hdb_raw"
    ).df()
    total = len(unique)

    cached_count = con.execute(
        "SELECT COUNT(*) FROM geo_cache WHERE latitude IS NOT NULL"
    ).fetchone()[0]
    print(f"Total unique addresses : {total:,}")
    print(f"Already geocoded       : {cached_count:,}")
    print(f"Need to geocode        : {total - cached_count:,}")
    print(f"Auth token             : {'✅ Set' if token else '❌ Not set'}")

    if cached_count >= total:
        print("✅ All addresses already geocoded!")
        con.close()
        return

    cached = set(map(tuple, con.execute(
        "SELECT block, street_name FROM geo_cache WHERE latitude IS NOT NULL"
    ).fetchall()))

    to_fetch = unique[
        ~unique.apply(
            lambda r: (r.block, r.street_name) in cached, axis=1
        )
    ]

    print(f"\nStarting geocoding {len(to_fetch):,} addresses...")
    print("(Ctrl+C safe — saves every 100)\n")

    success, failed = 0, 0

    for i, (_, row) in enumerate(to_fetch.iterrows()):
        lat, lng, postal = geocode_address(row.block, row.street_name, token)

        con.execute(
            "INSERT INTO geo_cache VALUES (?,?,?,?,?) ON CONFLICT DO NOTHING",
            [row.block, row.street_name, lat, lng, postal],
        )

        if lat:
            success += 1
        else:
            failed += 1

        if (i + 1) % 100 == 0:
            con.commit()
            pct     = (i + 1) / len(to_fetch) * 100
            total_f = cached_count + success
            print(f"  {i+1:,} / {len(to_fetch):,}  ({pct:.1f}%)  "
                  f"✅ {success} found  ❌ {failed} not found  "
                  f"(total: {total_f:,}/{total:,})")

        time.sleep(0.15)

    con.commit()
    con.close()

    total_found = cached_count + success
    print(f"\n✅ Geocoding complete!")
    print(f"   New finds  : {success:,}")
    print(f"   Total found: {total_found:,} / {total:,}")
    print(f"   Hit rate   : {total_found/total*100:.1f}%")


if __name__ == "__main__":
    run_geocoding()