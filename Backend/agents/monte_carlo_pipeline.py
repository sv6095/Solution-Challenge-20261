from __future__ import annotations

from typing import Any

from agents.autonomous_pipeline import run_pipeline


async def run_monte_carlo_pipeline(
    signal: dict[str, Any],
    suppliers: list[dict[str, Any]],
    context: dict[str, Any] | None,
    user_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """
    Dedicated simulation pipeline for Monte Carlo runs launched from Intelligence.

    It reuses the autonomous pipeline mechanics, but relaxes event severity filtering
    and marks any created incident as simulation-only so it stays out of the live queue.
    """
    return await run_pipeline(
        events=[signal],
        suppliers=suppliers,
        context=context if context else None,
        user_id=user_id,
        max_events=1,
        bypass_data_quality_gate=True,
        allow_no_impact_results=True,
        ignore_existing_incidents=True,
        tenant_id_override=tenant_id,
        minimum_signal_severity=0.0,
        simulation_only=True,
        affected_score_threshold=0.0,
    )
