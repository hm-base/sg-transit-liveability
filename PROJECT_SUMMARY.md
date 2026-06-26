# 🏙️ SG Transit Liveability — Full Project Summary
## Everything we built, file by file

---

## 📁 Project Structure

```
sg-transit-liveability/
│
├── 🔧 ROOT FILES
│   ├── config.py                   ← Frozen dataclass singleton (all tunables)
│   ├── main.py                     ← Orchestrator + CLI (--seed, --demo, --live)
│   ├── api.py                      ← FastAPI REST API
│   ├── requirements.txt            ← All Python dependencies
│   ├── Dockerfile                  ← Pipeline container
│   ├── Dockerfile.dashboard        ← Dashboard container  
│   ├── docker-compose.yml          ← All 3 services (pipeline+dashboard+airflow)
│   ├── .env.example                ← API key template (never commit .env!)
│   ├── .gitignore                  ← Excludes .env, data/, .venv/
│   └── README.md                   ← Full documentation
│
├── 📥 ingestion/
│   ├── client.py                   ← LTA HTTP client (v3 API, retry, backoff)
│   └── workers.py                  ← TaxiWorker (60s) + BusWorker (3min) + DataStore (RLock)
│
├── 🗺️ processing/
│   ├── taxi.py                     ← Taxi Disappearance Engine (SVY21 + 20m buffer)
│   └── spatial.py                  ← Bounding box filters
│
├── 📊 analytics/
│   └── engine.py                   ← Connectivity score + CV stability + bus redundancy
│
├── 🤖 ml/
│   ├── forecaster.py               ← Ridge regression (+30/60/120 min)
│   ├── extended_forecaster.py      ← 24hr forecast + peak hours + day pattern + HDB price
│   ├── anomaly.py                  ← LOW_TAXI / HIGH_FLUX / BUS_GAP detection
│   └── batch_jobs.py               ← APScheduler (daily 08:00 + every 30min)
│
├── 💾 storage/
│   └── database.py                 ← SQLite (taxi_snapshots, predictions, alerts, metrics)
│
├── 🏠 hdb/
│   ├── geocoder.py                 ← OneMap geocoding (9,712 blocks, 100% hit rate)
│   ├── analytics.py                ← DuckDB price queries + VFM score
│   ├── map_page.py                 ← Streamlit map page + postal code search
│   ├── onemap_services.py          ← Nearest MRT, bus stops, routing, reverse geocode
│   ├── planning_areas.py           ← All 55 Singapore planning areas bboxes
│   ├── postal_generator.py         ← Singapore postal code formula (sector+letter+block)
│   └── quality_check.py            ← Data quality report + auto-fix
│
├── 📊 dashboard/
│   ├── app.py                      ← 3-page Streamlit dashboard
│   └── sg_map.html                 ← React Leaflet interactive map
│
├── ✈️ airflow/
│   └── dags/
│       └── sg_transit_pipeline.py  ← 2 Airflow DAGs (daily + 30min)
│
└── 💾 data/ (not in GitHub)
    ├── transport.db                ← SQLite (taxi + ML data)
    ├── hdb.duckdb                  ← DuckDB (233k HDB transactions + geocache)
    └── models/                     ← Trained ML model .pkl files
```

---

## 🔑 Environment Variables Needed

| Variable | Where to get |
|----------|-------------|
| `LTA_API_KEY` | datamall.lta.gov.sg |
| `ONEMAP_TOKEN` | developers.onemap.gov.sg |

---

## 🚀 How to Run

### Fresh setup on new machine:
```powershell
# 1. Clone
git clone https://github.com/minna711/sg-transit-liveability.git
cd sg-transit-liveability

# 2. Setup venv
uv venv
.venv\Scripts\activate       # Windows
uv pip install -r requirements.txt

# 3. Set API keys (Windows Environment Variables)
# LTA_API_KEY and ONEMAP_TOKEN

# 4. Seed database + train models
python main.py --seed

# 5. Geocode HDB (run once, ~30 min)
python hdb/geocoder.py
python hdb/quality_check.py --fix

# 6. Seed 55 planning areas
python hdb/planning_areas.py

# 7. Run pipeline
python main.py

# 8. Dashboard (new terminal)
streamlit run dashboard/app.py
```

