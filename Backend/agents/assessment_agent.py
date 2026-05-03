from __future__ import annotations

from ml.assessment import assess_event


def run_assessment(workflow_id: str, event_type: str, severity: float, suppliers: list[dict]) -> dict:
    result = assess_event(workflow_id, event_type, severity, suppliers)
    return {
        "workflow_id": workflow_id,
        "affected_suppliers": result.affected_suppliers,
        "supplier_scores": result.supplier_scores,
        "financial_exposure_usd": result.financial_exposure_usd,
        "days_at_risk": result.days_at_risk,
        "confidence_score": result.confidence_score,
    }
