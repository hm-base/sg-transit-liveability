"""
processing/spatial.py
=====================
Bounding-box filters for taxis and bus stops.
"""
from __future__ import annotations
import geopandas as gpd
import pandas as pd
from config import cfg

BBox = tuple[float, float, float, float]

def filter_taxis_by_bbox(records: list[dict], bbox: BBox) -> list[dict]:
    min_lon, max_lon, min_lat, max_lat = bbox
    return [r for r in records
            if min_lon <= r.get('Longitude', 0) <= max_lon
            and min_lat <= r.get('Latitude', 0) <= max_lat]

def filter_bus_stops_by_bbox(stops: list[dict], bbox: BBox) -> gpd.GeoDataFrame:
    min_lon, max_lon, min_lat, max_lat = bbox
    if not stops:
        return gpd.GeoDataFrame(columns=['BusStopCode', 'geometry'], crs=cfg.wgs84_crs)
    df = pd.DataFrame(stops)
    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df['Longitude'], df['Latitude']),
        crs=cfg.wgs84_crs,
    )
    return gdf.cx[min_lon:max_lon, min_lat:max_lat].copy()
