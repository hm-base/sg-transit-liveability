"""
processing/taxi.py
==================
Taxi Disappearance Engine — taken from Claude Code's version.
Uses cfg singleton for all tuneables (buffer, CRS).

Algorithm
---------
1. Convert records → WGS84 GeoDataFrame, clip to bbox.
2. Reproject both snapshots to SVY21 (EPSG:3414) — metres, not degrees.
3. Buffer every T point by cfg.taxi_disappearance_buffer_m (20 m).
4. unary_union of all buffers → single "still present" polygon.
5. T-1 points outside that polygon = estimated pickups.

Why SVY21? GPS drift in Singapore urban canyons is typically < 15 m.
A 20 m buffer absorbs noise while staying far smaller than a city block.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import geopandas as gpd
import pandas as pd

from config import cfg

log = logging.getLogger(__name__)

BBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class DisappearanceResult:
    estimated_pickups: int
    total_t_minus_1:   int
    total_t:           int
    friction_ratio:    float
    disappeared_gdf:   gpd.GeoDataFrame


def _records_to_gdf(records: list[dict], bbox: BBox | None) -> gpd.GeoDataFrame:
    if not records:
        return gpd.GeoDataFrame(
            geometry=gpd.GeoSeries([], crs=cfg.wgs84_crs), crs=cfg.wgs84_crs
        )
    df  = pd.DataFrame(records)
    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["Longitude"], df["Latitude"]),
        crs=cfg.wgs84_crs,
    )
    if bbox is not None:
        min_lon, max_lon, min_lat, max_lat = bbox
        mask = (
            gdf.geometry.x.between(min_lon, max_lon)
            & gdf.geometry.y.between(min_lat, max_lat)
        )
        gdf = gdf[mask].copy()
    return gdf


def detect_disappearances(
    t_minus_1_records: list[dict],
    t_records:         list[dict],
    bbox:              BBox | None = None,
) -> DisappearanceResult:
    """
    Identify T-1 taxis no longer present in T (estimated pickups).
    See module docstring for full algorithm.
    """
    gdf_prev = _records_to_gdf(t_minus_1_records, bbox)
    gdf_curr = _records_to_gdf(t_records, bbox)
    n_prev, n_curr = len(gdf_prev), len(gdf_curr)

    empty_gdf = gpd.GeoDataFrame(
        geometry=gpd.GeoSeries([], crs=cfg.wgs84_crs), crs=cfg.wgs84_crs
    )

    if n_prev == 0:
        return DisappearanceResult(0, 0, n_curr, 0.0, empty_gdf)

    # Reproject to SVY21 for accurate metre-based buffering
    prev_m = gdf_prev.to_crs(cfg.singapore_crs)
    curr_m = gdf_curr.to_crs(cfg.singapore_crs)

    if n_curr == 0:
        disappeared_m = prev_m.copy()
    else:
        t_buffer_union = (
            curr_m.geometry
            .buffer(cfg.taxi_disappearance_buffer_m)
            .unary_union
        )
        prev_m = prev_m.copy()
        prev_m["_still_present"] = prev_m.geometry.within(t_buffer_union)
        disappeared_m = prev_m[~prev_m["_still_present"]].drop(
            columns=["_still_present"]
        )

    disappeared_gdf = disappeared_m.to_crs(cfg.wgs84_crs)
    n_gone   = len(disappeared_gdf)
    friction = n_gone / n_curr if n_curr > 0 else 0.0

    log.debug(
        "Disappearance: %d of %d T-1 taxis vanished; T=%d; friction=%.3f",
        n_gone, n_prev, n_curr, friction,
    )
    return DisappearanceResult(n_gone, n_prev, n_curr, friction, disappeared_gdf)
