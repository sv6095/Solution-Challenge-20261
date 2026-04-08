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
    return {
        "route_comparison": comparison,
        "currency_risk_index": await compute_currency_risk_index(origin_country_code, dest_country_code),
        "recommended_mode": "land",
    }
