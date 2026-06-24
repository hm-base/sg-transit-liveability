"""
config.py
=========
Central configuration for the pipeline.  All tuneable parameters live
here; the module exposes a frozen singleton ``cfg`` used by every layer.

Override any value by setting environment variables BEFORE import:
    LTA_API_KEY=<key> python -m main
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    # ── LTA DataMall ──────────────────────────────────────────────────────────
    lta_api_key: str = field(
        default_factory=lambda: os.environ.get("LTA_API_KEY", "")
    )
    lta_base_url: str = "https://datamall2.mytransport.sg/ltaodataservice"

    # ── Poll cadence (seconds) ─────────────────────────────────────────────────
    taxi_poll_interval: int = 60        # TaxiAvailability: every 60s
    bus_poll_interval: int  = 180       # BusArrivalv2: every 3 min

    # ── Coordinate reference systems ───────────────────────────────────────────
    wgs84_crs: str      = "EPSG:4326"   # GPS — input data from LTA
    singapore_crs: str  = "EPSG:3414"   # SVY21 — metric; used for buffering

    # ── Geospatial ────────────────────────────────────────────────────────────
    taxi_disappearance_buffer_m: float = 20.0   # metres

    # ── Analytics window ──────────────────────────────────────────────────────
    rolling_window_minutes: int = 15

    # ── District Connectivity Score weights ───────────────────────────────────
    bus_freq_weight:      float = 0.5
    taxi_stability_weight: float = 0.3
    taxi_friction_weight:  float = 0.2

    # ── Bus-score normalisation bounds ────────────────────────────────────────
    bus_wait_floor_min:   float = 2.0   # ≤ 2 min headway  → bus_score = 100
    bus_wait_ceiling_min: float = 30.0  # ≥ 30 min headway → bus_score = 0

    # ── HTTP client ───────────────────────────────────────────────────────────
    request_timeout:      int   = 10
    max_retries:          int   = 3
    rate_limit_backoff_s: float = 10.0
    retry_backoff_s:      float = 2.0

    # ── ML / storage (added for merged version) ───────────────────────────────
    db_path:              str   = "data/transport.db"
    model_dir:            str   = "data/models"
    forecast_horizons:    tuple = (30, 60, 120)     # minutes ahead to predict
    anomaly_sigma:        float = 2.0               # std deviations for LOW_TAXI
    anomaly_flux_thresh:  int   = 15                # abs flux to trigger HIGH_FLUX
    anomaly_bus_thresh_s: float = 480.0             # 8 min bus gap = alert


# Module-level singleton — every module does: from config import cfg
cfg = Config()
