from __future__ import annotations

from .agent_protocol import AgentPacket, EvidenceItem, RecommendedAction, RiskFinding
from .reasoning_logger import log_reasoning_step
from .runtime import run_structured_specialist
from .scheduler_agent import SchedulerResult


async def analyze_logistics_risk(
    scheduler: SchedulerResult,
    context: dict,
    workflow_id: str | None = None,
) -> dict:
    entries: list[dict] = []

    for item in scheduler.equipment_items[:5]:
        ship = str(item.get("shipping_port") or "Unknown")
        recv = str(item.get("receiving_port") or "Unknown")
        variance = int(item.get("variance_days") or 0)
        entries.append(
            {
                "country": str(item.get("destination") or "Unknown"),
                "summary": f"Lane {ship} to {recv} may face congestion, routing changes, or customs queue buildup.",
                "likelihood": 4 if variance > 7 else 3 if variance > 0 else 2,
                "reasoning": "Likelihood rises when scheduled variance already exists or when the route depends on a narrow lane/port pair.",
                "logistics_details": f"Review carrier allocation, port dwell, inland transfer capacity, and alternate routing for {ship} to {recv}.",
                "publish_date": "Current context",
                "source_name": "Routing heuristic",
                "source_url": "",
            }
        )

    if not entries:
        entries.append(
            {
                "country": "Unknown",
                "summary": "Route disruption risk review required before transport execution.",
                "likelihood": 2,
                "reasoning": "Route metadata is incomplete, so operational friction cannot yet be estimated precisely.",
                "logistics_details": "Validate lane, carrier, transfer mode, and alternate options.",
                "publish_date": "Current context",
                "source_name": "Routing heuristic",
                "source_url": "",
            }
        )

    markdown_lines = [
        "## Logistics Risk Analysis",
        "| Country | Summary | Likelihood (0-5) | Reasoning for Likelihood | Logistics Details | Publish Date | Source Name | Source URL |",
        "|---|---|---:|---|---|---|---|---|",
    ]
    for entry in entries:
        markdown_lines.append(
            f"| {entry['country']} | {entry['summary']} | {entry['likelihood']} | {entry['reasoning']} | "
            f"{entry['logistics_details']} | {entry['publish_date']} | {entry['source_name']} | {entry['source_url']} |"
        )

    structured = await run_structured_specialist(
        agent_name="logistics_risk_agent",
        mission="Assess logistics, route, congestion, and weather execution risk for the current supply context.",
        context={**context, "scheduler": scheduler.summary, "entries": entries},
        workflow_id=workflow_id,
    )
    findings: list[RiskFinding] = []
    if structured.findings:
        for finding in structured.findings:
            findings.append(
                RiskFinding(
                    category=finding.category,
                    geography=finding.geography,
                    severity=finding.severity,
                    likelihood=finding.likelihood,
                    operational_impact=finding.operational_impact,
                    financial_impact_hint=finding.financial_impact_hint,
                    time_horizon=finding.time_horizon,
                    evidence=[EvidenceItem(**e.model_dump()) for e in finding.evidence],
                    recommended_actions=[RecommendedAction(**a.model_dump()) for a in finding.recommended_actions],
                )
            )
    else:
        for entry in entries:
            findings.append(
                RiskFinding(
                    category="logistics",
                    geography=entry["country"],
                    severity="High" if entry["likelihood"] >= 4 else "Medium" if entry["likelihood"] >= 2 else "Low",
                    likelihood=min(0.94, 0.12 + entry["likelihood"] * 0.18),
                    operational_impact=entry["summary"],
                    financial_impact_hint="Lane disruption drives demurrage, rebooking, premium freight, and service-level penalties.",
                    time_horizon="0-21 days",
                    evidence=[
                        EvidenceItem(
                            source_name=entry["source_name"],
                            source_url=entry["source_url"],
                            title=entry["summary"],
                            verified=entry["source_name"].lower() != "routing heuristic",
                            citation_type="route_signal",
                        )
                    ],
                    recommended_actions=[
                        RecommendedAction(
                            priority="P1" if entry["likelihood"] >= 4 else "P2",
                            owner="Logistics Command",
                            action=f"Prepare alternate execution plan for {entry['country']} lane",
                            reason="Route congestion or customs friction compounds schedule delay quickly once cargo is already in motion.",
                        )
                    ],
                )
            )

    if structured.findings:
        markdown_lines = [
            "## Logistics Risk Analysis (LLM Detailed)",
            "| Category | Geography | Severity | Likelihood | Impact | Actions |",
            "|---|---|---|---|---|---|",
        ]
        for f in findings:
            acts = "<br>".join(f"**{a.owner}**: {a.action}" for a in f.recommended_actions)
            impact = f.operational_impact.replace("|", "/")
            markdown_lines.append(f"| {f.category} | {f.geography} | {f.severity} | {f.likelihood:.2f} | {impact} | {acts} |")

    packet = AgentPacket(
        agent="logistics_risk_agent",
        confidence=structured.confidence if entries else 0.56,
        summary=structured.summary if structured.summary else f"Logistics risk agent identified {len(entries)} lane and transfer execution risks.",
        findings=findings,
        key_metrics=structured.key_metrics or {"entries": len(entries)},
        markdown="\n".join(markdown_lines),
        escalation_required=structured.escalation_required or any(entry["likelihood"] >= 4 for entry in entries),
    )

    if workflow_id:
        log_reasoning_step(
            workflow_id,
            "logistics_risk_agent",
            "logistics_risk_analysis",
            f"Prepared {len(entries)} logistics risk entries from routing and schedule context.",
            "success",
            {"entries": len(entries)},
        )

    return {"entries": entries, "markdown": "\n".join(markdown_lines), "packet": packet.to_dict()}
