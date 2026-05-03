from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ValidationError

from agents.schemas import SpecialistOutputModel, ToolPlanModel
from agents.toolbox import TOOL_REGISTRY
from services.llm_provider import structured_complete


def _fallback_specialist_output(agent_name: str, context: dict[str, Any]) -> SpecialistOutputModel:
    signals = context.get("signals") if isinstance(context.get("signals"), list) else []
    geography = str(context.get("project_country") or context.get("destination_country") or "Unknown")
    return SpecialistOutputModel(
        summary=f"{agent_name} fallback analysis used deterministic heuristics for {geography}.",
        confidence=0.55,
        escalation_required=bool(signals),
        key_metrics={"signal_count": len(signals)},
        findings=[],
    )


async def _run_tool_plan(context: dict[str, Any], plan: ToolPlanModel) -> dict[str, Any]:
    outputs: dict[str, Any] = {}
    for call in plan.tool_calls:
        tool = TOOL_REGISTRY.get(call.tool_name)
        if tool is None:
            outputs[call.tool_name] = {"error": "tool_not_found"}
            continue
        merged_context = {**context, **(call.arguments or {})}
        try:
            outputs[call.tool_name] = await tool(merged_context)
        except Exception as exc:
            outputs[call.tool_name] = {"error": str(exc)}
    return outputs


async def run_structured_specialist(
    *,
    agent_name: str,
    mission: str,
    context: dict[str, Any],
    workflow_id: str | None = None,
) -> SpecialistOutputModel:
    tool_names = ", ".join(sorted(TOOL_REGISTRY.keys()))
    try:
        plan = await structured_complete(
            prompt=(
                f"You are {agent_name}. Select up to 4 tools to investigate this mission.\n"
                f"Mission: {mission}\n"
                f"Available tools: {tool_names}\n"
                "Return only structured JSON."
            ),
            output_model=ToolPlanModel,
            system="Choose only the tools needed to answer the mission rigorously.",
            workflow_id=workflow_id,
            agent_name=agent_name,
        )
    except Exception:
        plan = ToolPlanModel(tool_calls=[])

    tool_outputs = await _run_tool_plan(context, plan)
    try:
        result = await structured_complete(
            prompt=(
                f"You are {agent_name}. Produce a rigorous specialist risk assessment.\n"
                f"Mission: {mission}\n"
                f"Context JSON:\n{json.dumps(context, default=str)[:10000]}\n\n"
                f"Tool outputs JSON:\n{json.dumps(tool_outputs, default=str)[:12000]}\n"
                "Return only structured JSON matching the required schema."
            ),
            output_model=SpecialistOutputModel,
            system=(
                "Produce concise, decision-useful findings. "
                "Use the provided evidence and include recommended actions."
            ),
            workflow_id=workflow_id,
            agent_name=agent_name,
        )
        return result
    except (ValidationError, Exception):
        return _fallback_specialist_output(agent_name, context)
