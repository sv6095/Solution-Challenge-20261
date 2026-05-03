from __future__ import annotations

from typing import Any

from .agent_definitions import LOGISTICS_RISK_AGENT, POLITICAL_RISK_AGENT, REPORTING_AGENT, SCHEDULER_AGENT, TARIFF_RISK_AGENT
from .agent_protocol import AgentPacket, SupervisorPacket


def build_supervisor_packet(
    *,
    message: str,
    route_plan: dict[str, Any],
    packets: list[AgentPacket],
) -> SupervisorPacket:
    selected_agents = [packet.agent for packet in packets]
    confidences = [packet.confidence for packet in packets] or [0.55]
    escalation = any(packet.escalation_required for packet in packets)

    weighted_priority = []
    for packet in packets:
        priority_score = len(packet.findings) * 10 + int(packet.confidence * 10)
        weighted_priority.append((priority_score, packet.agent))
    weighted_priority.sort(reverse=True)

    rationale: list[str] = []
    if route_plan.get("needs_scheduler"):
        rationale.append("Schedule normalization is required before specialist analysis because equipment timing drives downstream risk.")
    if route_plan.get("needs_report"):
        rationale.append("A consolidated report is required because the request spans multiple risk domains or asks for executive synthesis.")
    if any(packet.agent == POLITICAL_RISK_AGENT for packet in packets):
        rationale.append("Political analysis was included to capture sanctions, permits, instability, and export-control friction.")
    if any(packet.agent == TARIFF_RISK_AGENT for packet in packets):
        rationale.append("Tariff analysis was included to capture customs, duties, and trade-policy volatility.")
    if any(packet.agent == LOGISTICS_RISK_AGENT for packet in packets):
        rationale.append("Logistics analysis was included to evaluate lane congestion, transfer risk, and route execution risk.")

    path = "monitor_only"
    all_findings = sum(len(packet.findings) for packet in packets)
    if all_findings >= 8:
        path = "multi_action_response"
    elif any(packet.escalation_required for packet in packets):
        path = "human_review"
    elif any(packet.agent in {POLITICAL_RISK_AGENT, TARIFF_RISK_AGENT, LOGISTICS_RISK_AGENT} for packet in packets):
        path = "specialist_mitigation"
    elif any(packet.agent == SCHEDULER_AGENT for packet in packets):
        path = "schedule_triage"
    if route_plan.get("needs_report"):
        selected_agents = [*selected_agents, REPORTING_AGENT] if REPORTING_AGENT not in selected_agents else selected_agents

    decision_brief = (
        f"Praecantator selected {', '.join(selected_agents) or 'assistant'} to answer: {message.strip()}. "
        f"Total findings: {all_findings}. Recommended path: {path}."
    )
    return SupervisorPacket(
        mission=message.strip(),
        selected_agents=selected_agents,
        priority_order=[name for _, name in weighted_priority] or selected_agents,
        decision_brief=decision_brief,
        global_confidence=round(sum(confidences) / len(confidences), 2),
        recommended_path=path,
        human_gate_required=escalation,
        rationale=rationale or ["Defaulted to the currently selected specialists based on the interpreted user intent."],
    )
