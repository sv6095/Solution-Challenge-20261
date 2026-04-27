from __future__ import annotations

from typing import Any, Callable

from currency.frankfurter import get_exchange_rate
from currency.worldbank import get_inflation_rate
from routing.air import air_route
from routing.land import land_route
from routing.sea import sea_route
from services.open_meteo import get_weather_risk


async def tool_schedule_snapshot(context: dict[str, Any]) -> dict[str, Any]:
    items = context.get("equipment_items") or context.get("suppliers") or []
    return {"item_count": len(items), "items": items[:12]}


async def tool_signal_snapshot(context: dict[str, Any]) -> dict[str, Any]:
    signals = context.get("signals") if isinstance(context.get("signals"), list) else []
    return {"signal_count": len(signals), "signals": signals[:10]}


async def tool_weather_snapshot(context: dict[str, Any]) -> dict[str, Any]:
    lat = float(context.get("lat") or 0.0)
    lng = float(context.get("lng") or 0.0)
    return await get_weather_risk(lat, lng)


async def tool_currency_snapshot(context: dict[str, Any]) -> dict[str, Any]:
    base = str(context.get("base_currency") or "USD")
    quote = str(context.get("quote_currency") or "USD")
    rate = await get_exchange_rate(base, quote)
    inflation = await get_inflation_rate(str(context.get("country_code") or "US"))
    return {"rate": rate, "inflation": inflation}


async def tool_route_snapshot(context: dict[str, Any]) -> dict[str, Any]:
    origin_lat = float(context.get("origin_lat") or 0.0)
    origin_lng = float(context.get("origin_lng") or 0.0)
    dest_lat = float(context.get("dest_lat") or 0.0)
    dest_lng = float(context.get("dest_lng") or 0.0)
    return {
        "sea": sea_route(origin_lat, origin_lng, dest_lat, dest_lng),
        "air": air_route(origin_lat, origin_lng, dest_lat, dest_lng),
        "land": land_route(origin_lat, origin_lng, dest_lat, dest_lng),
    }


TOOL_REGISTRY: dict[str, Callable[..., Any]] = {
    "schedule_snapshot": tool_schedule_snapshot,
    "signal_snapshot": tool_signal_snapshot,
    "weather_snapshot": tool_weather_snapshot,
    "currency_snapshot": tool_currency_snapshot,
    "route_snapshot": tool_route_snapshot,
}
