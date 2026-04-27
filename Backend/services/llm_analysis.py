from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from services.llm_provider import chat_complete


@dataclass
class LLMResult:
    provider: Literal["gemini", "groq", "local"]
    text: str


def _safe_truncate(value: str, limit: int = 6000) -> str:
    v = (value or "").strip()
    if len(v) <= limit:
        return v
    return v[: limit - 20].rstrip() + "\n\n[truncated]"


def _local_analysis(event: dict, suppliers: list[dict], assessment: dict | None = None) -> str:
    title = str(event.get("title") or event.get("event_type") or "Disruption signal").strip()
    location = str(event.get("location") or event.get("region") or "Unknown region").strip()
    affected = suppliers[:8]
    affected_names = ", ".join([str(s.get("name") or "Supplier") for s in affected[:5]])
    exposure_usd = None
    days_at_risk = None
    confidence = None
    if assessment:
        exposure_usd = assessment.get("financial_exposure_usd")
        days_at_risk = assessment.get("days_at_risk")
        confidence = assessment.get("confidence_score")

    lines: list[str] = []
    lines.append(f"### Situation Summary\n{title} near **{location}** is flagged as an operational disruption.")
    lines.append(
        "### Why This Matters (Supply Impact)\n"
        "This event is treated as a corridor-level risk: it can create upstream delays (production inputs), midstream delays (port/airport congestion), and downstream volatility (expedite cost + SLA breaches)."
    )
    lines.append(
        "### Node Exposure (Who is at risk)\n"
        f"Affected high-exposure nodes (top set): {affected_names if affected_names else 'No supplier nodes provided.'}\n"
        "Tier impact usually amplifies exposure: Tier 1 interruptions become immediate line-stops; Tier 2/3 propagate slower but are harder to observe."
    )
    lines.append(
        "### Operational Consequences (next 3–10 days)\n"
        "- Likely symptoms: delayed inbound ETAs, partial shipments, increased cancellations, carrier re-booking, and cost spikes on expedite lanes.\n"
        "- Secondary effects: inventory buffer drawdown, overtime production, and higher variance in delivery promises."
    )
    if exposure_usd is not None or days_at_risk is not None:
        lines.append(
            "### Quantified Impact (model-backed)\n"
            f"- Estimated exposure: **${exposure_usd} USD**\n"
            f"- Days at risk: **{days_at_risk} days**\n"
            f"- Confidence: **{confidence}**\n"
            "Interpretation: exposure is a planning number for mitigation (reroute + alternate supplier activation), not a bookable invoice."
        )
    lines.append(
        "### Recommended Response (decision-ready)\n"
        "- **Immediate**: verify which POs/shipments touch the impacted geography; freeze non-essential movements; alert procurement + logistics.\n"
        "- **Mitigation**: prepare a dual-track action: (A) reroute time-critical lanes, (B) pre-draft RFQs for backup suppliers.\n"
        "- **Governance**: keep a single workflow log so every decision is timestamped and exportable to a compliance PDF."
    )
    lines.append(
        "### What To Watch (signals that change the decision)\n"
        "- Escalation indicators: port closures, airport slot reductions, civil unrest near logistics hubs, or weather wind thresholds.\n"
        "- De-escalation indicators: re-open notices, backlog clearing rates, and carrier schedule normalization."
    )
    lines.append(
        "### Next Automation Steps\n"
        "If confidence is high and one signal dominates, auto-advance to assessment. Otherwise hold for human gate at DECIDE with a route comparison and backup supplier shortlist."
    )
    return "\n\n".join(lines).strip()


async def generate_workflow_analysis(
    *,
    event: dict,
    suppliers: list[dict],
    assessment: dict | None = None,
    workflow_id: str | None = None,
) -> LLMResult:
    prompt = _safe_truncate(
        f"""
You are SupplyShield's Assessment Agent.
Write a detailed but concise brief analysis (NOT 1-2 lines). Aim for ~8-14 sentences across clear sections.

Constraints:
- Be decision-ready for a supply chain manager.
- Mention exposure drivers, affected nodes, likely operational consequences, and recommended next actions.
- Use plain English, no fluff.

Event:
{event}

Suppliers (subset, may include tiers/locations/exposure scores):
{suppliers[:25]}

Assessment (if present):
{assessment or {}}
""".strip(),
        7000,
    )

    system = (
        "You are SupplyShield's Assessment Agent. "
        "Write decision-ready supply-chain analysis in clear sections. No fluff."
    )

    try:
        text, used = await chat_complete(
            prompt,
            system=system,
            max_tokens=850,
            workflow_id=workflow_id,
            agent_name="assessment_agent",
        )
        prov: Literal["gemini", "groq", "local"] = "gemini" if used == "gemini" else "groq"
        return LLMResult(provider=prov, text=text.strip())
    except Exception:
        return LLMResult(provider="local", text=_local_analysis(event, suppliers, assessment))


async def generate_appendix_nlp(report: dict) -> str:
    """Executive summary: LLM via provider pattern, then template fallback."""
    prompt = (
        "Convert this raw JSON workflow snapshot into a formal, concise 3-paragraph executive audit summary. "
        "Focus on the disruption event, the calculated financial exposure, and the final action taken. "
        "No markdown formatting, just plain professional text. JSON:\n"
        f"{json.dumps(report)[:4500]}"
    )

    try:
        text, _used = await chat_complete(prompt, system="", max_tokens=600, workflow_id=None, agent_name=None)
        if text.strip():
            return text.strip()
    except Exception:
        pass

    summary = report.get("summary", {})
    act = report.get("act", {})
    return (
        f"This execution record details a critical supply chain disruption managed by the Praecantator Kinetic Fortress module. "
        f"The platform registered a severe routing interruption triggering a fully coordinated reassessment protocol. "
        f"Initial telemetry projected a maximum operational financial exposure of {summary.get('exposure_usd', 'Unknown')} USD, "
        f"forcing immediate intervention.\n\n"
        f"Following the automated risk-modeling sequence, the operator executed emergency contingency '{str(summary.get('action_taken', 'N/A')).upper()}'. "
        f"The workflow achieved end-to-end resolution in {summary.get('response_time_seconds', 'N/A')} seconds. "
        f"Additional telemetry indicated decisions were locked with cryptographic execution parameters: {act.get('details', 'No detailed context provided.')}"
    )
