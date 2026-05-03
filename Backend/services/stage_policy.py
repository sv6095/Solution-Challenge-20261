"""
stage_policy.py — Stage Failure Policy Framework
=================================================
Defines the system-wide retry, timeout, fallback, and terminal-code
policy for every stage in the autonomous pipeline.

Why this exists:
  The pipeline currently has no defined behavior when a stage fails:
    - Signal fetch fails → should retry 3x with backoff
    - GNN propagation fails → should fallback to distance-only scoring, NOT crash
    - RFQ send fails → should log to audit, NOT silently swallow
    - Approval gate timeout → should ESCALATE, NOT leave incident in limbo

This module provides:
  1. `StagePolicy` — data class describing failure behavior per stage
  2. `PIPELINE_POLICIES` — complete policy table for all pipeline stages
  3. `execute_with_policy()` — decorator/wrapper that enforces the policy
  4. `StageOutcome` — typed result with terminal code propagation

Concepts:
  - RETRY:    Transient failure → retry N times with exponential backoff
  - FALLBACK: Stage has a defined fallback function to call instead
  - SKIP:     Stage can be skipped without invalidating the pipeline
  - TERMINAL: Failure is unrecoverable → abort pipeline, write audit

Terminal codes (from EU CSDDD / ISO 28000 inspired taxonomy):
  T001 — Graph build failed: no supplier nodes loaded
  T002 — GNN propagation failed with no fallback possible
  T003 — Critical financial assessment error
  T004 — Route generation completely failed
  T005 — RFQ generation failed after all retries + template fallback
  T006 — Approval execution failed: RFQ send failed after retries
  T007 — Idempotency violation: duplicate approval detected
  T008 — Authorization denied: unauthorized operation attempted
"""
from __future__ import annotations

import asyncio
import functools
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Literal


# ── Terminal codes ────────────────────────────────────────────────────────────


class TerminalCode:
    GRAPH_BUILD_FAILED = "T001"
    GNN_PROPAGATION_FAILED = "T002"
    FINANCIAL_ASSESSMENT_ERROR = "T003"
    ROUTE_GENERATION_FAILED = "T004"
    RFQ_GENERATION_FAILED = "T005"
    APPROVAL_EXECUTION_FAILED = "T006"
    IDEMPOTENCY_VIOLATION = "T007"
    AUTHORIZATION_DENIED = "T008"


# ── Stage outcome ─────────────────────────────────────────────────────────────


FailureMode = Literal["RETRY", "FALLBACK", "SKIP", "TERMINAL"]


@dataclass
class StageOutcome:
    """Result of executing a stage under policy control."""
    stage: str
    success: bool
    result: Any = None
    error: str = ""
    terminal_code: str = ""
    attempts: int = 1
    used_fallback: bool = False
    skipped: bool = False
    elapsed_ms: float = 0.0

    @property
    def is_terminal(self) -> bool:
        return bool(self.terminal_code)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "success": self.success,
            "error": self.error,
            "terminal_code": self.terminal_code,
            "attempts": self.attempts,
            "used_fallback": self.used_fallback,
            "skipped": self.skipped,
            "elapsed_ms": round(self.elapsed_ms, 2),
        }


# ── Policy config ─────────────────────────────────────────────────────────────


@dataclass
class StagePolicy:
    """
    Complete failure policy for a single pipeline stage.

    Attributes:
        name:           Human-readable stage name
        failure_mode:   What to do on failure (RETRY | FALLBACK | SKIP | TERMINAL)
        max_retries:    Number of retry attempts (0 = no retry)
        retry_backoff_s: Base seconds between retries (doubles each attempt)
        timeout_s:      Max seconds to allow the stage to run (0 = unlimited)
        terminal_code:  Code emitted if stage is TERMINAL and fails
        fallback_fn:    Async function to call if primary fails (FALLBACK mode only)
        skip_on_empty:  If True, skip stage when input data is empty rather than fail
        required:       If False, stage failure never propagates to TERMINAL
    """
    name: str
    failure_mode: FailureMode = "RETRY"
    max_retries: int = 2
    retry_backoff_s: float = 1.0
    timeout_s: float = 30.0
    terminal_code: str = ""
    fallback_fn: Callable | None = field(default=None, repr=False)
    skip_on_empty: bool = False
    required: bool = True


