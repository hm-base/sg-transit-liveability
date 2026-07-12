# SG Transit Liveability — Project Handoff Summary

## Project
**GitHub:** github.com/minna711/sg-transit-liveability  
**Due:** 14 Sep 2026 — SIT SNAIC Data Engineering capstone  
**Goal:** Help Singapore flat buyers evaluate non-MRT districts using real-time LTA taxi/bus data + HDB resale prices  
**Score formula:** `(Bus×0.5) + (Taxi×0.3) − (Friction×0.2)` clamped 0–100

---

## How to Run

```powershell
cd sg-transit-liveability
.venv\Scripts\activate
python main.py                          # Terminal 1 — pipeline + API
streamlit run dashboard/app.py          # Terminal 2 — original dashboard
streamlit run dashboard/app_v2.py --server.port 8502  # Terminal 3 — new v2 design
```

---

## Full File Structure

```
sg-transit-liveability/
├── config.py                    ← frozen dataclass singleton
├── main.py                      ← orchestrator; auto-seeds 55 planning areas, runs sanity check 5s post-startup, runs initial predictions
├── api.py                       ← FastAPI endpoints
├── sanity_check.py              ← system health check (runs in background thread after API starts)
├── requirements.txt
├── Dockerfile + Dockerfile.dashboard
├── docker-compose.yml
├── .env.example
├── PROJECT_SUMMARY.md
├── README.md
│
├── ingestion/
│   ├── client.py                ← LTA HTTP client; Taxi-Availability (no v3), v3/BusArrival, BusStops
│   └── workers.py               ← TaxiWorker(60s) + BusWorker(3min); saves snapshots for ALL 55 planning areas
│
├── processing/
│   ├── taxi.py                  ← SVY21 reprojection + 20m buffer disappearance engine
│   └── spatial.py               ← bbox filters
│
├── analytics/
│   └── engine.py                ← connectivity score + CV stability + bus_redundancy_score + num_unique_routes
│
├── ml/
│   ├── forecaster.py            ← Ridge regression +30/60/120min
│   ├── extended_forecaster.py   ← HourlyForecaster + PeakHourPredictor + DayPatternAnalyser + HDBPriceForecaster(Prophet)
│   ├── anomaly.py               ← LOW_TAXI/HIGH_FLUX/BUS_GAP
│   └── batch_jobs.py            ← APScheduler: predict every 5min, train/evaluate daily 08:00 SGT; get_districts() loads all 55 dynamically
│
├── storage/
│   └── database.py              ← SQLite: stores SGT timestamps (timezone(timedelta(hours=8)))
│
├── hdb/
│   ├── geocoder.py              ← OneMap geocoding (100% hit rate with ONEMAP_TOKEN)
│   ├── analytics.py             ← DuckDB queries; get_value_for_money(transport_weight, price_weight)
│   ├── map_page.py              ← Streamlit map page; Leaflet map + postal code search + live bus arrivals
│   ├── onemap_services.py       ← postal_to_coordinates, get_nearest_mrt, get_nearest_bus_stops, get_live_bus_arrivals, get_area_transport_profile; timeout=30s
│   ├── planning_areas.py        ← 55 Singapore planning area hardcoded bboxes → transport.db; seed_planning_areas() called on every startup
│   ├── postal_generator.py      ← postal code formula
│   └── quality_check.py         ← coverage report + --fix auto-geocode missing
│
├── dashboard/
│   ├── app.py                   ← original 3-page Streamlit: Dashboard / Singapore Map / Glossary
│   ├── app_v2.py                ← NEW v2 dashboard (designer wireframe + dark navy + Space Mono font)
│   └── sg_map.html              ← React Leaflet map: OneMap tiles, MRT stations(6 lines), district boxes, click→popup card
│
└── airflow/
    └── dags/
        └── sg_transit_pipeline.py ← DAG1: daily_pipeline + DAG2: 30min_predictions
```

---

## Data Files (not in GitHub — in .gitignore)
- `data/transport.db` — SQLite live data (SGT timestamps)
- `data/hdb.duckdb` — DuckDB 233k HDB rows + geo_cache (9,712 geocoded blocks, 100%)
- `data/models/*.pkl` — trained Ridge models

---

## Key Technical Decisions

- **All timestamps stored in SGT (UTC+8)**, not UTC — critical for ML time features
- **LTA API endpoints:** `Taxi-Availability` (no v3 prefix), `v3/BusArrival`, `BusStops`
- **55 planning areas auto-seeded** on every `main.py` startup via `seed_planning_areas()`
- **`batch_jobs.py`** uses `get_districts()` which loads from DB dynamically; NO fallback to 3 districts if DB unavailable (returns empty list)
- **Predictions run every 5 minutes** (changed from 30min)
- **Sanity check** runs in background thread 5 seconds after API starts
- **No fallback districts** for map display — if no data, show no data
- **`workers.py`** saves taxi snapshots for ALL 55 districts per poll
- **`extended_forecaster.py`** SGT fix: `SGT = timezone(timedelta(hours=8))` (NOT a tuple)
- **`batch_jobs.py`** datetime: `datetime.now(SGT)` not `utcnow()` (deprecated in Python 3.14, was crashing scheduler silently)

