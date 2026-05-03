from __future__ import annotations

import asyncio
import time
from typing import Any
from uuid import uuid4

from agents.signal_agent import fetch_gdelt, fetch_gnews, fetch_nasa_eonet, fetch_newsapi
from managers.chatbot_manager import ChatbotManager
from services.db_provider import db_provider
from services.firestore import read_reasoning_steps
from workflows.langgraph_workflow import WorkflowGraphManager

try:
    from mcp.server import MCPServer
except Exception:  # pragma: no cover - optional dependency
    MCPServer = None

chatbot_manager = ChatbotManager()
graph_manager = WorkflowGraphManager()
server = MCPServer("praecantator") if MCPServer else None


async def get_supplier_exposure(user_id: str) -> dict:
    context = db_provider.read_context(user_id) or {}
    suppliers = context.get("suppliers", []) if isinstance(context, dict) else []
    normalized = []
    for idx, supplier in enumerate(suppliers):
        if not isinstance(supplier, dict):
            continue
        score = float(supplier.get("exposure_score") or supplier.get("exposureScore") or 0.0)
        normalized.append(
            {
                "supplier_id": supplier.get("supplier_id") or f"sup_{idx+1}",
                "name": supplier.get("name") or f"Supplier {idx+1}",
                "score": score,
                "country": supplier.get("country"),
                "tier": supplier.get("tier"),
            }
        )
    total = len(normalized)
    avg = round(sum(row["score"] for row in normalized) / total, 2) if total else 0.0
    critical = sum(1 for row in normalized if row["score"] >= 80)
    return {"total_suppliers": total, "avg_exposure_score": avg, "critical_count": critical, "suppliers": normalized}


async def trigger_workflow(user_id: str, signal_id: str) -> dict:
    workflow_id = f"wf_{int(time.time())}_{uuid4().hex[:8]}"
    signal = {"signal_id": signal_id, "event_type": "manual_trigger", "severity": 7.5, "title": "Triggered signal", "location": "Unknown"}
    initial_state = {
        "workflow_id": workflow_id,
        "user_id": user_id,
        "current_stage": "DETECT",
        "signals": [signal],
        "selected_signal": signal,
        "affected_suppliers": [],
        "exposure_usd": 0.0,
        "exposure_local": 0.0,
        "local_currency": "USD",
        "days_at_risk": 0,
        "confidence": 0.0,
        "currency_risk_index": 0.0,
        "inflation_rate": 0.0,
        "assessment_summary": "",
        "route_comparison": [],
        "recommended_mode": "",
        "rl_confidence": 0.0,
        "rfq_sent": False,
        "reasoning_steps": [],
    }
    asyncio.create_task(graph_manager.start_workflow(initial_state))
    return {"workflow_id": workflow_id, "status": "started"}


async def get_route_options(origin: str, destination: str, cargo_weight_tonnes: float) -> dict:
    return {
        "origin": origin,
        "destination": destination,
        "cargo_weight_tonnes": cargo_weight_tonnes,
        "message": "Use the workflow routing endpoint for lane-precise route computation from coordinates.",
    }


async def get_reasoning_trail(workflow_id: str) -> list[dict]:
    return read_reasoning_steps(workflow_id, limit=500)


async def get_live_signals(user_id: str, severity_threshold: float = 5.0) -> list[dict]:
    _ = user_id
    nasa = await fetch_nasa_eonet()
    gdelt = await fetch_gdelt()
    news = await fetch_newsapi(None)
    gnews = await fetch_gnews(None)
    signals = nasa + gdelt + news + gnews
    return [row for row in signals if float(row.get("severity") or 0.0) >= severity_threshold]


if server:
    server.tool()(get_supplier_exposure)
    server.tool()(trigger_workflow)
    server.tool()(get_route_options)
    server.tool()(get_reasoning_trail)
    server.tool()(get_live_signals)
