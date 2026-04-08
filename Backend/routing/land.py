from __future__ import annotations

import os

import httpx

from services.data_registry import registry
from .utils import haversine_km


def _sssp_route(distance_km: float) -> dict:
    transit_hours = distance_km / 58.0
    land_baseline = registry.mode_cost_baseline.get("land", registry.mode_cost_baseline.get("sea", 3000.0) * 1.4)
    per_km = max(0.8, land_baseline / 1200.0)
    return {
        "engine": "sssp",
        "distance_km": round(distance_km * 1.08, 2),
        "duration_hours": round(transit_hours, 1),
        "cost_usd": round(distance_km * per_km, 2),
    }


def _maps_route(distance_km: float) -> dict:
    transit_hours = distance_km / 52.0
    land_baseline = registry.mode_cost_baseline.get("land", registry.mode_cost_baseline.get("sea", 3000.0) * 1.6)
    per_km = max(1.0, land_baseline / 1000.0)
    return {
        "engine": "maps",
        "distance_km": round(distance_km, 2),
        "duration_hours": round(transit_hours, 1),
        "cost_usd": round(distance_km * per_km, 2),
    }


def land_route(origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float) -> dict:
    distance_km = haversine_km(origin_lat, origin_lng, dest_lat, dest_lng)
    return {
        "mode": "land",
        "sssp": _sssp_route(distance_km),
        "maps": _maps_route(distance_km),
    }


async def google_maps_live_route(origin_text: str, destination_text: str) -> dict | None:
    if os.getenv("GOOGLE_MAPS_USE_LIVE", "false").lower() != "true":
        return None
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://routes.googleapis.com/directions/v2:computeRoutes",
                headers={
                    "X-Goog-Api-Key": api_key,
                    "X-Goog-FieldMask": "routes.duration,routes.distanceMeters",
                },
                json={
                    "origin": {"address": origin_text},
                    "destination": {"address": destination_text},
                    "travelMode": "DRIVE",
                    "routingPreference": "TRAFFIC_AWARE",
                },
            )
            response.raise_for_status()
            data = response.json()
            if not data.get("routes"):
                return None
            route = data["routes"][0]
            duration_s = 0.0
            duration_text = str(route.get("duration", "0s")).replace("s", "")
            try:
                duration_s = float(duration_text)
            except ValueError:
                duration_s = 0.0
            distance_km = float(route.get("distanceMeters", 0.0)) / 1000.0
            return {
                "engine": "maps_live",
                "distance_km": round(distance_km, 2),
                "duration_hours": round(duration_s / 3600.0, 2),
                "cost_usd": round(max(1.0, distance_km) * 1.2, 2),
            }
    except Exception:
        return None
