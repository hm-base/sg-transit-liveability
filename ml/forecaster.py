"""
ml/forecaster.py
================
Taxi availability forecaster using Ridge regression.
Predicts taxi count at +30, +60, +120 minutes ahead.

MLOps lifecycle:
  train()    — fit on DB history, save model to disk
  predict()  — load model, return forecasts, persist to DB
  evaluate() — compare past predictions vs actuals, write MAE/RMSE
"""
from __future__ import annotations

import logging
import pickle
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from config import cfg
from storage.database import (fetch_snapshots, fetch_predictions,
                               insert_prediction, insert_model_metrics)

log = logging.getLogger(__name__)

MODEL_DIR     = Path(cfg.model_dir)
FEATURE_COLS  = [
    "hour", "minute", "weekday",
    "lag_1", "lag_2", "lag_3", "lag_5", "lag_10",
    "roll5_mean", "roll15_mean", "roll5_std",
]


def _build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["fetched_at"] = pd.to_datetime(df["fetched_at"])
    df = df.set_index("fetched_at").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df["hour"]    = df.index.hour
    df["minute"]  = df.index.minute
    df["weekday"] = df.index.weekday
    for lag in [1, 2, 3, 5, 10]:
        df[f"lag_{lag}"] = df["taxi_count"].shift(lag)
    df["roll5_mean"]  = df["taxi_count"].rolling(5,  min_periods=1).mean()
    df["roll15_mean"] = df["taxi_count"].rolling(15, min_periods=1).mean()
    df["roll5_std"]   = df["taxi_count"].rolling(5,  min_periods=1).std().fillna(0)
    return df.dropna()


class TaxiForecaster:
    def __init__(self, district: str):
        self.district = district
        self._models: dict[int, Pipeline] = {}

    def train(self, lookback_min: int = 10080) -> dict[int, float]:
        """Train one Ridge model per horizon. Returns {horizon: train_MAE}."""
        rows = fetch_snapshots(self.district, minutes=lookback_min)
        if len(rows) < 30:
            log.warning("[%s] Only %d rows — need ≥30 to train.", self.district, len(rows))
            return {}

        df    = _build_features(pd.DataFrame(rows))
        results = {}
        for h in cfg.forecast_horizons:
            df["y"] = df["taxi_count"].shift(-h)
            train   = df.dropna(subset=["y"])
            if len(train) < 20:
                continue
            X, y  = train[FEATURE_COLS].values, train["y"].values
            pipe  = Pipeline([("sc", StandardScaler()), ("ridge", Ridge(alpha=1.0))])
            pipe.fit(X, y)
            mae   = mean_absolute_error(y, pipe.predict(X))
            self._models[h] = pipe
            results[h]      = round(mae, 2)
            log.info("[%s] horizon=%dmin  MAE=%.2f  n=%d", self.district, h, mae, len(X))

        self._save()
        return results

    def predict(self) -> dict[int, float]:
        """Load model, predict all horizons, persist forecasts to DB."""
        self._load()
        rows = fetch_snapshots(self.district, minutes=60)
        if not rows:
            return {h: 0.0 for h in cfg.forecast_horizons}

        df = _build_features(pd.DataFrame(rows))
        if df.empty:
            return self._ema_fallback(pd.DataFrame(rows))

        row = df[FEATURE_COLS].iloc[[-1]].values
        out = {}
        for h in cfg.forecast_horizons:
            if h in self._models:
                val = round(max(0.0, float(self._models[h].predict(row)[0])), 1)
            else:
                val = self._ema_fallback(pd.DataFrame(rows))[h]
            out[h] = val
            insert_prediction(self.district, h, val)
        return out

    def evaluate(self) -> Optional[dict]:
        """Compare predictions vs actuals. Writes metrics to DB."""
        rows = fetch_predictions(self.district, limit=200)
        df   = pd.DataFrame(rows).dropna(subset=["actual_count"])
        if len(df) < 5:
            return None
        mae  = mean_absolute_error(df.actual_count, df.predicted_count)
        rmse = mean_squared_error(df.actual_count,  df.predicted_count, squared=False)
        insert_model_metrics(self.district, mae, rmse, len(df))
        log.info("[%s] Eval — MAE=%.2f RMSE=%.2f n=%d", self.district, mae, rmse, len(df))
        return {"mae": round(mae, 3), "rmse": round(rmse, 3), "n": len(df)}

    def _model_path(self, h: int) -> Path:
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        return MODEL_DIR / f"{self.district}_{h}min_v1.pkl"

    def _save(self) -> None:
        for h, m in self._models.items():
            with open(self._model_path(h), "wb") as f:
                pickle.dump(m, f)

    def _load(self) -> None:
        if self._models:
            return
        for h in cfg.forecast_horizons:
            p = self._model_path(h)
            if p.exists():
                with open(p, "rb") as f:
                    self._models[h] = pickle.load(f)

    def _ema_fallback(self, df: pd.DataFrame) -> dict[int, float]:
        ema = float(df["taxi_count"].ewm(span=10).mean().iloc[-1])
        return {h: round(ema, 1) for h in cfg.forecast_horizons}
