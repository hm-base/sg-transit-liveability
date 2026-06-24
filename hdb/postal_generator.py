"""
hdb/postal_generator.py
=======================
Generate Singapore 6-digit postal codes from HDB block + street/town.

Formula: district_code (2 digits) + block_letter (1 digit) + block_number (3 digits)

Example: Punggol Blk 234E
  district = 82 (Punggol is in sector 82, district 19)
  letter E = 5  (no letter=0, A=1, B=2, C=3, D=4, E=5...)
  block 234 = 234
  postal = 825234

Source: URA List of Postal Districts (SingPost)
"""
from __future__ import annotations
import os
import re
import duckdb
import requests
import time
import pandas as pd
from pathlib import Path

DB_PATH    = Path("data/hdb.duckdb")
ONEMAP_URL = "https://www.onemap.gov.sg/api/common/elastic/search"

# ── Postal sector → district mapping ──────────────────────────────────────────
# From URA List of Postal Districts
# Key = 2-digit postal sector prefix, Value = district number
SECTOR_TO_DISTRICT = {
    "01": 1,  "02": 1,  "03": 1,  "04": 1,  "05": 1,  "06": 1,
    "07": 2,  "08": 2,
    "14": 3,  "15": 3,  "16": 3,
    "09": 4,  "10": 4,
    "11": 5,  "12": 5,  "13": 5,
    "17": 6,
    "18": 7,  "19": 7,
    "20": 8,  "21": 8,
    "22": 9,  "23": 9,
    "24": 10, "25": 10, "26": 10, "27": 10,
    "28": 11, "29": 11, "30": 11,
    "31": 12, "32": 12, "33": 12,
    "34": 13, "35": 13, "36": 13, "37": 13,
    "38": 14, "39": 14, "40": 14, "41": 14,
    "42": 15, "43": 15, "44": 15, "45": 15,
    "46": 16, "47": 16, "48": 16,
    "49": 17, "50": 17, "81": 17,
    "51": 18, "52": 18,
    "53": 19, "54": 19, "55": 19, "82": 19,
    "56": 20, "57": 20,
    "58": 21, "59": 21,
    "60": 22, "61": 22, "62": 22, "63": 22, "64": 22,
    "65": 23, "66": 23, "67": 23, "68": 23,
    "69": 24, "70": 24, "71": 24,
    "72": 25, "73": 25,
    "77": 26, "78": 26,
    "75": 27, "76": 27,
    "79": 28, "80": 28,
}

# ── Town → postal sector prefix mapping ───────────────────────────────────────
# Maps HDB town names to their primary postal sector(s)
TOWN_TO_SECTORS = {
    "ANG MO KIO":      ["56", "57"],
    "BEDOK":           ["46", "47", "48"],
    "BISHAN":          ["56", "57"],
    "BUKIT BATOK":     ["65", "66"],
    "BUKIT MERAH":     ["09", "10", "11", "14", "15"],
    "BUKIT PANJANG":   ["67", "68"],
    "BUKIT TIMAH":     ["58", "59"],
    "CENTRAL AREA":    ["01", "02", "03", "04", "05", "06"],
    "CHOA CHU KANG":   ["67", "68"],
    "CLEMENTI":        ["12", "13"],
    "GEYLANG":         ["38", "39", "40", "41"],
    "HOUGANG":         ["53", "54", "55"],
    "JURONG EAST":     ["60", "61"],
    "JURONG WEST":     ["62", "63", "64"],
    "KALLANG/WHAMPOA": ["32", "33", "34"],
    "MARINE PARADE":   ["44", "45"],
    "PASIR RIS":       ["51", "52"],
    "PUNGGOL":         ["82"],
    "QUEENSTOWN":      ["14", "15", "16"],
    "SEMBAWANG":       ["75", "76"],
    "SENGKANG":        ["54", "55"],
    "SERANGOON":       ["53", "54", "55"],
    "TAMPINES":        ["51", "52"],
    "TOA PAYOH":       ["31", "32", "33"],
    "WOODLANDS":       ["73", "75"],
    "YISHUN":          ["75", "76", "79"],
}


def parse_block(block: str) -> tuple[int, int]:
    """
    Parse a block string into (number, letter_digit).

    Examples:
        "406"  → (406, 0)
        "406A" → (406, 1)
        "10B"  → (10, 2)
        "234E" → (234, 5)
    """
    block = block.strip().upper()
    match = re.match(r"(\d+)([A-Z]?)", block)
    if not match:
        return 0, 0
    num    = int(match.group(1))
    letter = match.group(2)
    letter_digit = 0 if not letter else (ord(letter) - ord("A") + 1)
    return num, letter_digit


