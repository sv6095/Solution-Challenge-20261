from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

import httpx


@dataclass
class LLMResult:
    provider: Literal["gemini", "groq", "local"]
    text: str


def _safe_truncate(value: str, limit: int = 6000) -> str:
    v = (value or "").strip()
    if len(v) <= limit:
        return v
    return v[: limit - 20].rstrip() + "\n\n[truncated]"


async def _call_gemini(prompt: str) -> str:
    """
    Gemini 2.0 Flash via Google AI Studio Generative Language API.
    Env var: GEMINI_API_KEY
    """
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY")

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.35, "maxOutputTokens": 850},
    }
    async with httpx.AsyncClient(timeout=25) as client:
        res = await client.post(url, params={"key": api_key}, json=payload)
        res.raise_for_status()
        data = res.json()

    candidates = data.get("candidates") or []
    parts: list[str] = []
    for c in candidates:
        content = (c or {}).get("content") or {}
        for p in (content.get("parts") or []):
            if isinstance(p, dict) and isinstance(p.get("text"), str):
                parts.append(p["text"])
    text = "\n".join([p.strip() for p in parts if p and p.strip()]).strip()
    if not text:
        raise RuntimeError("Gemini returned empty text")
    return text


async def _call_groq(prompt: str) -> str:
    """
    Groq via OpenAI-compatible Chat Completions API.
    Env var: GROQ_API_KEY
    """
    api_key = (os.getenv("GROQ_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("Missing GROQ_API_KEY")

    url = "https://api.groq.com/openai/v1/chat/completions"
    payload: dict[str, Any] = {
        "model": os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile"),
        "temperature": 0.35,
        "max_tokens": 850,
        "messages": [
            {
                "role": "system",
                "content": "You are a supply-chain crisis response analyst. Produce structured, decision-ready analysis.",
            },
            {"role": "user", "content": prompt},
        ],
    }
    async with httpx.AsyncClient(timeout=25) as client:
        res = await client.post(url, headers={"Authorization": f"Bearer {api_key}"}, json=payload)
        res.raise_for_status()
        data = res.json()

    choices = data.get("choices") or []
    msg = (((choices[0] or {}).get("message") or {}).get("content") if choices else "") or ""
    text = str(msg).strip()
    if not text:
        raise RuntimeError("Groq returned empty text")
    return text


def _local_analysis(event: dict, suppliers: list[dict], assessment: dict | None = None) -> str:
    title = str(event.get("title") or event.get("event_type") or "Disruption signal").strip()
    location = str(event.get("location") or event.get("region") or "Unknown region").strip()
    severity = event.get("severity")
    severity_score = event.get("severity_score")
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

    # Primary: Gemini. Fallback: Groq. Final: local structured analysis.
    try:
        text = await _call_gemini(prompt)
        return LLMResult(provider="gemini", text=text.strip())
    except Exception:
        try:
            text = await _call_groq(prompt)
            return LLMResult(provider="groq", text=text.strip())
        except Exception:
            return LLMResult(provider="local", text=_local_analysis(event, suppliers, assessment))

