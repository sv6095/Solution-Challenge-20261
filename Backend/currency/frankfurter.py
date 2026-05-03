from __future__ import annotations

from datetime import datetime, timedelta

import httpx

_CACHE: dict[str, tuple[datetime, float]] = {}
_TTL = timedelta(minutes=15)


async def get_exchange_rate(from_currency: str, to_currency: str) -> float:
    key = f"{from_currency}:{to_currency}"
    now = datetime.utcnow()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < _TTL:
        return cached[1]

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(
                "https://api.frankfurter.app/latest",
                params={"from": from_currency, "to": to_currency},
            )
            response.raise_for_status()
            rate = float(response.json()["rates"][to_currency])
            _CACHE[key] = (now, rate)
            return rate
    except Exception:
        if cached:
            return cached[1]
        return 1.0


async def convert_cost(amount_usd: float, target_currency: str) -> dict:
    rate = await get_exchange_rate("USD", target_currency)
    return {
        "usd": round(amount_usd, 2),
        "local": round(amount_usd * rate, 2),
        "currency": target_currency,
        "rate": rate,
        "rate_date": datetime.utcnow().strftime("%Y-%m-%d"),
    }
