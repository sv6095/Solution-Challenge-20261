from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import asyncio
import contextvars

from services.firestore import persist_reasoning_step

current_tenant_id = contextvars.ContextVar("current_tenant_id", default="default")


def log_reasoning_step(
    workflow_id: str,
    agent: str,
    stage: str,
    detail: str,
    status: str = "success",
    output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Append one reasoning row for the Agent Reasoning panel (Firestore subcollection or SQLite).
    Also pushes the step via WebSocket for real-time dashboard updates.
    """
    now = datetime.now(timezone.utc)
    doc: dict[str, Any] = {
        "customer_id": current_tenant_id.get(),
        "tenant_id": current_tenant_id.get(),
        "agent": agent,
        "stage": stage,
        "detail": detail,
        "status": status,
        "output": output or {},
        "timestamp": now.isoformat(),
        "timestamp_ms": int(now.timestamp() * 1000),
    }
    persist_reasoning_step(workflow_id, doc)

    # ── Real-time WebSocket push (best-effort) ────────────────────────────
    try:
        from services.event_bus import push_reasoning_step
        tenant_id = current_tenant_id.get()
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(push_reasoning_step(tenant_id, workflow_id, doc))
    except Exception:
        pass  # WebSocket push is non-blocking; persistence already succeeded

    return doc

