"""
api.py
======
FastAPI app. Exposes:
  GET /evaluate          — district connectivity score
  GET /rank              — leaderboard of all known districts
  GET /predictions/{d}   — latest ML forecasts for a district
  GET /alerts            — recent anomaly alerts
  GET /health            — liveness check
  GET /dashboard         — the real, live SG Liveability dashboard (HTML page)
  GET /sg_map.html       — the interactive Leaflet map, served same-origin
                            so its own client-side fetch() calls to this API
                            work with no CORS/sandbox issues at all.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from analytics.engine import DistrictMetrics, compute_metrics
from ingestion.workers import DataStore

log = logging.getLogger(__name__)

BBox = tuple[float, float, float, float]

# Fallback hardcoded districts (used when planning areas not yet fetched)
KNOWN_DISTRICTS = {
    "marine_parade": (103.893, 103.935, 1.295, 1.316),
    "downtown_cbd":  (103.845, 103.865, 1.277, 1.295),
    "tengah":        (103.720, 103.760, 1.360, 1.390),
}


def get_all_districts() -> dict[str, tuple]:
    """
    Return all available districts as {name: bbox}.
    Uses all 55 planning areas from OneMap if available,
    falls back to hardcoded 3 districts.
    """
    try:
        from hdb.planning_areas import load_all_planning_areas
        areas = load_all_planning_areas()
        if areas:
            return {
                a["name"].title(): (a["min_lon"], a["max_lon"], a["min_lat"], a["max_lat"])
                for a in areas
            }
    except Exception:
        pass
    return KNOWN_DISTRICTS


def _slugify(name: str) -> str:
    """Same slug convention used everywhere else in the project (DB rows,
    trained model filenames, etc.)."""
    return name.lower().replace(" ", "_").replace("/", "_")


class ScoreResponse(BaseModel):
    bbox:                 tuple
    taxi_count:           int
    taxi_flux:            int
    estimated_pickups:    int
    friction_ratio:       float
    taxi_stability_score: float
    stops_in_bbox:        int
    avg_bus_headway_min:  float
    bus_frequency_score:   float
    bus_redundancy_score:  float = 0.0
    num_unique_routes:     int   = 0
    connectivity_score:    float
    verdict:               str


class RankEntry(BaseModel):
    rank:     int
    district: str
    score:    float
    verdict:  str


def evaluate_district(bbox: BBox, store: DataStore) -> DistrictMetrics:
    """Python-callable entry point (used by demo + tests)."""
    # Accumulate monitored stops across districts instead of replacing them —
    # the monitored-stops list lives only in memory (resets on every restart),
    # and previously every district switch wiped out whatever the last
    # BusWorker poll cycle was building up, so no district ever got a real
    # chance to accumulate live bus arrival data.
    from processing.spatial import filter_bus_stops_by_bbox
    stops = filter_bus_stops_by_bbox(store.get_bus_stops(), bbox)
    if not stops.empty:
        existing = store.get_monitored_stops()
        new_codes = set(stops["BusStopCode"].tolist())
        store.set_monitored_stops(existing | new_codes)
    return compute_metrics(store, bbox)


def rank_districts(store: DataStore) -> list[dict]:
    """
    Tier-1 bonus: score ALL Singapore planning areas and return sorted leaderboard.
    Uses all 55 OneMap planning areas if available, falls back to 3 hardcoded districts.

    Also registers bus stops for every district as monitored (same accumulation
    logic as evaluate_district) — since this runs on nearly every page load,
    it gets full 55-district bus coverage going within a page load or two,
    instead of requiring someone to manually click through every district.
    Trade-off worth knowing: registering ~5,000 stops citywide means each
    BusWorker poll cycle takes longer than its usual 3 minutes to complete a
    full round (more like 4-5 min) — bus data updates slightly less often,
    but across every district instead of just one.
    """
    from processing.spatial import filter_bus_stops_by_bbox
    districts = get_all_districts()
    results   = []
    all_stops_seen = store.get_monitored_stops()
    for name, bbox in districts.items():
        stops = filter_bus_stops_by_bbox(store.get_bus_stops(), bbox)
        if not stops.empty:
            all_stops_seen |= set(stops["BusStopCode"].tolist())
        m = compute_metrics(store, bbox)
        results.append({
            "district": name,
            "score":    m.connectivity_score,
            "verdict":  m.verdict,
        })
    store.set_monitored_stops(all_stops_seen)
    results.sort(key=lambda x: x["score"], reverse=True)
    for i, r in enumerate(results, 1):
        r["rank"] = i
    return results


def _build_dashboard_data(district_name: Optional[str], store: DataStore,
                           all_districts: dict[str, tuple]) -> tuple[dict, dict]:
    """Assemble every real number the dashboard page needs. Runs in-process —
    no HTTP self-calls, no timeouts, no 'is the pipeline running' guessing,
    since this function IS part of the running pipeline."""
    from storage.database import fetch_snapshots, fetch_alerts

    is_average = district_name is None or district_name not in all_districts

    if is_average:
        slugs = [_slugify(n) for n in all_districts.keys()]
        latest_counts = []
        for s in slugs:
            try:
                snaps = fetch_snapshots(s, minutes=5)
                if snaps:
                    latest_counts.append(snaps[-1]["taxi_count"])
            except Exception:
                pass
        try:
            alerts = fetch_alerts(None, limit=200)
        except Exception:
            alerts = []
        rank = rank_districts(store)
        conn_score = round(sum(r["score"] for r in rank) / len(rank)) if rank else None
        verdict = "MODERATE" if conn_score and conn_score < 80 else ("GOOD" if conn_score else None)

        data = dict(
            live_taxis=sum(latest_counts) if latest_counts else 0,
            avg_taxi=round(sum(latest_counts) / len(latest_counts), 1) if latest_counts else 0.0,
            friction=0.0, alerts=len(alerts), alerts_list=alerts[:6],
            conn_score=conn_score, verdict=verdict, price=None, bus=None, forecast={},
            local_snapshot=None,
        )
        selected_key = "average"
    else:
        bbox = all_districts[district_name]
        slug = _slugify(district_name)
        try:
            metrics = evaluate_district(bbox, store)
            bus = dict(stops_in_bbox=metrics.stops_in_bbox, avg_bus_headway_min=metrics.avg_bus_headway_min,
                       bus_frequency_score=metrics.bus_frequency_score, bus_redundancy_score=metrics.bus_redundancy_score,
                       num_unique_routes=metrics.num_unique_routes, taxi_stability_score=metrics.taxi_stability_score)
            conn_score, verdict = round(metrics.connectivity_score), metrics.verdict
        except Exception:
            bus, conn_score, verdict = None, None, None

        try:
            snaps = fetch_snapshots(slug, minutes=60)
        except Exception:
            snaps = []
        live_taxis = snaps[-1]["taxi_count"] if snaps else 0
        avg_taxi = round(sum(s["taxi_count"] for s in snaps) / len(snaps), 1) if snaps else 0.0
        friction = snaps[-1].get("friction", 0.0) if snaps else 0.0

        try:
            alerts = fetch_alerts(slug, limit=50)
        except Exception:
            alerts = []

        forecast = {}
        try:
            from ml.forecaster import TaxiForecaster
            forecast = TaxiForecaster(slug).predict()
        except Exception:
            pass

        local_snapshot = None
        try:
            from hdb.onemap_services import get_block_transport_profile
            center_lat = (bbox[2] + bbox[3]) / 2
            center_lng = (bbox[0] + bbox[1]) / 2
            local_snapshot = get_block_transport_profile(center_lat, center_lng)
        except Exception:
            pass

        price = None
        try:
            from hdb.analytics import get_town_summary
            df = get_town_summary(flat_type="4 ROOM", months=12)
            match = df[df["town"].str.lower().str.replace(" ", "_") == slug]
            if not match.empty:
                price = round(match["avg_price"].iloc[0], -3)
        except Exception:
            pass

        data = dict(live_taxis=live_taxis, avg_taxi=avg_taxi, friction=friction,
                    alerts=len(alerts), alerts_list=alerts[:6], conn_score=conn_score,
                    verdict=verdict, price=price, bus=bus, forecast=forecast,
                    local_snapshot=local_snapshot)
        selected_key = district_name

    # ── shared "extra" data (leaderboard, price tables) needed by every scope ──
    extra: dict = {}
    try:
        extra["rank"] = rank_districts(store)
    except Exception:
        extra["rank"] = []
    try:
        from hdb.analytics import get_town_summary
        extra["town_summary"] = get_town_summary(flat_type="4 ROOM", months=12)
    except Exception:
        extra["town_summary"] = None
    try:
        from hdb.analytics import get_available_towns, get_price_trend
        towns = get_available_towns()
        trend_town = towns[0] if towns else None
        extra["trend_town"] = trend_town
        extra["price_trend"] = get_price_trend(trend_town, "4 ROOM") if trend_town else None
    except Exception:
        extra["price_trend"] = None
        extra["trend_town"] = ""
    if extra.get("rank") and extra.get("town_summary") is not None:
        try:
            from hdb.analytics import get_value_for_money
            conn_scores = {r["district"]: r["score"] for r in extra["rank"]}
            extra["vfm"] = get_value_for_money(extra["town_summary"], conn_scores)
        except Exception:
            extra["vfm"] = None
    else:
        extra["vfm"] = None

    if not is_average:
        try:
            from ml.extended_forecaster import DayPatternAnalyser, HourlyForecaster, PeakHourPredictor
            extra["pattern"] = DayPatternAnalyser(slug).get_pattern()
            extra["hourly_forecast"] = HourlyForecaster(slug).predict_24h()
            extra["peaks"] = PeakHourPredictor(slug).predict_peaks()
        except Exception:
            import pandas as pd
            extra["pattern"] = pd.DataFrame()
            extra["hourly_forecast"] = pd.DataFrame()
            extra["peaks"] = []

    return data, extra


def create_app(store: DataStore) -> FastAPI:
    app = FastAPI(
        title="SG District Transport Evaluator",
        description="Real-time transit friction scoring for Singapore districts.",
        version="2.0.0",
    )
    # The dashboard map is also embedded as an iframe inside Streamlit
    # (localhost:8502 / srcdoc), so its fetches to this API are cross-origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/evaluate", response_model=ScoreResponse)
    def api_evaluate(min_lon: float, max_lon: float,
                     min_lat: float, max_lat: float):
        """
        Evaluate a district bounding box.
        Example (Marine Parade):
          GET /evaluate?min_lon=103.893&max_lon=103.935&min_lat=1.295&max_lat=1.316
        """
        bbox    = (min_lon, max_lon, min_lat, max_lat)
        metrics = evaluate_district(bbox, store)
        return ScoreResponse(
            bbox=bbox,
            taxi_count=metrics.taxi_count,
            taxi_flux=metrics.taxi_flux,
            estimated_pickups=metrics.estimated_pickups,
            friction_ratio=metrics.friction_ratio,
            taxi_stability_score=metrics.taxi_stability_score,
            stops_in_bbox=metrics.stops_in_bbox,
            avg_bus_headway_min=metrics.avg_bus_headway_min,
            bus_frequency_score=metrics.bus_frequency_score,
            connectivity_score=metrics.connectivity_score,
            bus_redundancy_score=metrics.bus_redundancy_score,
            num_unique_routes=metrics.num_unique_routes,
            verdict=metrics.verdict,
        )

    @app.get("/planning_areas.geojson")
    def serve_planning_areas_geojson():
        """Real Master Plan 2019 planning area boundaries (data.gov.sg) —
        used by sg_map.html to draw actual district shapes instead of
        crude bounding-box rectangles."""
        geo_path = Path(__file__).parent / "dashboard" / "planning_areas.geojson"
        if not geo_path.exists():
            return HTMLResponse('{"type":"FeatureCollection","features":[]}',
                               media_type="application/json", status_code=404)
        return HTMLResponse(geo_path.read_text(encoding="utf-8"), media_type="application/json")

    @app.get("/districts")
    def api_districts():
        """All known districts as {name: [min_lat, min_lon, max_lat, max_lon]} —
        used by sg_map.html to draw all 55 real planning areas instead of the
        3 hardcoded placeholder boxes it shipped with."""
        districts = get_all_districts()
        return {
            name: [bbox[2], bbox[0], bbox[3], bbox[1]]  # convert (min_lon,max_lon,min_lat,max_lat) -> [minLat,minLon,maxLat,maxLon]
            for name, bbox in districts.items()
        }

    @app.get("/rank", response_model=list[RankEntry])
    def api_rank():
        """Return connectivity leaderboard for all known districts."""
        return [RankEntry(**r) for r in rank_districts(store)]

    @app.get("/predictions/{district}")
    def api_predictions(district: str, limit: int = 10):
        from storage.database import fetch_predictions
        return fetch_predictions(district, limit=limit)

    @app.get("/alerts")
    def api_alerts(district: Optional[str] = None, limit: int = 20):
        from storage.database import fetch_alerts
        return fetch_alerts(district, limit=limit)

    @app.get("/forecast/24h/{district}")
    def forecast_24h(district: str):
        """24-hour hourly taxi forecast for a district."""
        from ml.extended_forecaster import HourlyForecaster
        hf  = HourlyForecaster(district)
        df  = hf.predict_24h()
        if df.empty:
            return {"error": "No data available"}
        return df.to_dict(orient="records")

    @app.get("/forecast/peaks/{district}")
    def forecast_peaks(district: str, days_ahead: int = 1):
        """Peak hour predictions for tomorrow."""
        from ml.extended_forecaster import PeakHourPredictor
        ph = PeakHourPredictor(district)
        return ph.predict_peaks(days_ahead=days_ahead)

    @app.get("/forecast/pattern/{district}")
    def day_pattern(district: str):
        """Day of week × hour heatmap pattern."""
        from ml.extended_forecaster import DayPatternAnalyser
        da = DayPatternAnalyser(district)
        df = da.get_pattern()
        if df.empty:
            return {"error": "No data available"}
        return {
            "pattern": df.to_dict(orient="records"),
            "best_times":  da.best_times(),
            "worst_times": da.worst_times(),
        }

    @app.get("/forecast/price/{town}")
    def price_forecast(town: str, flat_type: str = "4 ROOM", months: int = 6):
        """HDB resale price forecast using Prophet/linear regression."""
        from ml.extended_forecaster import HDBPriceForecaster
        hpf     = HDBPriceForecaster(town, flat_type)
        summary = hpf.summary()
        if not summary:
            return {"error": "Insufficient price history"}
        return summary

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard(district: Optional[str] = None):
        """The real, live SG Liveability dashboard — a genuine HTML page with
        real numbers baked in server-side. No Streamlit involved at all.
        Switch districts via ?district=Ang%20Mo%20Kio (the page's own
        dropdown does this for you)."""
        from dashboard.render import build_full_page
        all_districts = get_all_districts()
        names = sorted(all_districts.keys())
        data, extra = _build_dashboard_data(district, store, all_districts)
        selected_key = district if (district and district in all_districts) else "average"
        html = build_full_page(selected_key, data, extra, names)
        return HTMLResponse(html)

    @app.get("/sg_map.html", response_class=HTMLResponse)
    def serve_map():
        """Serves the real Leaflet map same-origin, so its own client-side
        fetch() calls back to this API work with zero CORS/iframe-sandbox
        issues — that's what kept silently breaking it inside Streamlit."""
        map_path = Path(__file__).parent / "dashboard" / "sg_map.html"
        if not map_path.exists():
            return HTMLResponse("<h3>dashboard/sg_map.html not found.</h3>", status_code=404)
        return HTMLResponse(map_path.read_text(encoding="utf-8"))

    @app.get("/health")
    def health():
        return {"status": "ok", "snapshots": len(store.taxi_snapshots)}

    return app
