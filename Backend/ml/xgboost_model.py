from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.ensemble import ExtraTreesRegressor, RandomForestRegressor, StackingRegressor
from sklearn.linear_model import RidgeCV
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "Dataset" / "Predective_Forecasting.csv"
MODEL_PATH = ROOT / "ml" / "ensemble_cost_model.joblib"

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


def _build_model() -> StackingRegressor:
    estimators = [
        (
            "xgb",
            XGBRegressor(
                n_estimators=320,
                max_depth=7,
                learning_rate=0.05,
                subsample=0.9,
                colsample_bytree=0.9,
                objective="reg:squarederror",
                random_state=42,
            ),
        ),
        (
            "rf",
            RandomForestRegressor(
                n_estimators=240,
                max_depth=14,
                min_samples_leaf=2,
                random_state=42,
                n_jobs=-1,
            ),
        ),
        (
            "et",
            ExtraTreesRegressor(
                n_estimators=260,
                max_depth=16,
                min_samples_leaf=2,
                random_state=42,
                n_jobs=-1,
            ),
        ),
    ]
    return StackingRegressor(
        estimators=estimators,
        final_estimator=RidgeCV(alphas=(0.1, 1.0, 10.0)),
        passthrough=True,
        n_jobs=-1,
    )


def train_and_save_model() -> dict[str, Any]:
    X, y = _rows()
    if len(X) == 0:
        raise RuntimeError("No training rows available from Predective_Forecasting.csv")

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.18, random_state=42)
    model = _build_model()
    model.fit(X_train, y_train)
    preds = model.predict(X_test)
    metrics = {
        "model_family": "stacking_ensemble",
        "base_models": ["xgboost", "random_forest", "extra_trees"],
        "rows": int(len(X)),
        "holdout_rows": int(len(X_test)),
        "mae": float(mean_absolute_error(y_test, preds)),
        "r2": float(r2_score(y_test, preds)),
    }
    joblib.dump({"model": model, "metrics": metrics}, MODEL_PATH)
    return {"model_path": str(MODEL_PATH), **metrics}


def load_bundle() -> dict[str, Any] | None:
    if not MODEL_PATH.exists():
        return None
    bundle = joblib.load(MODEL_PATH)
    if isinstance(bundle, dict) and "model" in bundle:
        return bundle
    # backward compatibility with old single-model artifact
    return {"model": bundle, "metrics": {"model_family": "legacy", "mae": None, "r2": None}}


def load_model() -> Any | None:
    bundle = load_bundle()
    return None if bundle is None else bundle.get("model")


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


def predict_cost_impact_with_diagnostics(
    event_type: str,
    country_stability_index: float,
    severity_score: float,
    disruption_duration_days: float,
    daily_revenue_loss: float,
    expedited_shipping_cost_usd: float,
) -> dict[str, Any] | None:
    bundle = load_bundle()
    if bundle is None:
        return None
    prediction = predict_cost_impact(
        event_type=event_type,
        country_stability_index=country_stability_index,
        severity_score=severity_score,
        disruption_duration_days=disruption_duration_days,
        daily_revenue_loss=daily_revenue_loss,
        expedited_shipping_cost_usd=expedited_shipping_cost_usd,
    )
    metrics = bundle.get("metrics") if isinstance(bundle.get("metrics"), dict) else {}
    return {
        "prediction": prediction,
        "model_family": metrics.get("model_family", "unknown"),
        "mae": metrics.get("mae"),
        "r2": metrics.get("r2"),
    }
