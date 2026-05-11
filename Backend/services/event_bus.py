"""
event_bus.py — Real-Time WebSocket Event Bus
=============================================
Closes SCRM Gap 4: replaces 30-second polling with sub-second push
notifications for incidents, reasoning steps, and checkpoint events.

Architecture:
  - FastAPI WebSocket endpoint at /ws/{tenant_id}
  - In-memory pub/sub: tenant_id → set of connected WebSocket clients
  - Any backend service can call broadcast() to push events
  - Frontend subscribes once on mount, receives JSON events:
    { "type": "incident_created" | "reasoning_step" | "checkpoint_raised" | ...,
      "payload": { ... } }

Thread safety:
  Uses asyncio.Lock for connection management. All broadcasts are
  non-blocking (fire-and-forget to each client; dropped on backpressure).

Scaling note:
  For multi-process deployment, replace in-memory dict with Redis Pub/Sub.
  The broadcast() interface remains identical.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
HEARTBEAT_INTERVAL_SECONDS = 20


# ── Connection registry ───────────────────────────────────────────────────────

# tenant_id → set of connected WebSocket clients
_connections: dict[str, set[WebSocket]] = {}
_lock = asyncio.Lock()


async def register(tenant_id: str, ws: WebSocket) -> None:
    """Register a WebSocket connection for a tenant."""
    async with _lock:
        if tenant_id not in _connections:
            _connections[tenant_id] = set()
        _connections[tenant_id].add(ws)
    logger.info("WS connected: tenant=%s (total=%d)", tenant_id, len(_connections.get(tenant_id, set())))


async def unregister(tenant_id: str, ws: WebSocket) -> None:
    """Remove a WebSocket connection for a tenant."""
    async with _lock:
        if tenant_id in _connections:
            _connections[tenant_id].discard(ws)
            if not _connections[tenant_id]:
                del _connections[tenant_id]
    logger.info("WS disconnected: tenant=%s", tenant_id)


def connection_count(tenant_id: str | None = None) -> int:
    """Return the number of active connections for a tenant (or total)."""
    if tenant_id:
        return len(_connections.get(tenant_id, set()))
    return sum(len(s) for s in _connections.values())


# ── Broadcasting ──────────────────────────────────────────────────────────────

async def broadcast(tenant_id: str, event_type: str, payload: dict[str, Any]) -> int:
    """
    Broadcast an event to all WebSocket clients for a tenant.
    
    Returns the number of clients that received the event.
    Silently drops messages for disconnected clients.
    
    Usage from any backend service:
        from services.event_bus import broadcast
        await broadcast(tenant_id, "incident_created", {"incident_id": "inc_123", ...})
    """
    message = json.dumps({
        "type": event_type,
        "payload": payload,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    clients = _connections.get(tenant_id, set()).copy()
    if not clients:
        return 0

    delivered = 0
    dead: list[WebSocket] = []

    for ws in clients:
        try:
            await ws.send_text(message)
            delivered += 1
        except Exception:
            dead.append(ws)

    # Clean up dead connections
    if dead:
        async with _lock:
            for ws in dead:
                _connections.get(tenant_id, set()).discard(ws)

    return delivered


async def broadcast_all(event_type: str, payload: dict[str, Any]) -> int:
    """Broadcast to ALL connected tenants (system-wide alerts)."""
    total = 0
    for tenant_id in list(_connections.keys()):
        total += await broadcast(tenant_id, event_type, payload)
    return total


# ── Convenience broadcast helpers ─────────────────────────────────────────────

async def push_incident_event(tenant_id: str, incident_id: str, status: str, summary: dict[str, Any]) -> None:
    """Push incident lifecycle event (created, updated, resolved)."""
    await broadcast(tenant_id, f"incident_{status}", {
        "incident_id": incident_id,
        "status": status,
        **summary,
    })


async def push_reasoning_step(tenant_id: str, workflow_id: str, step: dict[str, Any]) -> None:
    """Push a real-time reasoning step from an agent."""
    await broadcast(tenant_id, "reasoning_step", {
        "workflow_id": workflow_id,
        **step,
    })


async def push_checkpoint_event(tenant_id: str, checkpoint_id: str, checkpoint: dict[str, Any]) -> None:
    """Push governance checkpoint raised/resolved."""
    await broadcast(tenant_id, "checkpoint_raised", {
        "checkpoint_id": checkpoint_id,
        **checkpoint,
    })


async def push_threshold_tuned(tenant_id: str, report: dict[str, Any]) -> None:
    """Push threshold tuning results."""
    await broadcast(tenant_id, "threshold_tuned", report)


async def push_signal_detected(tenant_id: str, signal: dict[str, Any]) -> None:
    """Push new signal detection."""
    await broadcast(tenant_id, "signal_detected", signal)


# ── WebSocket handler (mounted from main.py) ─────────────────────────────────

async def websocket_handler(ws: WebSocket, tenant_id: str) -> None:
    """
    Main WebSocket handler. Mounted at /ws/{tenant_id}.
    
    Protocol:
    - Server sends JSON events to client (push model)
    - Client can send {"type": "ping"} for keepalive
    - Client can send {"type": "subscribe", "channels": [...]} for filtering
      (future: channel-based routing)
    """
    await ws.accept()
    await register(tenant_id, ws)
    stop_heartbeat = asyncio.Event()

    async def _heartbeat_loop() -> None:
        while not stop_heartbeat.is_set():
            await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
            try:
                await ws.send_text(json.dumps({"type": "heartbeat"}))
            except Exception:
                break

    heartbeat_task = asyncio.create_task(_heartbeat_loop())

    try:
        # Send connection confirmation
        await ws.send_text(json.dumps({
            "type": "connected",
            "payload": {
                "tenant_id": tenant_id,
                "active_connections": connection_count(tenant_id),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }))

        # Handle client messages; keepalive is sent by heartbeat task.
        while True:
            try:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                    msg_type = msg.get("type", "")
                    if msg_type == "ping":
                        await ws.send_text(json.dumps({
                            "type": "pong",
                            "payload": {"timestamp": datetime.now(timezone.utc).isoformat()},
                        }))
                except (json.JSONDecodeError, AttributeError):
                    pass

    except WebSocketDisconnect as exc:
        logger.info("WS client disconnected: tenant=%s code=%s", tenant_id, getattr(exc, "code", "unknown"))
    except Exception as exc:
        logger.warning("WS error for tenant=%s: %s", tenant_id, exc)
    finally:
        stop_heartbeat.set()
        heartbeat_task.cancel()
        await unregister(tenant_id, ws)
