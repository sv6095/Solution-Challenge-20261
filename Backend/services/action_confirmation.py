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

Storage: Firestore via firestore_store.py.

Schema:
  action_logs collection
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

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from google.cloud.firestore_v1.base_query import FieldFilter

from services.firestore_store import _client, add_audit


# ── Schema migration (idempotent) ─────────────────────────────────────────────


def _ensure_schema() -> None:
    """Firestore does not require runtime schema creation."""
    _client()


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


def _dict_to_record(data: dict[str, Any], include_milestones: bool = False) -> ActionRecord:
    rec = ActionRecord(
        action_id=str(data.get("action_id") or ""),
        incident_id=str(data.get("incident_id") or ""),
        action_type=str(data.get("action_type") or "audit_record"),  # type: ignore[arg-type]
        payload=data.get("payload") if isinstance(data.get("payload"), dict) else {},
        status=str(data.get("status") or "PENDING"),  # type: ignore[arg-type]
        dispatched_at=str(data.get("dispatched_at") or ""),
        delivered_at=str(data.get("delivered_at") or ""),
        acked_at=str(data.get("acked_at") or ""),
        updated_at=str(data.get("updated_at") or ""),
    )

    if include_milestones:
        rows = _client().collection("action_logs").document(rec.action_id).collection("milestones").order_by("occurred_at").stream()
        rec.milestones = [doc.to_dict() or {} for doc in rows]
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

    _client().collection("action_logs").document(action_id).set({
        "action_id": action_id,
        "incident_id": incident_id,
        "action_type": action_type,
        "payload": payload,
        "status": "SENT",
        "dispatched_at": now,
        "updated_at": now,
    })

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
    ref = _client().collection("action_logs").document(action_id)
    if not ref.get().exists:
        return None
    ref.set({"status": "DELIVERED", "delivered_at": now, "updated_at": now}, merge=True)
    _add_milestone(action_id, "DELIVERED", delivery_detail, now)

    add_audit("action_delivered", f"{action_id}:{delivery_detail[:120]}")
    return get_action(action_id)


def record_acknowledgement(action_id: str, acked_by: str = "", detail: str = "") -> ActionRecord | None:
    """
    Mark an action as ACKNOWLEDGED (e.g., supplier replied to RFQ).
    This is the final state for RFQ flows.
    """
    now = _now()
    ref = _client().collection("action_logs").document(action_id)
    if not ref.get().exists:
        return None
    ref.set({"status": "ACKNOWLEDGED", "acked_at": now, "updated_at": now}, merge=True)
    _add_milestone(action_id, "ACKNOWLEDGED", f"By {acked_by}: {detail}"[:200], now)

    add_audit("action_acknowledged", f"{action_id}:by={acked_by}")
    return get_action(action_id)


def mark_failed(action_id: str, reason: str = "") -> ActionRecord | None:
    """Mark an action as FAILED with a reason."""
    now = _now()
    ref = _client().collection("action_logs").document(action_id)
    if not ref.get().exists:
        return None
    ref.set({"status": "FAILED", "updated_at": now}, merge=True)
    _add_milestone(action_id, "FAILED", reason[:200], now)

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
    _add_milestone(action_id, milestone, detail, ts)
    return True


def _add_milestone(action_id: str, milestone: str, detail: str, ts: str) -> None:
    _client().collection("action_logs").document(action_id).collection("milestones").document().set({
        "milestone": milestone,
        "detail": detail or "",
        "occurred_at": ts,
    })


def get_action(action_id: str, include_milestones: bool = True) -> ActionRecord | None:
    doc = _client().collection("action_logs").document(action_id).get()
    if not doc.exists:
        return None
    return _dict_to_record(doc.to_dict() or {}, include_milestones=include_milestones)


def list_actions_for_incident(incident_id: str) -> list[ActionRecord]:
    # Avoid composite index: filter only, sort in Python.
    rows = (
        _client()
        .collection("action_logs")
        .where(filter=FieldFilter("incident_id", "==", incident_id))
        .stream()
    )
    docs = [_dict_to_record(doc.to_dict() or {}, include_milestones=True) for doc in rows]
    docs.sort(key=lambda r: r.dispatched_at or "")
    return docs


def list_pending_actions(limit: int = 100) -> list[ActionRecord]:
    """Return actions still in SENT state (awaiting delivery confirmation)."""
    # Avoid composite index: filter only, sort in Python.
    rows = (
        _client()
        .collection("action_logs")
        .where(filter=FieldFilter("status", "==", "SENT"))
        .stream()
    )
    docs = [_dict_to_record(doc.to_dict() or {}) for doc in rows]
    docs.sort(key=lambda r: r.dispatched_at or "")
    return docs[:limit]


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
