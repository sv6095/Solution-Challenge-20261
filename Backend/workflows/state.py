from __future__ import annotations

from typing import Literal, NotRequired, TypedDict


class WorkflowState(TypedDict):
    workflow_id: str
    user_id: str
    customer_id: NotRequired[str]
    current_stage: Literal["DETECT", "ASSESS", "DECIDE", "ACT", "AUDIT"]

    signals: list[dict]
    selected_signal: dict

    affected_suppliers: list[dict]
    exposure_usd: float
    exposure_local: float
    local_currency: str
    days_at_risk: int
    confidence: float
    currency_risk_index: float
    inflation_rate: float
    assessment_summary: str

    route_comparison: list[dict]
    network_routes: NotRequired[list[dict]]
    recommended_mode: str
    rl_confidence: float

    human_decision: NotRequired[str | None]
    selected_mode: NotRequired[str | None]
    waiting_human: NotRequired[bool]

    rfq_sent: bool
    action_state: dict
    rfq_recipient: NotRequired[str | None]
    rfq_email_body: NotRequired[str | None]
    rfq_requires_manual_send: NotRequired[bool]
    gmail_message_id: NotRequired[str | None]

    response_time_seconds: NotRequired[float | None]
    certificate_url: NotRequired[str | None]
    reasoning_steps: list[dict]
    specialist_packets: NotRequired[dict]
    decision_brief: NotRequired[dict]
    human_gate_packet: NotRequired[dict]
    final_report_markdown: NotRequired[str]
    compliance_frameworks: NotRequired[list[str]]
    completed_at: NotRequired[str]
