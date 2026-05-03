from __future__ import annotations

from .assessment_agent import run_assessment
from .rfq_agent import draft_rfq

OODA_FLOW: dict[str, dict[str, str | None]] = {
    "DETECT": {"next": "ASSESS", "agent": "signal_agent"},
    "ASSESS": {"next": "DECIDE", "agent": "assessment_agent"},
    "DECIDE": {"next": "ACT", "agent": "routing_agent"},
    "ACT": {"next": "AUDIT", "agent": "rfq_agent"},
    "AUDIT": {"next": None, "agent": "audit_agent"},
}


def should_human_gate(confidence: float, stage: str) -> bool:
    """Human approval when confidence is below stage-specific thresholds."""
    thresholds = {
        "DECIDE": 0.75,
        "ACT": 0.85,
    }
    threshold = thresholds.get(stage.upper(), 0.75)
    return confidence < threshold


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