---

## Environment Variables
- `LTA_API_KEY` — from datamall.lta.gov.sg
- `ONEMAP_TOKEN` — from developers.onemap.gov.sg

---

## API Endpoints
```
GET /evaluate?min_lon=&max_lon=&min_lat=&max_lat=
GET /rank
GET /predictions/{district}
GET /alerts
GET /forecast/24h/{district}
GET /forecast/peaks/{district}
GET /forecast/pattern/{district}
GET /forecast/price/{town}
GET /health
```

---

## ML Models
| Model | Horizons | Notes |
|-------|----------|-------|
| Ridge Regression | +30/60/120 min | MAE ~3.1/3.9/5.0 taxis |
| HourlyForecaster | 24 hours | 24 horizons |
| PeakHourPredictor | Tomorrow peaks | 7am/8am/5pm/6pm/7pm ratings |
| DayPatternAnalyser | 7×24 heatmap | best/worst times |
| HDBPriceForecaster | 6 months | Prophet/linear |

**MLOps schedule (APScheduler):**
- Every 5 min → `job_predict_and_check` (all 55 districts)
- Every 60 min → `job_extended_predictions`
- Daily 08:00 SGT → `job_train_all`
- Daily 08:05 SGT → `job_evaluate_all`
- On startup → initial prediction run immediately

---

## Dashboard v1 (app.py) — 3 pages
- **Page 1 – Dashboard:** KPIs, taxi history chart ±2σ + forecast diamonds, flux bar, bus section (5 KPIs + progress bars + formula), extended forecasts (3 tabs: 24hr chart / peak ratings / day heatmap), district leaderboard
- **Page 2 – Singapore Map:** React Leaflet + OneMap tiles, HDB price table, MRT stations (6 lines), postal code search with live bus arrivals, VFM ranking with sliders, price trend chart
- **Page 3 – Glossary:** plain English explanations

## Dashboard v2 (app_v2.py) — NEW
Dark navy `#0d1520` + Space Mono font + blue/cyan accent scheme matching designer wireframe.
- Landing page with 3-step onboarding
- Top navbar: search + district dropdown + time + weights button
- 6-KPI bar with connectivity score
- 4 tabs: Overview / 24H Forecast / Price Trends / Compare
- Transport cards (MRT / Bus Network / Taxi / Commute to CBD) with score badges
- Peak hour pills (7am ✓/✗)
- Score weights modal with Commuter/Budget Buyer/Balanced presets
- Score ring (circular) with color coding
- District leaderboard bar chart + table
- Price snapshot + VFM top 5
- Weekly taxi heatmap (24H tab)
- Compare tab side by side

---

## Sanity Check Output (runs 5s after startup)
```
=======================================================
  SG Transit Liveability — System Ready Check
  2026-06-27 HH:MM:SS SGT
=======================================================
🔑 Environment Variables
  ✅ LTA_API_KEY  — configured
  ✅ ONEMAP_TOKEN — configured
💾 Storage
  ✅ transport.db  — XX,XXX rows | last write: HH:MM:SS
  ✅ Districts      — 55/55 collecting data
  ✅ Planning areas — 55/55 loaded
  ✅ ML predictions — XXX predictions
  ✅ hdb.duckdb    — 233,479 transactions | 9,712 geocoded
  ✅ ML model files — 9 files
🌐 External APIs
  ✅ LTA DataMall  — XXX taxis | XXXms
  ✅ OneMap API    — responding | XXXms
🚀 Pipeline API (port 8000)
  ✅ FastAPI health — snapshots=XX | XXms
  ✅ Evaluate endpoint — score=XX.X
  ✅ Rank endpoint    — 55 districts
=======================================================
```

---

## TODO (remaining)
- [ ] Git LFS — push `hdb.duckdb` to GitHub (too big for regular push)
- [ ] Streamlit Cloud deploy — after Git LFS; main file: `dashboard/app.py`; add API keys as secrets
- [ ] Docker build + test — `docker-compose up --build`
- [ ] Airflow DAGs — built in `airflow/dags/sg_transit_pipeline.py`, needs docker-compose to run
- [ ] MLflow — experiment tracking (not yet implemented)
- [ ] v2 dashboard — review after designer feedback; may need further iteration
- [ ] Presentation video recording — required for submission 14 Sep 2026
- [ ] 3–5 resume bullet points PDF — required for submission
- [ ] Run UAT test plan — 71 cases in `sg_transit_UAT_test_plan.xlsx`
- [ ] `--reset` flag — wipe synthetic seed data after real data accumulates (not built)
