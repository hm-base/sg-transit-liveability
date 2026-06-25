"""
airflow/dags/sg_transit_pipeline.py
=====================================
Apache Airflow DAG for the SG Transit Liveability pipeline.

Replaces APScheduler with proper workflow orchestration:

DAG 1: daily_model_pipeline (runs at 08:00 SGT)
  ┌─────────────────────────────────────────────────────┐
  │                                                     │
  │  check_data_quality → train_models → evaluate_models│
  │         ↓                                           │
  │  generate_extended_forecasts                        │
  │         ↓                                           │
  │  run_anomaly_checks → send_alerts (if any)          │
  │                                                     │
  └─────────────────────────────────────────────────────┘

DAG 2: hourly_predictions (runs every 30 minutes)
  predict_taxi → check_anomalies → update_dashboard

Task dependencies ensure:
  - Models only evaluated AFTER training
  - Alerts only sent IF anomalies detected
  - Failed tasks auto-retry up to 3 times
"""
from __future__ import annotations

import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.empty import EmptyOperator

# ── Default args ───────────────────────────────────────────────────────────────
DEFAULT_ARGS = {
    "owner":            "sg_transit",
    "depends_on_past":  False,
    "retries":          3,
    "retry_delay":      timedelta(minutes=5),
    "email_on_failure": False,
}

DISTRICTS = ["marine_parade", "downtown_cbd", "tengah"]


# ── Task functions ─────────────────────────────────────────────────────────────

def task_check_data_quality(**context):
    """Check data quality before training — fail fast if data is bad."""
    from storage.database import fetch_snapshots
    issues = []
    for district in DISTRICTS:
        rows = fetch_snapshots(district, minutes=1440)
        if len(rows) < 100:
            issues.append(f"{district}: only {len(rows)} rows (need ≥100)")
    if issues:
        raise ValueError(f"Data quality issues: {issues}")
    print(f"✅ Data quality OK — all districts have sufficient data")


def task_train_models(**context):
    """Retrain Ridge regression models for all districts."""
    from ml.forecaster import TaxiForecaster
    results = {}
    for district in DISTRICTS:
        f   = TaxiForecaster(district)
        res = f.train(lookback_min=1440)
        results[district] = res
        print(f"[{district}] Train results: {res}")
    context["ti"].xcom_push(key="train_results", value=results)


def task_train_hourly_models(**context):
    """Train extended hourly forecaster for all districts."""
    from ml.extended_forecaster import HourlyForecaster
    for district in DISTRICTS:
        hf  = HourlyForecaster(district)
        res = hf.train(lookback_min=1440)
        print(f"[{district}] Hourly train: {res}")


def task_evaluate_models(**context):
    """Evaluate predictions vs actuals — log MAE/RMSE."""
    from ml.forecaster import TaxiForecaster
    for district in DISTRICTS:
        metrics = TaxiForecaster(district).evaluate()
        if metrics:
            print(f"[{district}] MAE={metrics['mae']:.2f} RMSE={metrics['rmse']:.2f}")
        else:
            print(f"[{district}] No actuals to evaluate yet")


def task_generate_predictions(**context):
    """Generate fresh predictions for all districts + horizons."""
    from ml.forecaster          import TaxiForecaster
    from ml.extended_forecaster import HourlyForecaster, PeakHourPredictor

    for district in DISTRICTS:
        # Basic +30/60/120 min
        preds = TaxiForecaster(district).predict()
        print(f"[{district}] Basic predictions: {preds}")

        # 24-hour hourly
        df24 = HourlyForecaster(district).predict_24h()
        print(f"[{district}] 24hr forecast: {len(df24)} hours")

        # Peak hours
        peaks = PeakHourPredictor(district).predict_peaks()
        print(f"[{district}] Peak ratings: {[p['rating'] for p in peaks]}")


