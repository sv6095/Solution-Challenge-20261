from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .agent_protocol import AgentPacket, EvidenceItem, RecommendedAction, RiskFinding
from .reasoning_logger import log_reasoning_step
from .risk_calculator import calculate_risk_percentage, categorize_risk


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _days_until_due(p6_due_date: datetime | None) -> int:
    if not p6_due_date:
        return 0
    now = datetime.now(timezone.utc).date()
    due = p6_due_date.date() if p6_due_date.tzinfo else p6_due_date.date()
    return (due - now).days


def _normalize_equipment(context: dict[str, Any]) -> list[dict[str, Any]]:
    items = context.get("equipment_items")
    if isinstance(items, list) and items:
        return [item for item in items if isinstance(item, dict)]

    suppliers = context.get("suppliers")
    if isinstance(suppliers, list) and suppliers:
        normalized: list[dict[str, Any]] = []
        for idx, supplier in enumerate(suppliers):
            if not isinstance(supplier, dict):
                continue
            normalized.append(
                {
                    "code": supplier.get("supplier_id") or f"S-{idx + 1:03d}",
                    "name": supplier.get("name") or f"Supplier {idx + 1}",
                    "origin": supplier.get("country") or supplier.get("origin_country") or "Unknown",
                    "destination": context.get("project_country") or context.get("destination_country") or "Unknown",
                    "p6_due_date": supplier.get("p6_due_date"),
                    "delivery_date": supplier.get("delivery_date"),
                    "shipping_port": supplier.get("shipping_port") or supplier.get("city") or "Unknown",
                    "receiving_port": supplier.get("receiving_port") or context.get("receiving_port") or "Unknown",
                    "transport_mode": supplier.get("transport_mode") or "mixed",
                }
            )
        return normalized
    return []


def _risk_bucket_label(points: int) -> str:
    return "High" if points == 5 else "Medium" if points == 3 else "Low"


@dataclass
class SchedulerResult:
    summary: dict[str, Any]
    equipment_items: list[dict[str, Any]]
    manufacturing_locations: list[str]
    shipping_ports: list[str]
    receiving_ports: list[str]
    search_query: dict[str, str]
    markdown: str
    packet: AgentPacket


