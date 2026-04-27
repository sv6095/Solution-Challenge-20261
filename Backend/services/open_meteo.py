from __future__ import annotations

import httpx


async def get_weather_risk(lat: float, lng: float) -> dict:
    async with httpx.AsyncClient(timeout=12.0) as client:
        res = await client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lng,
                "current": "temperature_2m,weather_code,wind_speed_10m",
                "forecast_days": 1,
            },
        )
        res.raise_for_status()
        data = res.json()
    current = data.get("current", {}) if isinstance(data, dict) else {}
    wind = float(current.get("wind_speed_10m") or 0.0)
    code = int(current.get("weather_code") or 0)
    risk = "high" if wind >= 20 or code in {95, 96, 99} else "moderate" if wind >= 12 else "low"
    return {"risk": risk, "wind_speed_10m": wind, "weather_code": code}