def generate_postal_code(block: str, town: str) -> str | None:
    """
    Generate a 6-digit Singapore postal code from block number and town.

    Formula: sector_prefix (2 digits) + letter_digit (1) + block_number (3)
    """
    town = town.strip().upper()
    sectors = TOWN_TO_SECTORS.get(town)
    if not sectors:
        return None

    block_num, letter_digit = parse_block(block)
    if block_num == 0:
        return None

    # Use first sector for this town as the prefix
    sector = sectors[0]
    postal = f"{sector}{letter_digit}{block_num:03d}"
    return postal


def geocode_by_postal(postal_code: str) -> tuple:
    """
    Use OneMap postal code search — much more accurate than free-text!
    Returns (latitude, longitude) or (None, None).
    """
    token = os.environ.get("ONEMAP_TOKEN", "")
    headers = {"Authorization": token} if token else {}
    try:
        r = requests.get(
            ONEMAP_URL,
            headers=headers,
            params={
                "searchVal":      postal_code,
                "returnGeom":     "Y",
                "getAddrDetails": "Y",
            },
            timeout=10,
        ).json()
        results = r.get("results", [])
        if not results:
            return None, None
        top = results[0]
        lat = float(top.get("LATITUDE", 0))
        lng = float(top.get("LONGITUDE", 0))
        if 1.15 <= lat <= 1.48 and 103.6 <= lng <= 104.1:
            return lat, lng
        return None, None
    except Exception:
        return None, None


def run_postal_geocoding():
    """
    Generate postal codes for all HDB addresses and geocode via OneMap.
    Much faster and more accurate than free-text search!
    """
    con = duckdb.connect(str(DB_PATH))

    # Ensure geo_cache has postal_code column
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

    # Get all unique block + town combinations
    unique = con.execute(
        "SELECT DISTINCT block, street_name, town FROM stg_hdb_raw"
    ).df()
    total = len(unique)
    print(f"Total unique addresses : {total:,}")

    # Check already cached
    cached_count = con.execute(
        "SELECT COUNT(*) FROM geo_cache WHERE latitude IS NOT NULL"
    ).fetchone()[0]
    print(f"Already geocoded       : {cached_count:,}")

    # Generate postal codes
    unique["postal_code"] = unique.apply(
        lambda r: generate_postal_code(r["block"], r["town"]), axis=1
    )
    has_postal = unique[unique["postal_code"].notna()]
    no_postal  = unique[unique["postal_code"].isna()]
    print(f"Generated postal codes : {len(has_postal):,}")
    print(f"No postal code         : {len(no_postal):,}")

    # Get already cached to skip
    cached = set(map(tuple, con.execute(
        "SELECT block, street_name FROM geo_cache WHERE latitude IS NOT NULL"
    ).fetchall()))

    to_fetch = has_postal[
        ~has_postal.apply(
            lambda r: (r["block"], r["street_name"]) in cached, axis=1
        )
    ]
    print(f"Need to geocode        : {len(to_fetch):,}")
    print(f"\nStarting postal geocoding...")
    print("(Ctrl+C safe — saves every 100)\n")

    success, failed = 0, 0

    for i, (_, row) in enumerate(to_fetch.iterrows()):
        lat, lng = geocode_by_postal(row["postal_code"])

        con.execute(
            "INSERT INTO geo_cache VALUES (?,?,?,?,?) ON CONFLICT DO NOTHING",
            [row["block"], row["street_name"], lat, lng, row["postal_code"]],
        )

        if lat:
            success += 1
        else:
            failed += 1

        if (i + 1) % 100 == 0:
            con.commit()
            pct = (i + 1) / len(to_fetch) * 100
            print(f"  {i+1:,} / {len(to_fetch):,}  ({pct:.1f}%)  "
                  f"✅ {success} found  ❌ {failed} not found")

        time.sleep(0.15)

    con.commit()
    con.close()

    total_found = cached_count + success
    print(f"\n✅ Postal geocoding complete!")
    print(f"   New finds  : {success:,}")
    print(f"   Total found: {total_found:,} / {total:,}")
    print(f"   Hit rate   : {total_found/total*100:.1f}%")


if __name__ == "__main__":
    run_postal_geocoding()