from __future__ import annotations

from dataclasses import dataclass

from .agent_definitions import (
    ASSISTANT_AGENT,
    LOGISTICS_RISK_AGENT,
    POLITICAL_RISK_AGENT,
    REPORTING_AGENT,
    SCHEDULER_AGENT,
    TARIFF_RISK_AGENT,
)


@dataclass
class QueryPlan:
    original_query: str
    needs_scheduler: bool
    requested_agents: list[str]
    use_assistant_only: bool
    needs_report: bool


def build_query_plan(message: str) -> QueryPlan:
    query = (message or "").strip()
    lowered = query.lower()

    political = "political" in lowered
    tariff = any(token in lowered for token in ("tariff", "trade risk", "customs", "duty"))
    logistics = any(token in lowered for token in ("logistics", "shipping", "port", "route", "transport"))
    schedule = any(token in lowered for token in ("schedule", "delay", "variance", "delivery", "late", "equipment"))
    comprehensive = any(
        token in lowered
        for token in (
            "all risks",
            "comprehensive",
            "full analysis",
            "complete risk",
            "what are the risks",
            "all specialist agents",
            "all agents",
            "full workflow",
            "coordinate all",
            "best response path",
            "cross-agent",
        )
    )
    report = any(token in lowered for token in ("report", "summary", "executive", "consolidated"))
    helpish = any(token in lowered for token in ("help", "hello", "hi", "what can you do"))
    workflowish = any(token in lowered for token in ("workflow", "decision", "response", "reroute", "backup supplier"))

    requested_agents: list[str] = []
    if comprehensive:
        requested_agents = [POLITICAL_RISK_AGENT, TARIFF_RISK_AGENT, LOGISTICS_RISK_AGENT]
    else:
        if political:
            requested_agents.append(POLITICAL_RISK_AGENT)
        if tariff:
            requested_agents.append(TARIFF_RISK_AGENT)
        if logistics:
            requested_agents.append(LOGISTICS_RISK_AGENT)

    use_assistant_only = helpish and not (schedule or requested_agents or report or workflowish)
    needs_scheduler = not use_assistant_only and (schedule or report or bool(requested_agents) or comprehensive or workflowish)
    needs_report = report or comprehensive or workflowish or len(requested_agents) > 1

    return QueryPlan(
        original_query=query,
        needs_scheduler=needs_scheduler,
        requested_agents=requested_agents,
        use_assistant_only=use_assistant_only,
        needs_report=needs_report,
    )


def build_agent_sequence(plan: QueryPlan) -> list[str]:
    if plan.use_assistant_only:
        return [ASSISTANT_AGENT]

    sequence: list[str] = []
    if plan.needs_scheduler:
        sequence.append(SCHEDULER_AGENT)
    sequence.extend(plan.requested_agents)
    if plan.needs_report or len(sequence) > 1:
        sequence.append(REPORTING_AGENT)
    elif not sequence:
        sequence.append(ASSISTANT_AGENT)
    return sequence
