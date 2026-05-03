from __future__ import annotations

from currency.frankfurter import convert_cost
from currency.risk_index import compute_currency_risk_index
from routing.air import air_route
from routing.land import google_maps_live_route, land_route
from routing.sea import sea_route


async def run_routing(
    origin_lat: float,
    origin_lng: float,
    origin_country_code: str,
    origin_label: str,
    dest_lat: float,
    dest_lng: float,
    dest_country_code: str,
    dest_label: str,
    target_currency: str,
) -> dict:
    if abs(origin_lat - dest_lat) < 1e-6 and abs(origin_lng - dest_lng) < 1e-6:
        raise ValueError("Origin and destination cannot be identical")
    if not all(
        isinstance(v, (int, float))
        for v in (origin_lat, origin_lng, dest_lat, dest_lng)
    ):
        raise ValueError("Invalid routing coordinates")

    sea = sea_route(origin_lat, origin_lng, dest_lat, dest_lng)
    air = air_route(origin_lat, origin_lng, dest_lat, dest_lng)
    land = land_route(origin_lat, origin_lng, dest_lat, dest_lng)
    live = await google_maps_live_route(origin_label, dest_label)
    if live:
        land["maps"] = live

    comparison = []
    for mode in (sea, air):
        comparison.append({**mode, "cost": await convert_cost(mode["cost_usd"], target_currency)})
    comparison.append(
        {
            "mode": "land",
            "sssp": {**land["sssp"], "cost": await convert_cost(float(land["sssp"]["cost_usd"]), target_currency)},
            "maps": {**land["maps"], "cost": await convert_cost(float(land["maps"]["cost_usd"]), target_currency)},
        }
    )
    valid_modes = {"sea", "air", "land"}
    mode_costs: dict[str, float] = {}
    for row in comparison:
        mode = str(row.get("mode") or "")
        if mode not in valid_modes:
            continue
        if mode in {"sea", "air"}:
            mode_costs[mode] = float(row.get("cost_usd") or 0.0)
        else:
            sssp = row.get("sssp") if isinstance(row.get("sssp"), dict) else {}
            maps = row.get("maps") if isinstance(row.get("maps"), dict) else {}
            mode_costs[mode] = min(float(sssp.get("cost_usd") or 0.0), float(maps.get("cost_usd") or 0.0))
    if not mode_costs:
        raise ValueError("No valid route modes computed")
    recommended_mode = min(mode_costs, key=mode_costs.get)
    return {
        "route_comparison": comparison,
        "currency_risk_index": await compute_currency_risk_index(origin_country_code, dest_country_code),
        "recommended_mode": recommended_mode,
    }
