from __future__ import annotations

from typing import Any


def confidence_bounds(
    recommendation_confidence: float,
    data_quality_score: float,
    provider: str,
) -> dict[str, Any]:
    provider_factor = {"gemini": 1.0, "groq": 0.92, "local": 0.85}.get(str(provider).lower(), 0.9)
    quality_factor = max(0.5, min(1.0, data_quality_score / 100.0))
    calibrated = max(0.0, min(1.0, recommendation_confidence * provider_factor * quality_factor))
    spread = max(0.08, (1.0 - quality_factor) * 0.4)
    return {
        "base": round(calibrated, 4),
        "best_case": round(min(1.0, calibrated + spread), 4),
        "worst_case": round(max(0.0, calibrated - spread), 4),
        "spread": round(spread, 4),
        "actionable": calibrated >= 0.6 and quality_factor >= 0.75,
    }
