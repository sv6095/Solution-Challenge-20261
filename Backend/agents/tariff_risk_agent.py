from __future__ import annotations

from typing import Any

from .agent_protocol import AgentPacket, EvidenceItem, RecommendedAction, RiskFinding
from .reasoning_logger import log_reasoning_step
from .runtime import run_structured_specialist
from .scheduler_agent import SchedulerResult


async def analyze_tariff_risk(
    scheduler: SchedulerResult,
    context: dict[str, Any],
    workflow_id: str | None = None,
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    destination = str(context.get("project_country") or context.get("destination_country") or "Unknown")

    for item in scheduler.equipment_items[:5]:
        origin = str(item.get("origin") or "Unknown")
        entries.append(
            {
                "country": origin,
                "summary": f"Trade policy changes between {origin} and {destination} could alter landed cost or customs timing.",
                "likelihood": 3 if origin != destination else 2,
                "reasoning": "Cross-border equipment flows carry moderate customs and duty exposure when origin and destination differ.",
                "tariff_details": f"Review HS-code classification, duty treatment, and any temporary safeguard or anti-dumping exposure for {origin} to {destination}.",
                "publish_date": "Current context",
                "source_name": "Trade heuristic",
                "source_url": "",
            }
        )

    if not entries:
        entries.append(
            {
                "country": "Unknown",
                "summary": "Trade-policy baseline review required before shipment commitment.",
                "likelihood": 2,
                "reasoning": "Origin and destination details are incomplete, so tariff exposure cannot yet be ruled out.",
                "tariff_details": "Validate origin country, incoterms, and customs classification.",
                "publish_date": "Current context",
                "source_name": "Trade heuristic",
                "source_url": "",
            }
        )

    markdown_lines = [
        "## Tariff Risk Analysis",
        "| Country | Summary | Likelihood (0-5) | Reasoning for Likelihood | Tariff Details | Publish Date | Source Name | Source URL |",
        "|---|---|---:|---|---|---|---|---|",
    ]
    for entry in entries:
        markdown_lines.append(
            f"| {entry['country']} | {entry['summary']} | {entry['likelihood']} | {entry['reasoning']} | "
            f"{entry['tariff_details']} | {entry['publish_date']} | {entry['source_name']} | {entry['source_url']} |"
        )

    structured = await run_structured_specialist(
        agent_name="tariff_risk_agent",
        mission="Assess tariff, customs, and trade-policy risks for the current supply context.",
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
                    category="tariff",
                    geography=entry["country"],
                    severity="High" if entry["likelihood"] >= 4 else "Medium" if entry["likelihood"] >= 2 else "Low",
                    likelihood=min(0.92, 0.14 + entry["likelihood"] * 0.17),
                    operational_impact=entry["summary"],
                    financial_impact_hint="Tariff shifts change landed cost, customs dwell time, and quote competitiveness.",
                    time_horizon="0-45 days",
                    evidence=[
                        EvidenceItem(
                            source_name=entry["source_name"],
                            source_url=entry["source_url"],
                            title=entry["summary"],
                            verified=entry["source_name"].lower() != "trade heuristic",
                            citation_type="trade_signal",
                        )
                    ],
                    recommended_actions=[
                        RecommendedAction(
                            priority="P1" if entry["likelihood"] >= 4 else "P2",
                            owner="Trade Compliance",
                            action=f"Validate duty exposure and HS classification for {entry['country']} shipments",
                            reason="Trade-policy volatility must be priced and cleared before backup or reroute commitments are made.",
                        )
                    ],
                )
            )

    if structured.findings:
        markdown_lines = [
            "## Tariff Risk Analysis (LLM Detailed)",
            "| Category | Geography | Severity | Likelihood | Impact | Actions |",
            "|---|---|---|---|---|---|",
        ]
        for f in findings:
            acts = "<br>".join(f"**{a.owner}**: {a.action}" for a in f.recommended_actions)
            impact = f.operational_impact.replace("|", "/")
            markdown_lines.append(f"| {f.category} | {f.geography} | {f.severity} | {f.likelihood:.2f} | {impact} | {acts} |")

    packet = AgentPacket(
        agent="tariff_risk_agent",
        confidence=structured.confidence if entries else 0.55,
        summary=structured.summary if structured.summary else f"Tariff risk agent identified {len(entries)} trade and customs risk vectors.",
        findings=findings,
        key_metrics=structured.key_metrics or {"entries": len(entries), "destination": destination},
        markdown="\n".join(markdown_lines),
        escalation_required=structured.escalation_required or any(entry["likelihood"] >= 4 for entry in entries),
    )

    if workflow_id:
        log_reasoning_step(
            workflow_id,
            "tariff_risk_agent",
            "tariff_risk_analysis",
            f"Prepared {len(entries)} tariff risk entries from origin-destination schedule context.",
            "success",
            {"entries": len(entries)},
        )

    return {"entries": entries, "markdown": "\n".join(markdown_lines), "packet": packet.to_dict()}
