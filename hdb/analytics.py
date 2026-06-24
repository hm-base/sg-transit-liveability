"""
hdb/analytics.py
================
Queries hdb.duckdb to produce town-level price summaries
and per-block geocoded data for the map page.
"""
from __future__ import annotations

import duckdb
import pandas as pd
from pathlib import Path

DB_PATH = Path("data/hdb.duckdb")


def get_town_summary(flat_type: str = "4 ROOM",
                     months: int = 12) -> pd.DataFrame:
    """
    Return average resale price per town for the last N months.
    Filters by flat_type (default 4 ROOM — most common).

    Returns DataFrame with columns:
        town, avg_price, median_price, num_transactions, lat, lng
    """
    con = duckdb.connect(str(DB_PATH), read_only=True)
    df = con.execute(f"""
        SELECT
            r.town,
            ROUND(AVG(CAST(r.resale_price AS DOUBLE)), 0)    AS avg_price,
            MEDIAN(CAST(r.resale_price AS DOUBLE))           AS median_price,
            COUNT(*)                                          AS num_transactions,
            AVG(g.latitude)                                   AS lat,
            AVG(g.longitude)                                  AS lng
        FROM stg_hdb_raw r
        LEFT JOIN geo_cache g
            ON r.block = g.block AND r.street_name = g.street_name
        WHERE r.flat_type = '{flat_type}'
          AND strptime(r.month, '%Y-%m') >=
              (CURRENT_DATE - INTERVAL '{months} months')
          AND g.latitude IS NOT NULL
        GROUP BY r.town
        ORDER BY avg_price DESC
    """).df()
    con.close()
    return df


def get_block_prices(town: str = None,
                     flat_type: str = "4 ROOM",
                     months: int = 6) -> pd.DataFrame:
    """
    Return individual block-level prices with coordinates for heatmap.
    Optionally filter by town.
    """
    town_filter = f"AND r.town = '{town}'" if town else ""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    df = con.execute(f"""
        SELECT
            r.block, r.street_name, r.town,
            CAST(r.resale_price AS DOUBLE)  AS resale_price,
            r.flat_type, r.storey_range,
            g.latitude, g.longitude, g.postal_code
        FROM stg_hdb_raw r
        JOIN geo_cache g
            ON r.block = g.block AND r.street_name = g.street_name
        WHERE r.flat_type = '{flat_type}'
          AND strptime(r.month, '%Y-%m') >=
              (CURRENT_DATE - INTERVAL '{months} months')
          AND g.latitude IS NOT NULL
          {town_filter}
        ORDER BY r.resale_price DESC
    """).df()
    con.close()
    return df


def get_price_trend(town: str, flat_type: str = "4 ROOM") -> pd.DataFrame:
    """
    Return monthly average price trend for a specific town.
    Used for the price trend chart when user clicks a district.
    """
    con = duckdb.connect(str(DB_PATH), read_only=True)
    df = con.execute(f"""
        SELECT
            strptime(month, '%Y-%m')::date          AS sale_month,
            ROUND(AVG(CAST(resale_price AS DOUBLE)), 0) AS avg_price,
            COUNT(*)                                 AS num_transactions
        FROM stg_hdb_raw
        WHERE town      = '{town}'
          AND flat_type = '{flat_type}'
        GROUP BY sale_month
        ORDER BY sale_month
    """).df()
    con.close()
    return df


def get_available_towns() -> list[str]:
    """Return all unique town names in the dataset."""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    towns = con.execute(
        "SELECT DISTINCT town FROM stg_hdb_raw ORDER BY town"
    ).df()["town"].tolist()
    con.close()
    return towns


def get_flat_types() -> list[str]:
    """Return all unique flat types."""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    types = con.execute(
        "SELECT DISTINCT flat_type FROM stg_hdb_raw ORDER BY flat_type"
    ).df()["flat_type"].tolist()
    con.close()
    return types


def get_value_for_money(town_summary: pd.DataFrame,
                         connectivity_scores: dict,
                         transport_weight: float = 0.5,
                         price_weight: float = 0.5) -> pd.DataFrame:
    """
    Compute Value-for-Money score combining transport connectivity
    and HDB resale price.

    Formula:
        vfm_score = (connectivity_score * 0.5) + (affordability_score * 0.5)

    Where affordability_score = 100 * (1 - (price / max_price))
    Higher score = better value for money!

    Parameters
    ----------
    town_summary        : output of get_town_summary()
    connectivity_scores : {town_name: connectivity_score} dict
    """
    df = town_summary.copy()

    # Normalise price to 0-100 affordability score (cheaper = higher score)
    max_price = df["avg_price"].max()
    min_price = df["avg_price"].min()
    df["affordability_score"] = 100 * (1 - (df["avg_price"] - min_price) /
                                        (max_price - min_price + 1))

    # Map connectivity scores to towns
    df["connectivity_score"] = df["town"].map(
        lambda t: connectivity_scores.get(t.title(), 50.0)
    )

    # Combined Value-for-Money score
    df["vfm_score"] = (
        df["connectivity_score"] * transport_weight +
        df["affordability_score"] * price_weight
    ).round(1)

    df["vfm_verdict"] = df["vfm_score"].apply(
        lambda s: "🟢 Great value" if s >= 65
        else "🟡 Moderate value" if s >= 45
        else "🔴 Poor value"
    )

    return df.sort_values("vfm_score", ascending=False)