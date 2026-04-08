from __future__ import annotations

from .assessment_agent import run_assessment
from .rfq_agent import draft_rfq


def run_ooda(workflow_id: str, event_type: str, severity: float, suppliers: list[dict], recipient: str, quantities: str) -> dict:
    assessment = run_assessment(workflow_id, event_type, severity, suppliers)
    rfq = draft_rfq(recipient, event_type, quantities)
    return {
        "observe": {"event_type": event_type, "severity": severity},
        "orient": {"suppliers_count": len(suppliers)},
        "decide": {"recommendation": "trigger_rfq_if_confidence_high"},
        "act": {"rfq_draft": rfq},
        "assessment": assessment,
    }