def analyze_schedule_context(context: dict[str, Any], workflow_id: str | None = None) -> SchedulerResult:
    equipment = _normalize_equipment(context)
    enriched: list[dict[str, Any]] = []
    risk_counts = {"High": 0, "Medium": 0, "Low": 0, "On Track": 0}

    for item in equipment:
        p6_due = _parse_dt(item.get("p6_due_date"))
        delivery = _parse_dt(item.get("delivery_date"))
        variance_days = 0
        if p6_due and delivery:
            variance_days = (delivery.date() - p6_due.date()).days
        days_until_due = _days_until_due(p6_due)
        risk_percentage = round(calculate_risk_percentage(variance_days, days_until_due), 2) if p6_due else 0.0
        category = categorize_risk(risk_percentage) if variance_days != 0 or p6_due else {"risk_flag": "Low Risk", "risk_points": 1}
        label = category["risk_flag"]
        short_label = "On Track" if variance_days == 0 else label.replace(" Risk", "")
        risk_counts[short_label] = risk_counts.get(short_label, 0) + 1
        enriched.append(
            {
                **item,
                "variance_days": variance_days,
                "days_until_due": days_until_due,
                "risk_percentage": risk_percentage,
                "risk_flag": label,
                "risk_points": category["risk_points"],
            }
        )

    manufacturing_locations = sorted({str(item.get("origin") or "Unknown") for item in enriched})
    shipping_ports = sorted({str(item.get("shipping_port") or "Unknown") for item in enriched})
    receiving_ports = sorted({str(item.get("receiving_port") or "Unknown") for item in enriched})
    equipment_type = str(context.get("equipment_type") or "industrial equipment")
    primary_origin = manufacturing_locations[0] if manufacturing_locations else "origin country"
    primary_destination = str(context.get("project_country") or context.get("destination_country") or "destination country")
    primary_ship = shipping_ports[0] if shipping_ports else "origin port"
    primary_recv = receiving_ports[0] if receiving_ports else "destination port"

    search_query = {
        "political": f"Political risks manufacturing exports {primary_origin} to {primary_destination} {equipment_type} current issues",
        "tariff": f"{primary_origin} {primary_destination} tariffs {equipment_type} trade agreements current changes",
        "logistics": f"{primary_ship} to {primary_recv} shipping route disruptions congestion delays current issues",
    }

    table_lines = [
        "| Equipment Code | Equipment Name | P6 Due Date | Delivery Date | Variance (days) | Risk % | Risk Level | Origin | Destination |",
        "|---|---|---|---|---:|---:|---|---|---|",
    ]
    for item in sorted(enriched, key=lambda row: row.get("risk_points", 1), reverse=True):
        table_lines.append(
            f"| {item.get('code', '')} | {item.get('name', '')} | {item.get('p6_due_date', '-') or '-'} | "
            f"{item.get('delivery_date', '-') or '-'} | {item.get('variance_days', 0)} | "
            f"{item.get('risk_percentage', 0):.2f}% | {item.get('risk_flag', 'Low Risk')} | "
            f"{item.get('origin', 'Unknown')} | {item.get('destination', 'Unknown')} |"
        )

    markdown = "\n".join(
        [
            "## Schedule Analysis",
            f"Items analyzed: **{len(enriched)}**",
            (
                "Risk breakdown: "
                f"High={risk_counts.get('High', 0)}, "
                f"Medium={risk_counts.get('Medium', 0)}, "
                f"Low={risk_counts.get('Low', 0)}, "
                f"On Track={risk_counts.get('On Track', 0)}"
            ),
            "",
            *table_lines,
        ]
    )

    findings: list[RiskFinding] = []
    for item in sorted(enriched, key=lambda row: row.get("risk_points", 1), reverse=True)[:8]:
        severity = _risk_bucket_label(int(item.get("risk_points", 1)))
        findings.append(
            RiskFinding(
                category="schedule",
                geography=str(item.get("destination") or "Unknown"),
                severity=severity,
                likelihood=min(0.95, 0.3 + float(item.get("risk_percentage", 0.0)) / 100.0),
                operational_impact=(
                    f"{item.get('name', 'Item')} shows variance of {item.get('variance_days', 0)} days against the planned due date, "
                    "which can cascade into downstream transport or production delay."
                ),
                financial_impact_hint="Exposure increases with expedite routing, buffer depletion, and unplanned procurement.",
                time_horizon="0-14 days" if int(item.get("variance_days", 0)) > 0 else "monitor",
                evidence=[
                    EvidenceItem(
                        source_name="Schedule context",
                        source_url="",
                        title=f"{item.get('code', '')} / {item.get('name', '')}",
                        verified=True,
                        citation_type="internal_schedule",
                    )
                ],
                recommended_actions=[
                    RecommendedAction(
                        priority="P1" if severity == "High" else "P2",
                        owner="Supply Chain Control Tower",
                        action=f"Validate ETA and fallback for {item.get('name', 'item')}",
                        reason="High-variance items should be confirmed before downstream routing or sourcing decisions are locked.",
                    )
                ],
            )
        )

    packet = AgentPacket(
        agent="scheduler_agent",
        confidence=0.84 if enriched else 0.58,
        summary=f"Schedule agent analyzed {len(enriched)} items and built normalized specialist context.",
        findings=findings,
        key_metrics={
            "items_analyzed": len(enriched),
            "high_risk_items": risk_counts.get("High", 0),
            "medium_risk_items": risk_counts.get("Medium", 0),
            "on_track_items": risk_counts.get("On Track", 0),
        },
        markdown=markdown,
        escalation_required=risk_counts.get("High", 0) > 0,
    )

    if workflow_id:
        log_reasoning_step(
            workflow_id,
            "scheduler_agent",
            "schedule_analysis",
            f"Analyzed {len(enriched)} schedule items and prepared cross-agent routing context.",
            "success",
            {"items": len(enriched), "risk_breakdown": risk_counts},
        )

    return SchedulerResult(
        summary={
            "items_analyzed": len(enriched),
            "risk_breakdown": risk_counts,
        },
        equipment_items=enriched,
        manufacturing_locations=manufacturing_locations,
        shipping_ports=shipping_ports,
        receiving_ports=receiving_ports,
        search_query=search_query,
        markdown=markdown,
        packet=packet,
    )
