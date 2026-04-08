from __future__ import annotations

import csv
from pathlib import Path

import joblib
import numpy as np
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "Dataset" / "Predective_Forecasting.csv"
MODEL_PATH = ROOT / "ml" / "xgboost_cost_model.joblib"

EVENT_MAP = {
    "Port Congestion": 0,
    "Geopolitical Conflict (Route Diversion)": 1,
    "Severe Weather (Typhoon/Storm)": 2,
    "Unknown_Disruption": 3,
}


def _event_to_id(event: str) -> int:
    if event in EVENT_MAP:
        return EVENT_MAP[event]
    return len(EVENT_MAP)


def _rows() -> tuple[np.ndarray, np.ndarray]:
    xs: list[list[float]] = []
    ys: list[float] = []
    with DATASET.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                xs.append(
                    [
                        float(_event_to_id((row.get("event_type") or "").strip())),
                        float(row.get("country_stability_index") or 0),
                        float(row.get("severity_score") or 0),
                        float(row.get("disruption_duration_days") or 0),
                        float(row.get("daily_revenue_loss") or 0),
                        float(row.get("expedited_shipping_cost_usd") or 0),
                    ]
                )
                ys.append(float(row.get("cost_impact_usd") or 0))
            except ValueError:
                continue
    return np.array(xs, dtype=np.float32), np.array(ys, dtype=np.float32)


def train_and_save_model() -> dict:
    X, y = _rows()
    if len(X) == 0:
        raise RuntimeError("No training rows available from Predective_Forecasting.csv")
    model = XGBRegressor(
        n_estimators=220,
        max_depth=6,
        learning_rate=0.06,
        subsample=0.9,
        colsample_bytree=0.9,
        objective="reg:squarederror",
        random_state=42,
    )
    model.fit(X, y)
    joblib.dump(model, MODEL_PATH)
    return {"model_path": str(MODEL_PATH), "rows": int(len(X))}


def load_model() -> XGBRegressor | None:
    if not MODEL_PATH.exists():
        return None
    return joblib.load(MODEL_PATH)


def predict_cost_impact(
    event_type: str,
    country_stability_index: float,
    severity_score: float,
    disruption_duration_days: float,
    daily_revenue_loss: float,
    expedited_shipping_cost_usd: float,
) -> float | None:
    model = load_model()
    if model is None:
        return None
    x = np.array(
        [
            [
                float(_event_to_id(event_type)),
                float(country_stability_index),
                float(severity_score),
                float(disruption_duration_days),
                float(daily_revenue_loss),
                float(expedited_shipping_cost_usd),
            ]
        ],
        dtype=np.float32,
    )
    pred = model.predict(x)
    return float(pred[0])
