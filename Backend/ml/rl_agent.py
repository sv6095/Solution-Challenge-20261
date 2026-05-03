from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class RLDecision:
    recommended_mode: Literal["sea", "air", "land"]
    confidence: float
    auto_approve_rfq: bool


def recommend_mode(
    *,
    disruption_severity: float,
    supplier_exposure_score: float,
    sea_available: bool,
    air_available: bool,
    land_available: bool,
    sea_cost_delta_pct: float = 0.0,
    land_time_delta_pct: float = 0.0,
    air_cost_usd: float = 0.0,
    currency_risk_index: float = 0.0,
    days_to_supplier_sla: float = 0.0,
) -> RLDecision:
    """
    Lightweight deterministic stand-in for the PPO decision layer.
    The interface matches the intended production policy inputs and outputs.
    """
    urgency = disruption_severity * 0.25 + supplier_exposure_score * 0.01 + max(0.0, 10.0 - days_to_supplier_sla) * 0.04
    if air_available and (urgency > 2.2 or air_cost_usd < 10000):
        mode = "air"
        confidence = 0.82
    elif land_available and land_time_delta_pct <= 35:
        mode = "land"
        confidence = 0.79
    elif sea_available:
        mode = "sea"
        confidence = 0.77 - min(currency_risk_index * 0.1, 0.08) - min(sea_cost_delta_pct * 0.002, 0.06)
    elif land_available:
        mode = "land"
        confidence = 0.73
    else:
        mode = "air"
        confidence = 0.68
    return RLDecision(recommended_mode=mode, confidence=max(0.5, round(confidence, 2)), auto_approve_rfq=confidence > 0.85)

