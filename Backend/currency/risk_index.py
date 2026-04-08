from __future__ import annotations

from .worldbank import get_inflation_rate


async def compute_currency_risk_index(origin_country_code: str, dest_country_code: str) -> float:
    origin_inflation = await get_inflation_rate(origin_country_code)
    dest_inflation = await get_inflation_rate(dest_country_code)
    inflation_diff = abs(origin_inflation - dest_inflation)
    return round(min(inflation_diff / 20.0, 1.0), 3)
