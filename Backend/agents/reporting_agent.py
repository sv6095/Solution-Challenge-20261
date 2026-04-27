from __future__ import annotations

from .agent_protocol import AgentPacket
from .reasoning_logger import log_reasoning_step


def build_consolidated_report(
    *,
    scheduler_markdown: str | None = None,
    political_markdown: str | None = None,
    tariff_markdown: str | None = None,
    logistics_markdown: str | None = None,
    packets: list[dict] | None = None,
    workflow_id: str | None = None,
) -> dict:
    sections = ["# Comprehensive Risk Report"]
    typed_packets: list[AgentPacket] = []
    for packet in packets or []:
        if not isinstance(packet, dict) or not packet.get("agent"):
            continue
        typed_packets.append(
            AgentPacket(
                agent=str(packet.get("agent")),
                confidence=float(packet.get("confidence") or 0.0),
                summary=str(packet.get("summary") or ""),
                findings=[],
                key_metrics=packet.get("key_metrics") if isinstance(packet.get("key_metrics"), dict) else {},
                markdown=str(packet.get("markdown") or ""),
                escalation_required=bool(packet.get("escalation_required")),
            )
        )
    if typed_packets:
        sections.append("## Executive Decision Brief")
        for packet in typed_packets:
            sections.append(
                f"- **{packet.agent}** ({int(packet.confidence * 100)}% confidence): {packet.summary}"
            )
        actions: list[str] = []
        for raw_packet in packets or []:
            if not isinstance(raw_packet, dict):
                continue
            for finding in raw_packet.get("findings", [])[:2] if isinstance(raw_packet.get("findings"), list) else []:
                if not isinstance(finding, dict):
                    continue
                actions_list = finding.get("recommended_actions", [])
                if not isinstance(actions_list, list) or not actions_list:
                    continue
                action = actions_list[0]
                if not isinstance(action, dict):
                    continue
                actions.append(
                    f"- [{action.get('priority', 'P2')}] {action.get('owner', 'Ops')}: "
                    f"{action.get('action', 'Review') } because {action.get('reason', 'this risk is material.')}"
                )
        if actions:
            sections.append("## Priority Actions\n" + "\n".join(actions[:8]))
    if scheduler_markdown:
        sections.append(scheduler_markdown)
    if political_markdown:
        sections.append(political_markdown)
    if tariff_markdown:
        sections.append(tariff_markdown)
    if logistics_markdown:
        sections.append(logistics_markdown)

    sections.append(
        "\n## Consolidated Recommendations\n"
        "- Validate high-variance equipment first and align escalation owners.\n"
        "- Secure alternate lanes and backup suppliers for any high-risk origin-destination pair.\n"
        "- Reconfirm customs documentation, trade terms, and approval gates before shipment release.\n"
        "- Keep one workflow record so decisions, route changes, and RFQ actions remain auditable."
    )
    markdown = "\n\n".join(sections)

    if workflow_id:
        log_reasoning_step(
            workflow_id,
            "reporting_agent",
            "report_consolidation",
            "Consolidated schedule and specialized risk outputs into an executive workflow report.",
            "success",
            {"sections": len(sections) - 1},
        )

    return {"markdown": markdown}
