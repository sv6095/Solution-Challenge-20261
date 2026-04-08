from __future__ import annotations

from services.data_registry import registry
from .utils import haversine_km

AVG_CARGO_SPEED_KMH = 800.0


def air_cost(distance_km: float) -> float:
    baseline = registry.mode_cost_baseline.get("air", 15000.0)
    per_km = max(2.0, baseline / 900.0)
    return round(distance_km * per_km, 2)


def air_route(origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float) -> dict:
    distance_km = haversine_km(origin_lat, origin_lng, dest_lat, dest_lng)
    flight_hours = distance_km / AVG_CARGO_SPEED_KMH
    return {
        "mode": "air",
        "distance_km": round(distance_km, 2),
        "flight_hours": round(flight_hours, 1),
        "cost_usd": air_cost(distance_km),
    }