# ── Master policy table ───────────────────────────────────────────────────────


async def _fallback_gnn_scoring(event: dict, graph: Any) -> Any:
    """
    Distance-only risk scoring when GNN propagation fails.
    Returns a minimal GNNResult-compatible dict.
    """
    import math

    lat = float(event.get("lat", 0))
    lng = float(event.get("lng", 0))
    radius = float(event.get("radius_km", 150))
    severity = float(event.get("severity_raw", event.get("severity", 3.0)))

    # Simple distance-only scoring
    affected = []
    for nid, node in (graph.nodes if hasattr(graph, "nodes") else {}).items():
        dlat = math.radians(node.lat - lat)
        dlng = math.radians(node.lng - lng)
        a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat)) * math.cos(math.radians(node.lat)) * math.sin(dlng / 2) ** 2
        dist = 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        if dist < radius:
            score = max(0.3, 1.0 - (dist / radius)) * min(1.0, severity / 10.0)
            node.risk_score = round(score, 3)
            node.exposure_usd = round(node.contract_value_usd * score * 0.5, 2)
            node.days_to_stockout = max(1.0, node.safety_stock_days * (1 - score))
            affected.append(node)

    # Return a minimal GNNResult-like object
    class _FallbackResult:
        affected_nodes = affected
        confidence = 0.55  # reduced confidence for fallback
        all_scores: dict = {}

    return _FallbackResult()


async def _fallback_route_generation(
    origin_lat: float, origin_lng: float,
    dest_lat: float, dest_lng: float,
    event_title: str, **_kwargs
) -> list[dict]:
    """Minimal route generation fallback: air only."""
    import math
    dlat = math.radians(dest_lat - origin_lat)
    dlng = math.radians(dest_lng - origin_lng)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(origin_lat)) * math.cos(math.radians(dest_lat)) * math.sin(dlng / 2) ** 2
    dist = 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return [{
        "mode": "air",
        "description": f"Air freight (fallback) · {dist:.0f}km",
        "transit_days": round(max(0.5, dist / 8000), 1),
        "cost_usd": round(dist * 0.85, 0),
        "risk_score": 0.2,
        "recommended": True,
        "status_label": "Best (Fallback)",
        "_is_fallback": True,
    }]


async def _fallback_rfq_template(
    event_title: str,
    backup_supplier: dict | None,
    total_exposure: float,
    company_name: str,
    **_kwargs,
) -> dict:
    """Pre-written RFQ template when LLM is unavailable."""
    name = backup_supplier.get("name", "Backup Supplier") if backup_supplier else "Backup Supplier"
    email = backup_supplier.get("email", "procurement@supplier.com") if backup_supplier else "procurement@supplier.com"
    return {
        "to": email,
        "subject": f"URGENT: Emergency RFQ — {event_title}",
        "body": (
            f"Dear {name} team,\n\n"
            f"We are reaching out urgently due to '{event_title}' disrupting our supply chain.\n"
            f"Financial exposure at risk: ${total_exposure:,.0f} USD.\n\n"
            f"Please confirm your current capacity and earliest available ship date.\n"
            f"Incoterm: DAP. Payment: Net 30.\n\n"
            f"Regards,\n{company_name} Procurement"
        ),
        "provider": "template-fallback",
        "editable": True,
        "_is_fallback": True,
    }


