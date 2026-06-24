# 🏙️ SG Transit Liveability Index

> Real-time neighbourhood evaluation for Singapore flat hunters — combining live taxi availability, bus frequency, and HDB resale prices into a single **District Connectivity Score**.

![Python](https://img.shields.io/badge/Python-3.14-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110-green)
![Streamlit](https://img.shields.io/badge/Streamlit-1.33-red)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## 🎯 Problem Statement

Singapore has 55+ HDB towns — but not all are MRT-connected. If you're considering moving to a non-MRT estate like **Marine Parade**, **Tengah**, or **Punggol**, how do you know if the bus and taxi connectivity is good enough?

This pipeline answers that question with **real-time data**.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     DATA INGESTION                          │
│  LTA DataMall API          data.gov.sg        OneMap API    │
│  (Taxi every 60s)     (HDB 233k records)   (Geocoding)      │
└──────────────┬──────────────────┬────────────────┬──────────┘
               │                  │                │
               ▼                  ▼                ▼
┌─────────────────────────────────────────────────────────────┐
│                       STORAGE                               │
│     SQLite (transport.db)          DuckDB (hdb.duckdb)      │
│  taxi_snapshots, predictions,    stg_hdb_raw, geo_cache     │
│  anomaly_alerts, model_metrics   (9,712 geocoded blocks)    │
└──────────────┬──────────────────┬────────────────────────────┘
               │                  │
               ▼                  ▼
┌─────────────────────────────────────────────────────────────┐
│                    PROCESSING                               │
│  Taxi Disappearance Engine     HDB Price Analytics          │
│  (SVY21 + 20m spatial buffer)  (Town summaries, VFM score)  │
└──────────────┬──────────────────┬────────────────────────────┘
               │                  │
               ▼                  ▼
┌─────────────────────────────────────────────────────────────┐
│                   ANALYTICS + ML                            │
│  District Connectivity Score   Ridge Regression Forecaster  │
│  Anomaly Detection             APScheduler (daily 08:00)    │
│  (Bus × 0.5 + Taxi × 0.3       (+30/+60/+120 min ahead)     │
│   - Friction × 0.2)                                         │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│                      SERVING                                │
│   FastAPI REST API          Streamlit Dashboard             │
│   /evaluate /rank           Live charts, forecasts,         │
│   /predictions /alerts      HDB map, glossary page          │
└─────────────────────────────────────────────────────────────┘
```

---

## ✨ Features

### 🚕 Real-time Transport Analysis
- **Taxi Disappearance Engine** — detects estimated pickups by comparing GPS snapshots with 20m spatial buffers (reprojects to SVY21 for metre accuracy)
- **Bus Reliability Factor** — average headway across all stops in district, filters anomalous gaps >120 min
- **District Connectivity Score (0–100)** — weighted formula combining bus frequency, taxi stability, and friction

### 🤖 ML Forecasting
- Ridge regression with rolling lag features predicts taxi availability at **+30, +60, +120 minutes**
- Daily model retraining at 08:00 SGT via APScheduler
- MAE ~3 taxis at +30 min horizon

### 🚨 Anomaly Detection
| Alert | Trigger |
|-------|---------|
| `LOW_TAXI` | Count drops below rolling mean − 2σ |
| `HIGH_FLUX` | Sudden surge/drain ≥ 15 taxis |
| `BUS_GAP` | Mean bus interval exceeds 8 minutes |

### 🏠 HDB Resale Integration
- 233,479 resale transactions from data.gov.sg
- 9,712 HDB blocks geocoded via OneMap API (100% hit rate with auth token)
- **Value-for-Money Score** — combines transport connectivity + affordability
- Dynamic weight sliders — adjust transport vs price importance

### 📊 Live Dashboard
- Taxi availability chart with ±2σ band and forecast diamonds
- Bus frequency scores with progress bars
- District leaderboard with real-time ranking
- Glossary page — plain English explanations of every metric
- Singapore map with HDB price heatmap (coming soon)

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- [uv](https://astral.sh/uv) package manager
- LTA DataMall API key → [datamall.lta.gov.sg](https://datamall.lta.gov.sg)
- OneMap API token → [developers.onemap.gov.sg](https://developers.onemap.gov.sg)

### Setup

```bash
# Clone the repo
git clone https://github.com/minna711/sg-transit-liveability.git
cd sg-transit-liveability

# Create virtual environment
uv venv
source .venv/bin/activate  # Mac/Linux
.venv\Scripts\activate     # Windows

# Install dependencies
uv pip install -r requirements.txt

# Set API keys (Windows)
# Add LTA_API_KEY and ONEMAP_TOKEN to Environment Variables

# Seed 7 days of synthetic history + train ML model
python main.py --seed

# Geocode HDB addresses (run once, ~30 min)
python hdb/geocoder.py
python hdb/quality_check.py --fix
```

### Run

```bash
# Terminal 1 — start pipeline + FastAPI
python main.py

# Terminal 2 — open dashboard
streamlit run dashboard/app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser!

### Offline demo (no API keys needed)

```bash
python main.py --demo
```

---

## 📁 Project Structure

```
sg-transit-liveability/
├── config.py               ← frozen dataclass singleton (all tunables)
├── main.py                 ← orchestrator + CLI entry point
├── api.py                  ← FastAPI endpoints
├── requirements.txt
│
├── ingestion/
│   ├── client.py           ← LTA HTTP client (retry + backoff)
│   └── workers.py          ← TaxiWorker + BusWorker (RLock threading)
│
├── processing/
│   ├── taxi.py             ← Taxi Disappearance Engine (SVY21 buffer)
│   └── spatial.py          ← Bounding box filters
│
├── analytics/
│   └── engine.py           ← Connectivity score + CV stability
│
├── ml/
│   ├── forecaster.py       ← Ridge regression forecaster
│   ├── anomaly.py          ← Anomaly detection (LOW_TAXI/FLUX/BUS)
│   └── batch_jobs.py       ← APScheduler daily jobs
│
├── storage/
│   └── database.py         ← SQLite persistence layer
│
├── hdb/
│   ├── geocoder.py         ← OneMap geocoding (9,712 blocks)
│   ├── analytics.py        ← DuckDB price queries + VFM score
│   ├── map_page.py         ← Streamlit map page
│   ├── postal_generator.py ← Singapore postal code formula
│   └── quality_check.py   ← Data quality report + auto-fix
│
├── dashboard/
│   └── app.py              ← Streamlit dashboard (3 pages)
│
└── sg_transit_liveability.ipynb  ← Interactive notebook walkthrough
```

---

## 🔌 API Endpoints

```
GET /evaluate?min_lon=103.893&max_lon=103.935&min_lat=1.295&max_lat=1.316
GET /rank
GET /predictions/{district}
GET /alerts?district=marine_parade
GET /health
```

### Example response `/evaluate` (Marine Parade)

```json
{
  "taxi_count": 40,
  "taxi_flux": -8,
  "estimated_pickups": 17,
  "friction_ratio": 0.425,
  "taxi_stability_score": 87.96,
  "stops_in_bbox": 131,
  "avg_bus_headway_min": 8.4,
  "bus_frequency_score": 77.3,
  "connectivity_score": 58.2,
  "verdict": "⚠️ Moderate connectivity — manageable with planning"
}
```

---

## 📊 District Connectivity Score Formula

```
Score = (Bus Frequency Score × 0.50)
      + (Taxi Stability Score × 0.30)
      − (Friction Penalty × 0.20)

Clamped to [0, 100]
```

| Score | Verdict |
|-------|---------|
| 75–100 | ✅ Well connected — comfortable without MRT |
| 50–74 | ⚠️ Moderate — manageable with planning |
| 0–49 | ❌ Poor connectivity — transit friction is high |

---

## 🗺️ Districts Monitored

| District | Type | BBox |
|----------|------|------|
| Marine Parade | Non-MRT estate | 103.893–103.935, 1.295–1.316 |
| Downtown CBD | MRT reference | 103.845–103.865, 1.277–1.295 |
| Tengah | New non-MRT town | 103.720–103.760, 1.360–1.390 |

---

## 🔜 Roadmap

- [ ] Singapore map with OneMap tiles + MRT overlay
- [ ] HDB block popup cards (price + transport + MRT distance)
- [ ] Nearest MRT API integration
- [ ] Docker + docker-compose
- [ ] Apache Airflow DAG (replace APScheduler)
- [ ] dbt transforms for HDB analytics
- [ ] All 55 Singapore planning areas

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.14 |
| Geospatial | GeoPandas, Shapely, PyProj |
| ML | scikit-learn (Ridge Regression) |
| Storage | SQLite, DuckDB |
| API | FastAPI, Uvicorn |
| Dashboard | Streamlit, Plotly |
| Scheduling | APScheduler |
| Data sources | LTA DataMall, data.gov.sg, OneMap |

---

## 📄 License

MIT License — data used under [Singapore Open Data Licence](https://datamall.lta.gov.sg/content/datamall/en/SingaporeOpenDataLicence.html)

---

*Built as a Data Engineering project — SIT SNAIC 2026*
