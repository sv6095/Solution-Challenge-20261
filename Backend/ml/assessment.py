from __future__ import annotations

from dataclasses import dataclass

from services.data_registry import registry
from ml.xgboost_model import predict_cost_impact_with_diagnostics


@dataclass
class AssessmentResult:
    financial_exposure_usd: float
    days_at_risk: int
    confidence_score: float
    affected_suppliers: list[dict]
    supplier_scores: list[dict]


def assess_event(workflow_id: str, event_type: str, severity: float, suppliers: list[dict]) -> AssessmentResult:
    base = registry.assessment_cost_by_event.get(event_type, 15000.0)
    sev = max(0.0, min(10.0, severity)) / 10.0
    supplier_scores: list[dict] = []
    weighted = 0.0
    for s in suppliers:
        tier_raw = str(s.get("tier", "3")).lower().replace("tier", "").strip()
        try:
            tier = int(tier_raw)
        except ValueError:
            tier = 3
        tier_weight = {1: 1.0, 2: 0.6, 3: 0.3}.get(tier, 0.3)
        score = round((0.65 * sev + 0.35 * tier_weight) * 100, 1)
        supplier_scores.append({"supplier": s.get("name", "unknown"), "tier": tier, "score": score})
        weighted += score

    supplier_factor = max(1.0, (weighted / 100.0) if suppliers else 1.0)
    model_pred = predict_cost_impact_with_diagnostics(
        event_type=event_type,
        country_stability_index=0.6,
        severity_score=float(severity),
        disruption_duration_days=max(1.0, float(severity) * 1.4),
        daily_revenue_loss=base / 8.0,
        expedited_shipping_cost_usd=base / 4.0,
    )
    predicted = float(model_pred.get("prediction")) if model_pred and model_pred.get("prediction") is not None else base
    exposure = round(predicted * max(0.2, sev) * supplier_factor, 2)
    model_r2 = float(model_pred.get("r2") or 0.0) if model_pred else 0.0
    confidence = round(min(0.98, 0.48 + 0.28 * sev + min(0.08, len(suppliers) * 0.01) + max(0.0, model_r2) * 0.12), 3)
    days = max(1, int(round(1 + severity * 1.4)))
    return AssessmentResult(
        financial_exposure_usd=exposure,
        days_at_risk=days,
        confidence_score=confidence,
        affected_suppliers=suppliers,
        supplier_scores=supplier_scores,
    )