# The complete policy table
PIPELINE_POLICIES: dict[str, StagePolicy] = {
    "graph_build": StagePolicy(
        name="Supply Chain Graph Build",
        failure_mode="TERMINAL",
        max_retries=0,
        timeout_s=10.0,
        terminal_code=TerminalCode.GRAPH_BUILD_FAILED,
        required=True,
    ),
    "signal_detection": StagePolicy(
        name="Signal Detection & Ingestion",
        failure_mode="RETRY",
        max_retries=3,
        retry_backoff_s=1.0,
        timeout_s=20.0,
        skip_on_empty=True,
        required=False,  # pipeline can continue with partial signals
    ),
    "cross_verification": StagePolicy(
        name="Cross-Source Signal Verification",
        failure_mode="SKIP",
        max_retries=0,
        timeout_s=5.0,
        required=False,
    ),
    "gnn_propagation": StagePolicy(
        name="GNN Risk Propagation",
        failure_mode="FALLBACK",
        max_retries=1,
        retry_backoff_s=0.5,
        timeout_s=15.0,
        fallback_fn=_fallback_gnn_scoring,
        terminal_code=TerminalCode.GNN_PROPAGATION_FAILED,
        required=True,
    ),
    "financial_assessment": StagePolicy(
        name="Financial Exposure Assessment",
        failure_mode="RETRY",
        max_retries=2,
        retry_backoff_s=0.5,
        timeout_s=10.0,
        terminal_code=TerminalCode.FINANCIAL_ASSESSMENT_ERROR,
        required=True,
    ),
    "route_generation": StagePolicy(
        name="Multi-Modal Route Generation",
        failure_mode="FALLBACK",
        max_retries=1,
        retry_backoff_s=0.5,
        timeout_s=10.0,
        fallback_fn=_fallback_route_generation,
        terminal_code=TerminalCode.ROUTE_GENERATION_FAILED,
        required=True,
    ),
    "political_risk": StagePolicy(
        name="Geopolitical Risk Analysis",
        failure_mode="SKIP",
        max_retries=0,
        timeout_s=8.0,
        required=False,
    ),
    "logistics_risk": StagePolicy(
        name="Logistics Capacity Analysis",
        failure_mode="SKIP",
        max_retries=0,
        timeout_s=8.0,
        required=False,
    ),
    "tariff_risk": StagePolicy(
        name="Tariff & Trade Compliance",
        failure_mode="SKIP",
        max_retries=0,
        timeout_s=8.0,
        required=False,
    ),
    "rfq_generation": StagePolicy(
        name="RFQ Draft Generation",
        failure_mode="FALLBACK",
        max_retries=2,
        retry_backoff_s=2.0,
        timeout_s=30.0,             # LLM calls can be slow
        fallback_fn=_fallback_rfq_template,
        terminal_code=TerminalCode.RFQ_GENERATION_FAILED,
        required=True,
    ),
    "rfq_dispatch": StagePolicy(
        name="RFQ Email Dispatch",
        failure_mode="RETRY",
        max_retries=3,
        retry_backoff_s=2.0,
        timeout_s=30.0,
        terminal_code=TerminalCode.APPROVAL_EXECUTION_FAILED,
        required=True,
    ),
    "audit_write": StagePolicy(
        name="Audit Record Write",
        failure_mode="RETRY",
        max_retries=5,
        retry_backoff_s=0.5,
        timeout_s=10.0,
        required=True,  # Must never lose audit records
    ),
    "approval_gate": StagePolicy(
        name="Human Approval Gate",
        failure_mode="TERMINAL",
        max_retries=0,
        timeout_s=0,                # No timeout — waits indefinitely for human
        terminal_code=TerminalCode.IDEMPOTENCY_VIOLATION,
        required=True,
    ),
}


# ── Policy executor ───────────────────────────────────────────────────────────