### Docker (one command):
```powershell
cp .env.example .env   # add your keys
docker-compose up
```

---

## 🌐 Access Points

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:8501 |
| FastAPI | http://localhost:8000 |
| API docs | http://localhost:8000/docs |
| Airflow | http://localhost:8080 (admin/admin) |

---

## 📡 API Endpoints

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

## 📊 Dashboard Pages

### Page 1 — 📊 Dashboard
- KPI tiles: live taxis, mean, friction, alerts
- Taxi availability chart + ±2σ band + ML forecast diamonds
- Taxi flux bar chart
- Bus connectivity section (5 KPIs + progress bars + formula breakdown)
- 🔮 Extended Forecasts (3 tabs):
  - 📈 24-Hour Forecast chart
  - ⏰ Peak Hour Ratings (🟢🟡🔴)
  - 📅 Day Pattern Heatmap (7×24)
- District leaderboard

### Page 2 — 🗺️ Singapore Map
- React Leaflet map with OneMap tiles
- Click anywhere → connectivity score popup
- Click HDB area → full popup card
- HDB price heatmap
- MRT stations (all 6 lines)
- District boundary boxes
- Price by town table
- VFM ranking with dynamic weight sliders
- Price trend chart
- Postal code search → live bus arrivals

### Page 3 — 📖 Glossary
- Plain English explanations of every metric
- Score formula breakdown
- Alert types explained
- Data sources table

---

## 🤖 ML Models

| Model | Horizons | MAE |
|-------|----------|-----|
| Ridge Regression | +30/60/120 min | ~3.1/3.9/5.0 taxis |
| HourlyForecaster | 24 hours | — |
| PeakHourPredictor | Tomorrow peaks | — |
| DayPatternAnalyser | 7×24 heatmap | — |
| HDBPriceForecaster | 6 months | — |

### MLOps schedule:
```
Daily 08:00 SGT → retrain all models
Daily 08:05 SGT → evaluate predictions vs actuals
Every 30 min    → predict + anomaly check
Every 60 min    → extended predictions
```

---

## 📐 Score Formula

```
Connectivity Score (0–100) =
  (Bus Frequency    × 50%)
+ (Taxi Stability   × 30%)
− (Taxi Friction    × 20%)
```

---

## 🗄️ Database Tables

### SQLite (transport.db)
| Table | Purpose |
|-------|---------|
| taxi_snapshots | Live taxi counts per district |
| predictions | ML forecasts |
| anomaly_alerts | LOW_TAXI / HIGH_FLUX / BUS_GAP |
| model_metrics | Daily MAE/RMSE |
| planning_areas | 55 Singapore district bboxes |

### DuckDB (hdb.duckdb)
| Table | Purpose |
|-------|---------|
| stg_hdb_raw | 233,479 resale transactions |
| geo_cache | 9,712 geocoded HDB blocks |

---

## 🔜 Still TODO

- [ ] Git LFS for hdb.duckdb
- [x] All 55 planning areas collecting data automatically
- [x] Bus route redundancy score added
- [ ] Streamlit Cloud deployment
- [ ] Docker testing (needs Windows restart)
- [ ] MLflow experiment tracking
- [ ] Wireframe redesign (designer in progress)
- [ ] Presentation video recording (due 14 Sep 2026)
- [ ] 3-5 resume bullet points PDF

---

## 🛠️ Tech Stack

```
Python 3.14          FastAPI + Uvicorn
GeoPandas + Shapely  Streamlit + Plotly
scikit-learn         React Leaflet (HTML)
Prophet              SQLite + DuckDB
APScheduler          Apache Airflow
Docker Compose       Git + GitHub
LTA DataMall API     OneMap API
data.gov.sg          Singapore Open Data
```

---

*SIT SNAIC Data Engineering Project 2026*
*GitHub: github.com/minna711/sg-transit-liveability*
