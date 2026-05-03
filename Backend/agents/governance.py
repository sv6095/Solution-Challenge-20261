from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable


OrchestrationPath = str

PATH_CHAT: OrchestrationPath = "chat_manager"
PATH_WORKFLOW: OrchestrationPath = "workflow_graph"
PATH_AUTONOMOUS: OrchestrationPath = "autonomous_pipeline"

AGENTS_CHAT = {
    "signal_agent",
    "assessment_agent",
    "routing_agent",
    "supervisor_agent",
    "scheduler_agent",
    "political_risk_agent",
    "tariff_risk_agent",
    "logistics_risk_agent",
    "reporting_agent",
    "assistant_agent",
}
AGENTS_WORKFLOW = {
    "signal_agent",
    "assessment_agent",
    "routing_agent",
    "rfq_agent",
    "audit_agent",
    "scheduler_agent",
    "political_risk_agent",
    "tariff_risk_agent",
    "logistics_risk_agent",
}
AGENTS_AUTONOMOUS = {
    "signal_agent",
    "graph_agent",
    "assessment_agent",
    "routing_agent",
    "logistics_risk_agent",
    "political_risk_agent",
    "tariff_risk_agent",
    "decision_agent",
    "rfq_agent",
    "notification_agent",
    "action_agent",
    "audit_agent",
}

ALLOWED_AGENTS_BY_PATH: dict[OrchestrationPath, set[str]] = {
    PATH_CHAT: AGENTS_CHAT,
    PATH_WORKFLOW: AGENTS_WORKFLOW,
    PATH_AUTONOMOUS: AGENTS_AUTONOMOUS,
}

RETRY_POLICY_BY_AGENT: dict[str, tuple[int, float]] = {
    "signal_agent": (1, 0.0),
    "assessment_agent": (2, 0.0),
    "routing_agent": (2, 0.0),
    "scheduler_agent": (2, 0.0),
    "political_risk_agent": (2, 0.0),
    "tariff_risk_agent": (2, 0.0),
    "logistics_risk_agent": (2, 0.0),
    "reporting_agent": (1, 0.0),
    "rfq_agent": (1, 0.0),
    "audit_agent": (1, 0.0),
}


@dataclass
class AgentContract:
    agent: str
    required_inputs: tuple[str, ...]
    required_outputs: tuple[str, ...]
    owner_state_fields: tuple[str, ...]
    fallback_mode: str


CONTRACTS: dict[str, AgentContract] = {
    "signal_agent": AgentContract("signal_agent", ("selected_signal",), ("current_stage",), ("selected_signal", "current_stage"), "halt"),
    "assessment_agent": AgentContract("assessment_agent", ("selected_signal", "affected_suppliers"), ("confidence", "days_at_risk"), ("confidence", "days_at_risk", "assessment_summary"), "error"),
    "routing_agent": AgentContract("routing_agent", ("selected_signal", "affected_suppliers"), ("recommended_mode", "route_comparison"), ("recommended_mode", "route_comparison", "rl_confidence"), "error"),
    "rfq_agent": AgentContract("rfq_agent", ("selected_signal",), ("rfq_email_body", "action_state"), ("rfq_sent", "rfq_email_body", "action_state"), "manual_review"),
    "audit_agent": AgentContract("audit_agent", ("action_state",), ("completed_at",), ("completed_at", "final_report_markdown"), "terminal_error"),
}


def validate_agent_allowed(path: OrchestrationPath, agent: str) -> None:
    allowed = ALLOWED_AGENTS_BY_PATH.get(path, set())
    if agent not in allowed:
        raise ValueError(f"Agent '{agent}' not allowed in orchestration path '{path}'")


def validate_contract_input(agent: str, payload: dict[str, Any]) -> None:
    contract = CONTRACTS.get(agent)
    if not contract:
        return
    missing = [key for key in contract.required_inputs if key not in payload or payload.get(key) in (None, "", [], {})]
    if missing:
        raise ValueError(f"Agent '{agent}' missing required inputs: {missing}")


def validate_contract_output(agent: str, payload: dict[str, Any]) -> None:
    contract = CONTRACTS.get(agent)
    if not contract:
        return
    missing = [key for key in contract.required_outputs if key not in payload or payload.get(key) in (None, "", [], {})]
    if missing:
        raise ValueError(f"Agent '{agent}' missing required outputs: {missing}")


async def run_with_policy(
    *,
    agent: str,
    path: OrchestrationPath,
    fn: Callable[..., Any],
    kwargs: dict[str, Any] | None = None,
) -> Any:
    validate_agent_allowed(path, agent)
    attempts, _delay = RETRY_POLICY_BY_AGENT.get(agent, (1, 0.0))
    last_error: Exception | None = None
    args = kwargs or {}
    for _ in range(max(1, attempts)):
        try:
            result = fn(**args)
            if hasattr(result, "__await__"):
                result = await result
            return result
        except Exception as exc:  # noqa: PERF203
            last_error = exc
            continue
    if last_error:
        raise last_error
    raise RuntimeError(f"{agent} failed without explicit exception")


def build_failure_record(*, workflow_or_incident_id: str, path: OrchestrationPath, agent: str, error: str, terminal: bool) -> dict[str, Any]:
    return {
        "id": workflow_or_incident_id,
        "path": path,
        "agent": agent,
        "error": error,
        "terminal": terminal,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