async def execute_with_policy(
    stage_key: str,
    fn: Callable,
    *args: Any,
    policy: StagePolicy | None = None,
    logging_fn: Callable | None = None,
    **kwargs: Any,
) -> StageOutcome:
    """
    Execute a pipeline stage function under its policy.

    Args:
        stage_key:  Key into PIPELINE_POLICIES (e.g., "gnn_propagation")
        fn:         The async stage function to call
        *args:      Positional args for fn
        policy:     Override policy (defaults to PIPELINE_POLICIES[stage_key])
        logging_fn: Optional callable(stage, detail, status) for reasoning logs
        **kwargs:   Keyword args for fn

    Returns:
        StageOutcome with result or error details.
    """
    p = policy or PIPELINE_POLICIES.get(stage_key, StagePolicy(name=stage_key))
    start = datetime.now(timezone.utc)
    last_error = ""
    attempts = 0

    async def _call_fn() -> Any:
        if p.timeout_s > 0:
            return await asyncio.wait_for(
                fn(*args, **kwargs) if asyncio.iscoroutinefunction(fn) else asyncio.to_thread(fn, *args, **kwargs),
                timeout=p.timeout_s,
            )
        if asyncio.iscoroutinefunction(fn):
            return await fn(*args, **kwargs)
        return fn(*args, **kwargs)

    # ── Retry loop ──
    for attempt in range(max(1, p.max_retries + 1)):
        attempts = attempt + 1
        try:
            result = await _call_fn()
            elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            if logging_fn:
                try:
                    logging_fn(stage_key, f"Stage '{p.name}' completed in {elapsed:.0f}ms", "success")
                except Exception:
                    pass
            return StageOutcome(
                stage=stage_key,
                success=True,
                result=result,
                attempts=attempts,
                elapsed_ms=elapsed,
            )
        except asyncio.TimeoutError:
            last_error = f"Stage '{p.name}' timed out after {p.timeout_s}s"
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            tb = traceback.format_exc(limit=3)

        if logging_fn:
            try:
                logging_fn(stage_key, f"Attempt {attempts}/{p.max_retries + 1} failed: {last_error[:200]}", "error")
            except Exception:
                pass

        # Backoff before next retry
        if attempt < p.max_retries:
            backoff = p.retry_backoff_s * (2 ** attempt)
            await asyncio.sleep(min(backoff, 30.0))

    # ── All retries exhausted ──
    elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000

    if p.failure_mode == "FALLBACK" and p.fallback_fn:
        try:
            fb_result = await (
                p.fallback_fn(*args, **kwargs)
                if asyncio.iscoroutinefunction(p.fallback_fn)
                else asyncio.to_thread(p.fallback_fn, *args, **kwargs)
            )
            if logging_fn:
                try:
                    logging_fn(stage_key, f"Stage '{p.name}' using fallback after {attempts} attempts", "fallback")
                except Exception:
                    pass
            return StageOutcome(
                stage=stage_key,
                success=True,
                result=fb_result,
                error=last_error,
                attempts=attempts,
                used_fallback=True,
                elapsed_ms=elapsed,
            )
        except Exception as fb_exc:
            last_error = f"Primary failed; fallback also failed: {fb_exc}"

    if p.failure_mode == "SKIP" or not p.required:
        if logging_fn:
            try:
                logging_fn(stage_key, f"Stage '{p.name}' skipped after failure: {last_error[:200]}", "fallback")
            except Exception:
                pass
        return StageOutcome(
            stage=stage_key,
            success=False,
            error=last_error,
            attempts=attempts,
            skipped=True,
            elapsed_ms=elapsed,
        )

    # TERMINAL or required RETRY-exhausted
    return StageOutcome(
        stage=stage_key,
        success=False,
        error=last_error,
        terminal_code=p.terminal_code or TerminalCode.GRAPH_BUILD_FAILED,
        attempts=attempts,
        elapsed_ms=elapsed,
    )


def get_policy(stage_key: str) -> StagePolicy | None:
    """Return the policy for a given stage key."""
    return PIPELINE_POLICIES.get(stage_key)


def list_policies() -> list[dict[str, Any]]:
    """Return all policies as dicts (for admin/debug endpoints)."""
    return [
        {
            "stage_key": k,
            "name": p.name,
            "failure_mode": p.failure_mode,
            "max_retries": p.max_retries,
            "timeout_s": p.timeout_s,
            "has_fallback": p.fallback_fn is not None,
            "terminal_code": p.terminal_code,
            "required": p.required,
        }
        for k, p in PIPELINE_POLICIES.items()
    ]
