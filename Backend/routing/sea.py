from __future__ import annotations

from services.data_registry import registry
from .utils import haversine_km

AVG_VESSEL_SPEED_KMH = 26.0
DEFAULT_MULTIPLIERS: dict[str, float] = {
    "Pacific": 1.15,
    "Suez": 1.35,
    "Cape": 1.65,
    "Atlantic": 1.20,
    "Intra-Asia": 1.10,
    "Indian": 1.25,
}


def detect_lane(origin_lng: float, dest_lng: float, origin_lat: float, dest_lat: float) -> str:
    if abs(origin_lng - dest_lng) > 120:
        return "Pacific"
    if min(origin_lat, dest_lat) > 45 and abs(origin_lng - dest_lng) < 80:
        return "Atlantic"
    if min(origin_lng, dest_lng) > 30 and max(origin_lng, dest_lng) < 105:
        return "Indian"
    if abs(origin_lng - dest_lng) > 70:
        return "Suez"
    return "Intra-Asia"


def lane_multiplier(lane: str) -> float:
    dataset_value = registry.sea_lane_multiplier.get(lane)
    if dataset_value:
        return dataset_value
    return DEFAULT_MULTIPLIERS.get(lane, 1.2)


def sea_cost(distance_km: float) -> float:
    baseline = registry.mode_cost_baseline.get("sea", 3000.0)
    per_km = max(0.4, baseline / 1800.0)
    return round(distance_km * per_km, 2)


def sea_route(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
) -> dict:
    distance_km = haversine_km(origin_lat, origin_lng, dest_lat, dest_lng)
    lane = detect_lane(origin_lng, dest_lng, origin_lat, dest_lat)
    adjusted_km = distance_km * lane_multiplier(lane)
    transit_days = adjusted_km / (AVG_VESSEL_SPEED_KMH * 24.0)
    return {
        "mode": "sea",
        "lane": lane,
        "distance_km": round(adjusted_km, 2),
        "transit_days": round(transit_days, 1),
        "cost_usd": sea_cost(adjusted_km),
    }
