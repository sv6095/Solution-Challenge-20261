from __future__ import annotations

from typing import Any

from .agent_protocol import AgentPacket, EvidenceItem, RecommendedAction, RiskFinding
from .reasoning_logger import log_reasoning_step
from .runtime import run_structured_specialist
from .scheduler_agent import SchedulerResult


def _build_entry(country: str, title: str, likelihood: int, detail: str, source_name: str, source_url: str) -> dict[str, Any]:
    return {
        "country": country,
        "political_type": title,
        "risk_information": detail,
        "likelihood": likelihood,
        "likelihood_reasoning": (
            "Higher likelihood reflects active policy or governance conditions that can affect supplier timing, "
            "customs handling, or export clearance."
        ),
        "publication_date": "Current context",
        "citation_title": title,
        "citation_name": source_name,
        "citation_url": source_url,
    }


async def analyze_political_risk(
    scheduler: SchedulerResult,
    context: dict[str, Any],
    workflow_id: str | None = None,
) -> dict[str, Any]:
    signals = context.get("signals") if isinstance(context.get("signals"), list) else []
    entries: list[dict[str, Any]] = []

    for signal in signals:
        if not isinstance(signal, dict):
            continue
        source = str(signal.get("source") or "Signal feed")
        title = str(signal.get("title") or "Regional political disruption")
        event_type = str(signal.get("event_type") or "").lower()
        if any(token in event_type for token in ("political", "geopolitical", "sanction", "conflict")) or source.lower() == "gdelt":
            entries.append(
                _build_entry(
                    country=str(signal.get("location") or scheduler.manufacturing_locations[0] if scheduler.manufacturing_locations else "Unknown"),
                    title=title,
                    likelihood=4,
                    detail=f"{title} may tighten export controls, slow permits, or increase border friction for scheduled deliveries.",
                    source_name=source,
                    source_url=str(signal.get("source_url") or signal.get("url") or ""),
                )
            )

    if not entries:
        for country in scheduler.manufacturing_locations[:3] or ["Unknown"]:
            entries.append(
                _build_entry(
                    country=country,
                    title=f"Policy volatility watch for {country}",
                    likelihood=3,
                    detail=f"Cross-border shipments from {country} should be monitored for export licensing, inspections, and political escalation risk.",
                    source_name="Planner heuristic",
                    source_url="",
                )
            )

    markdown_lines = [
        "## Political Risk Analysis",
        "| Country | Political Type | Risk Information | Likelihood (0-5) | Likelihood Reasoning | Publication Date | Citation Title | Citation Name | Citation URL |",
        "|---|---|---|---:|---|---|---|---|---|",
    ]
    for entry in entries:
        markdown_lines.append(
            f"| {entry['country']} | {entry['political_type']} | {entry['risk_information']} | {entry['likelihood']} | "
            f"{entry['likelihood_reasoning']} | {entry['publication_date']} | {entry['citation_title']} | "
            f"{entry['citation_name']} | {entry['citation_url']} |"
        )

    structured = await run_structured_specialist(
        agent_name="political_risk_agent",
        mission="Assess political and geopolitical risks affecting current supply execution.",
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
                    category="political",
                    geography=entry["country"],
                    severity="High" if entry["likelihood"] >= 4 else "Medium" if entry["likelihood"] >= 2 else "Low",
                    likelihood=min(0.95, 0.15 + entry["likelihood"] * 0.18),
                    operational_impact=entry["risk_information"],
                    financial_impact_hint="Political friction can introduce permit delays, border holds, and expedited re-sourcing cost.",
                    time_horizon="0-30 days",
                    evidence=[
                        EvidenceItem(
                            source_name=entry["citation_name"],
                            source_url=entry["citation_url"],
                            title=entry["citation_title"],
                            verified=entry["citation_name"].lower() not in {"signal feed", "planner heuristic"},
                            citation_type="political_signal",
                        )
                    ],
                    recommended_actions=[
                        RecommendedAction(
                            priority="P1" if entry["likelihood"] >= 4 else "P2",
                            owner="Procurement and Trade Compliance",
                            action=f"Review export and import constraints affecting {entry['country']}",
                            reason="Political instability and policy changes often materialize as customs or permitting delay before formal disruption notices arrive.",
                        )
                    ],
                )
            )

    if structured.findings:
        markdown_lines = [
            "## Political Risk Analysis (LLM Detailed)",
            "| Category | Geography | Severity | Likelihood | Impact | Actions |",
            "|---|---|---|---|---|---|",
        ]
        for f in findings:
            acts = "<br>".join(f"**{a.owner}**: {a.action}" for a in f.recommended_actions)
            impact = f.operational_impact.replace("|", "/")
            markdown_lines.append(f"| {f.category} | {f.geography} | {f.severity} | {f.likelihood:.2f} | {impact} | {acts} |")

    packet = AgentPacket(
        agent="political_risk_agent",
        confidence=structured.confidence if entries else 0.55,
        summary=structured.summary if structured.summary else f"Political risk agent identified {len(entries)} political risk vectors affecting the current supply picture.",
        findings=findings,
        key_metrics=structured.key_metrics or {"entries": len(entries), "countries": sorted({entry['country'] for entry in entries})},
        markdown="\n".join(markdown_lines),
        escalation_required=structured.escalation_required or any(entry["likelihood"] >= 4 for entry in entries),
    )

    if workflow_id:
        log_reasoning_step(
            workflow_id,
            "political_risk_agent",
            "political_risk_analysis",
            f"Prepared {len(entries)} political risk entries from schedule context and available signals.",
            "success",
            {"entries": len(entries)},
        )

    return {"entries": entries, "markdown": "\n".join(markdown_lines), "packet": packet.to_dict()}
