"""
action_confirmation.py — Action Confirmation & Delivery Tracking Service
==========================================================================
Tracks the full dispatch → delivery → acknowledgement lifecycle for every
external action taken by the autonomous pipeline.

Covers:
  - RFQ email dispatch (via Gmail / SMTP / audit-log fallback)
  - Route confirmation (AWB/booking reference)
  - Supplier acknowledgement (inbound reply detection)
  - Delivery milestone tracking (shipped → in-transit → delivered)

Why this exists:
  - The pipeline was firing RFQs without any record of receipt.
  - Approvals had no ack tracking — we didn't know if backup supplier replied.
  - This service creates an immutable action ledger so every step is traceable.

Storage: SQLite via local_store.py (same DB as incidents).
Firestore upgrade: swap dispatch_action() / get_action() to use db_provider.

Schema:
  action_logs table (added to local_store.py migration)
  ├── action_id     TEXT PK         (ack_<hex12>)
  ├── incident_id   TEXT NOT NULL   (parent incident)
  ├── action_type   TEXT NOT NULL   (rfq_dispatch | route_confirm | delivery_ack | ...)
  ├── payload_json  TEXT NOT NULL   (structured action details)
  ├── status        TEXT NOT NULL   (PENDING | SENT | DELIVERED | ACKNOWLEDGED | FAILED)
  ├── dispatched_at TEXT
  ├── delivered_at  TEXT
  ├── acked_at      TEXT
  └── updated_at    TEXT
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from services.local_store import DB_PATH, add_audit


# ── Schema migration (idempotent) ─────────────────────────────────────────────


def _ensure_schema() -> None:
    """Create action_logs table if it doesn't exist. Called at import time."""
    with sqlite3.connect(DB_PATH) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("""
            CREATE TABLE IF NOT EXISTS action_logs (
                action_id     TEXT PRIMARY KEY,
                incident_id   TEXT NOT NULL,
                action_type   TEXT NOT NULL,
                payload_json  TEXT NOT NULL,
                status        TEXT NOT NULL DEFAULT 'PENDING',
                dispatched_at TEXT,
                delivered_at  TEXT,
                acked_at      TEXT,
                updated_at    TEXT NOT NULL
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_action_incident ON action_logs(incident_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_action_status ON action_logs(status)")

        # delivery_milestones tracks granular checkpoints (shipped, cleared, etc.)
        con.execute("""
            CREATE TABLE IF NOT EXISTS delivery_milestones (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                action_id     TEXT NOT NULL,
                milestone     TEXT NOT NULL,
                detail        TEXT,
                occurred_at   TEXT NOT NULL
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_milestone_action ON delivery_milestones(action_id)")


_ensure_schema()


# ── Data model ────────────────────────────────────────────────────────────────


ActionStatus = Literal["PENDING", "SENT", "DELIVERED", "ACKNOWLEDGED", "FAILED", "CANCELLED"]

ActionType = Literal[
    "rfq_dispatch",
    "route_confirm",
    "delivery_ack",
    "supplier_notification",
    "audit_record",
    "certificate_issue",
]


@dataclass
class ActionRecord:
    action_id: str
    incident_id: str
    action_type: ActionType
    payload: dict[str, Any]
    status: ActionStatus = "PENDING"
    dispatched_at: str = ""
    delivered_at: str = ""
    acked_at: str = ""
    updated_at: str = ""
    milestones: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("milestones")
        return d


# ── Internal helpers ──────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def _row_to_record(row: tuple, include_milestones: bool = False) -> ActionRecord:
    action_id, incident_id, action_type, payload_json, status, dispatched_at, delivered_at, acked_at, updated_at = row
    try:
        payload = json.loads(payload_json or "{}")
    except Exception:
        payload = {}

    rec = ActionRecord(
        action_id=action_id,
        incident_id=incident_id,
        action_type=action_type,  # type: ignore[arg-type]
        payload=payload,
        status=status,  # type: ignore[arg-type]
        dispatched_at=dispatched_at or "",
        delivered_at=delivered_at or "",
        acked_at=acked_at or "",
        updated_at=updated_at or "",
    )

    if include_milestones:
        with _conn() as con:
            ms_rows = con.execute(
                "SELECT milestone, detail, occurred_at FROM delivery_milestones WHERE action_id = ? ORDER BY id ASC",
                (action_id,),
            ).fetchall()
        rec.milestones = [
            {"milestone": r[0], "detail": r[1] or "", "occurred_at": r[2]}
            for r in ms_rows
        ]
    return rec


# ── Public API ────────────────────────────────────────────────────────────────


def dispatch_action(
    incident_id: str,
    action_type: ActionType,
    payload: dict[str, Any],
) -> ActionRecord:
    """
    Register a new action and mark it as dispatched immediately.

    Call this right BEFORE sending the RFC/email/booking so the record
    exists even if the send fails (status transitions to FAILED on error).

    Returns the created ActionRecord.
    """
    action_id = f"ack_{uuid4().hex[:12]}"
    now = _now()

    with _conn() as con:
        con.execute(
            """
            INSERT INTO action_logs
                (action_id, incident_id, action_type, payload_json, status,
                 dispatched_at, updated_at)
            VALUES (?, ?, ?, ?, 'SENT', ?, ?)
            """,
            (action_id, incident_id, action_type, json.dumps(payload), now, now),
        )

    add_audit("action_dispatched", f"{action_id}:{action_type}:{incident_id}")

    return ActionRecord(
        action_id=action_id,
        incident_id=incident_id,
        action_type=action_type,  # type: ignore[arg-type]
        payload=payload,
        status="SENT",
        dispatched_at=now,
        updated_at=now,
    )


def confirm_delivery(action_id: str, delivery_detail: str = "") -> ActionRecord | None:
    """
    Mark an action as DELIVERED (e.g., email accepted by recipient MTA).
    """
    now = _now()
    with _conn() as con:
        cur = con.execute(
            "UPDATE action_logs SET status = 'DELIVERED', delivered_at = ?, updated_at = ? WHERE action_id = ?",
            (now, now, action_id),
        )
        if not cur.rowcount:
            return None
        _add_milestone(con, action_id, "DELIVERED", delivery_detail, now)

    add_audit("action_delivered", f"{action_id}:{delivery_detail[:120]}")
    return get_action(action_id)


def record_acknowledgement(action_id: str, acked_by: str = "", detail: str = "") -> ActionRecord | None:
    """
    Mark an action as ACKNOWLEDGED (e.g., supplier replied to RFQ).
    This is the final state for RFQ flows.
    """
    now = _now()
    with _conn() as con:
        cur = con.execute(
            "UPDATE action_logs SET status = 'ACKNOWLEDGED', acked_at = ?, updated_at = ? WHERE action_id = ?",
            (now, now, action_id),
        )
        if not cur.rowcount:
            return None
        _add_milestone(con, action_id, "ACKNOWLEDGED", f"By {acked_by}: {detail}"[:200], now)

    add_audit("action_acknowledged", f"{action_id}:by={acked_by}")
    return get_action(action_id)


def mark_failed(action_id: str, reason: str = "") -> ActionRecord | None:
    """Mark an action as FAILED with a reason."""
    now = _now()
    with _conn() as con:
        cur = con.execute(
            "UPDATE action_logs SET status = 'FAILED', updated_at = ? WHERE action_id = ?",
            (now, action_id),
        )
        if not cur.rowcount:
            return None
        _add_milestone(con, action_id, "FAILED", reason[:200], now)

    add_audit("action_failed", f"{action_id}:{reason[:120]}")
    return get_action(action_id)


def add_delivery_milestone(
    action_id: str,
    milestone: str,
    detail: str = "",
    occurred_at: str | None = None,
) -> bool:
    """
    Append a granular delivery milestone to an action.

    Examples:
      milestone="PICKED_UP"    detail="Courier collected 08:30 SGT"
      milestone="CUSTOMS_CLEARED"  detail="Singapore customs: cleared 14:00"
      milestone="DELIVERED"    detail="Arrived at factory gate"
    """
    ts = occurred_at or _now()
    with _conn() as con:
        _add_milestone(con, action_id, milestone, detail, ts)
    return True


def _add_milestone(con: sqlite3.Connection, action_id: str, milestone: str, detail: str, ts: str) -> None:
    con.execute(
        "INSERT INTO delivery_milestones (action_id, milestone, detail, occurred_at) VALUES (?, ?, ?, ?)",
        (action_id, milestone, detail or "", ts),
    )


def get_action(action_id: str, include_milestones: bool = True) -> ActionRecord | None:
    with _conn() as con:
        row = con.execute(
            "SELECT action_id, incident_id, action_type, payload_json, status, "
            "dispatched_at, delivered_at, acked_at, updated_at "
            "FROM action_logs WHERE action_id = ?",
            (action_id,),
        ).fetchone()
    if not row:
        return None
    return _row_to_record(row, include_milestones=include_milestones)


def list_actions_for_incident(incident_id: str) -> list[ActionRecord]:
    with _conn() as con:
        rows = con.execute(
            "SELECT action_id, incident_id, action_type, payload_json, status, "
            "dispatched_at, delivered_at, acked_at, updated_at "
            "FROM action_logs WHERE incident_id = ? ORDER BY dispatched_at ASC",
            (incident_id,),
        ).fetchall()
    return [_row_to_record(r, include_milestones=True) for r in rows]


def list_pending_actions(limit: int = 100) -> list[ActionRecord]:
    """Return actions still in SENT state (awaiting delivery confirmation)."""
    with _conn() as con:
        rows = con.execute(
            "SELECT action_id, incident_id, action_type, payload_json, status, "
            "dispatched_at, delivered_at, acked_at, updated_at "
            "FROM action_logs WHERE status = 'SENT' ORDER BY dispatched_at ASC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_row_to_record(r) for r in rows]


def action_summary_for_incident(incident_id: str) -> dict[str, Any]:
    """
    Return a compact summary of all actions for an incident.
    Used by the frontend incident card to show execution status.
    """
    actions = list_actions_for_incident(incident_id)
    return {
        "incident_id": incident_id,
        "total": len(actions),
        "by_status": {
            status: sum(1 for a in actions if a.status == status)
            for status in ["PENDING", "SENT", "DELIVERED", "ACKNOWLEDGED", "FAILED"]
        },
        "actions": [
            {
                "action_id": a.action_id,
                "type": a.action_type,
                "status": a.status,
                "dispatched_at": a.dispatched_at,
                "acked_at": a.acked_at,
                "milestones": a.milestones,
            }
            for a in actions
        ],
    }