def task_check_anomalies(**context) -> str:
    """
    Check for anomalies — returns branch:
      'alert_triggered' if anomalies found
      'no_alerts'       if all clear
    """
    from ml.anomaly import AnomalyDetector
    from storage.database import fetch_snapshots

    detector   = AnomalyDetector()
    all_alerts = []

    for district in DISTRICTS:
        recent = fetch_snapshots(district, minutes=5)
        if recent:
            alerts = detector.check(
                district,
                recent[-1]["taxi_count"],
                recent[-1]["flux"],
            )
            all_alerts.extend(alerts)

    context["ti"].xcom_push(key="alert_count", value=len(all_alerts))

    if all_alerts:
        print(f"🚨 {len(all_alerts)} anomaly alerts triggered!")
        return "alert_triggered"
    else:
        print("✅ No anomalies detected")
        return "no_alerts"


def task_log_alerts(**context):
    """Log alert summary (extend to send email/Slack in production)."""
    alert_count = context["ti"].xcom_pull(key="alert_count")
    print(f"📧 Would send alert notification: {alert_count} alerts triggered")
    # In production: send email, Slack message, PagerDuty etc


def task_hdb_price_forecast(**context):
    """Run HDB price forecasts for key towns."""
    from ml.extended_forecaster import HDBPriceForecaster
    towns = ["MARINE PARADE", "TAMPINES", "PUNGGOL", "TENGAH", "WOODLANDS"]
    for town in towns:
        for flat_type in ["4 ROOM", "5 ROOM"]:
            try:
                hpf     = HDBPriceForecaster(town, flat_type)
                summary = hpf.summary()
                if summary:
                    print(f"[{town} {flat_type}] {summary['trend']} "
                          f"S${summary['current_price']:,.0f} → "
                          f"S${summary['forecast_price']:,.0f} "
                          f"({summary['change_pct']:+.1f}%)")
            except Exception as e:
                print(f"[{town}] Price forecast failed: {e}")


# ── DAG 1: Daily model pipeline ────────────────────────────────────────────────

with DAG(
    dag_id="sg_transit_daily_pipeline",
    description="Daily model training, evaluation and forecasting",
    default_args=DEFAULT_ARGS,
    schedule_interval="5 0 * * *",   # 08:05 SGT = 00:05 UTC
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["sg_transit", "ml", "daily"],
) as daily_dag:

    start = EmptyOperator(task_id="start")
    end   = EmptyOperator(task_id="end")

    check_quality = PythonOperator(
        task_id="check_data_quality",
        python_callable=task_check_data_quality,
    )

    train = PythonOperator(
        task_id="train_models",
        python_callable=task_train_models,
    )

    train_hourly = PythonOperator(
        task_id="train_hourly_models",
        python_callable=task_train_hourly_models,
    )

    evaluate = PythonOperator(
        task_id="evaluate_models",
        python_callable=task_evaluate_models,
    )

    hdb_forecast = PythonOperator(
        task_id="hdb_price_forecast",
        python_callable=task_hdb_price_forecast,
    )

    # ── Task dependencies ──────────────────────────────────────────────────────
    # check_quality → train → [evaluate, train_hourly] → hdb_forecast → end
    start >> check_quality >> [train, train_hourly]
    train >> evaluate >> hdb_forecast >> end
    train_hourly >> end


# ── DAG 2: 30-minute predictions + anomaly check ───────────────────────────────

with DAG(
    dag_id="sg_transit_30min_predictions",
    description="Every 30 min: generate predictions and check anomalies",
    default_args=DEFAULT_ARGS,
    schedule_interval="*/30 * * * *",   # every 30 minutes
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["sg_transit", "ml", "realtime"],
) as predict_dag:

    start_p = EmptyOperator(task_id="start")
    end_p   = EmptyOperator(task_id="end", trigger_rule="none_failed_min_one_success")

    generate = PythonOperator(
        task_id="generate_predictions",
        python_callable=task_generate_predictions,
    )

    branch = BranchPythonOperator(
        task_id="check_anomalies",
        python_callable=task_check_anomalies,
    )

    alert = PythonOperator(
        task_id="alert_triggered",
        python_callable=task_log_alerts,
    )

    no_alert = EmptyOperator(task_id="no_alerts")

    # ── Task dependencies ──────────────────────────────────────────────────────
    # start → generate → branch → [alert_triggered | no_alerts] → end
    start_p >> generate >> branch
    branch >> [alert, no_alert]
    [alert, no_alert] >> end_p
