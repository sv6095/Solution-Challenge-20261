from __future__ import annotations

from datetime import datetime, timedelta

import httpx

_CACHE: dict[str, tuple[datetime, float]] = {}
_TTL = timedelta(minutes=15)


async def get_inflation_rate(country_code: str) -> float:
    code = country_code.upper()
    now = datetime.utcnow()
    cached = _CACHE.get(code)
    if cached and now - cached[0] < _TTL:
        return cached[1]

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(
                f"https://api.worldbank.org/v2/country/{code}/indicator/FP.CPI.TOTL.ZG",
                params={"format": "json", "mrv": 1},
            )
            response.raise_for_status()
            payload = response.json()
            value = payload[1][0]["value"] if len(payload) > 1 and payload[1] else None
            rate = float(value) if value is not None else 0.0
            _CACHE[code] = (now, rate)
            return rate
    except Exception:
        if cached:
            return cached[1]
        return 0.0
