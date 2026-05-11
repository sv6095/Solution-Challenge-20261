"""
governance_checkpoint.py — Operator Verification Checkpoints & Feedback Loop
=============================================================================
Addresses:
  ⏳ Add explicit operator-verification checkpoints for high-risk outputs
  ⏳ Add false-positive/false-negative governance feedback loop

Why this exists:
  - High-risk outputs (CRITICAL severity, large financial exposure, sole-source
    suppliers) need human sign-off BEFORE the autonomous pipeline acts on them.
  - After resolution, operators must be able to tag an incident as a true positive,
    false positive, or false negative — feeding a feedback table that drives model
    improvement and alert threshold calibration.

Collections (stored in Firestore):

  governance_checkpoints
    ├── checkpoint_id     TEXT PK
    ├── incident_id       TEXT NOT NULL
    ├── tenant_id         TEXT NOT NULL
    ├── risk_trigger      TEXT NOT NULL   (why this checkpoint was raised)
    ├── risk_level        TEXT NOT NULL   (CRITICAL | HIGH | MODERATE)
    ├── exposure_usd      REAL
    ├── gnn_confidence    REAL
    ├── status            TEXT NOT NULL   (PENDING | VERIFIED | OVERRIDDEN | EXPIRED)
    ├── verified_by       TEXT
    ├── verified_at       TEXT
    ├── override_reason   TEXT
    ├── created_at        TEXT NOT NULL
    └── expires_at        TEXT NOT NULL   (auto-expire after 4h if not actioned)

  governance_feedback
    ├── feedback_id       TEXT PK
    ├── incident_id       TEXT NOT NULL
    ├── tenant_id         TEXT NOT NULL
    ├── verdict           TEXT NOT NULL   (TRUE_POSITIVE | FALSE_POSITIVE | FALSE_NEGATIVE | UNCERTAIN)
    ├── submitted_by      TEXT NOT NULL
    ├── notes             TEXT
    ├── affected_stage    TEXT            (which pipeline stage produced the error)
    ├── created_at        TEXT NOT NULL
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from google.cloud import firestore as g_firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from services.firestore_store import _client, add_audit


# ── Schema migration (idempotent) ─────────────────────────────────────────────

def _ensure_schema() -> None:
    _client()


_ensure_schema()


# ── Constants ─────────────────────────────────────────────────────────────────

CheckpointStatus = Literal["PENDING", "VERIFIED", "OVERRIDDEN", "EXPIRED"]
FeedbackVerdict  = Literal["TRUE_POSITIVE", "FALSE_POSITIVE", "FALSE_NEGATIVE", "UNCERTAIN"]

# Thresholds that trigger a checkpoint
HIGH_RISK_EXPOSURE_USD   = 500_000   # ≥ $500K exposure
HIGH_RISK_CONFIDENCE_LOW = 0.70      # GNN confidence < 70% → needs human verification
HIGH_RISK_SEVERITY       = {"CRITICAL", "HIGH"}
CHECKPOINT_TTL_HOURS     = 4         # Checkpoints expire after 4 hours


# ── Internal helpers ──────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Checkpoint logic ──────────────────────────────────────────────────────────

def evaluate_checkpoint_triggers(incident: dict[str, Any]) -> list[str]:
    """
    Evaluate whether a given incident requires operator verification.
    Returns a list of human-readable trigger reasons (empty = no checkpoint needed).
    """
    triggers: list[str] = []
    severity = str(incident.get("severity") or "").upper()
    exposure  = float(incident.get("total_exposure_usd") or 0)
    confidence = float(incident.get("gnn_confidence") or 1.0)
    affected_nodes = incident.get("affected_nodes") or []
    has_sole_source = any(n.get("single_source") for n in affected_nodes if isinstance(n, dict))

    if severity in HIGH_RISK_SEVERITY:
        triggers.append(f"Severity={severity}: requires operator sign-off before autonomous execution")
    if exposure >= HIGH_RISK_EXPOSURE_USD:
        triggers.append(f"Exposure=${exposure:,.0f} USD exceeds ${HIGH_RISK_EXPOSURE_USD:,.0f} threshold")
    if 0 < confidence < HIGH_RISK_CONFIDENCE_LOW:
        triggers.append(f"GNN confidence={confidence:.0%} below {HIGH_RISK_CONFIDENCE_LOW:.0%} threshold")
    if has_sole_source:
        triggers.append("Sole-source supplier affected: disruption has no automatic backup")

    return triggers


def create_checkpoint(
    incident_id: str,
    tenant_id: str,
    triggers: list[str],
    risk_level: str,
    exposure_usd: float = 0.0,
    gnn_confidence: float = 0.0,
) -> dict[str, Any]:
    """
    Create a new PENDING governance checkpoint for an incident.
    Returns the checkpoint record.
    """
    checkpoint_id = f"chk_{uuid4().hex[:12]}"
    now = _now()
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=CHECKPOINT_TTL_HOURS)).isoformat()
    risk_trigger = " | ".join(triggers)

    _client().collection("tenants").document(tenant_id).collection("governance_checkpoints").document(checkpoint_id).set({
        "checkpoint_id": checkpoint_id,
        "incident_id": incident_id,
        "tenant_id": tenant_id,
        "risk_trigger": risk_trigger,
        "risk_level": risk_level,
        "exposure_usd": exposure_usd,
        "gnn_confidence": gnn_confidence,
        "status": "PENDING",
        "verified_by": "",
        "verified_at": "",
        "override_reason": "",
        "created_at": now,
        "expires_at": expires_at,
    })

    add_audit("checkpoint_created", f"{checkpoint_id}:{incident_id}:{risk_level}")
    checkpoint_result = get_checkpoint_for_incident(incident_id, tenant_id) or {
        "checkpoint_id": checkpoint_id,
        "incident_id": incident_id,
        "status": "PENDING",
    }

    # ── Real-time WebSocket push (best-effort) ────────────────────────────
    try:
        import asyncio
        from services.event_bus import push_checkpoint_event
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(push_checkpoint_event(
                tenant_id, checkpoint_id, checkpoint_result
            ))
    except Exception:
        pass  # WebSocket push is non-blocking

    return checkpoint_result


def get_checkpoint_for_incident(incident_id: str, tenant_id: str | None = None) -> dict[str, Any] | None:
    """Return the most recent checkpoint for this incident."""
    db = _client()
    query = db.collection("tenants").document(tenant_id).collection("governance_checkpoints") if tenant_id else db.collection_group("governance_checkpoints")
    rows = list(
        query
        .where(filter=FieldFilter("incident_id", "==", incident_id))
        .order_by("created_at", direction=g_firestore.Query.DESCENDING)
        .limit(1)
        .stream()
    )
    if not rows:
        return None
    return rows[0].to_dict() or {}


def list_pending_checkpoints(tenant_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Return all PENDING (non-expired) checkpoints for a tenant."""
    now = _now()
    # Query only by status to avoid a required composite index on (status, expires_at).
    # We apply expiry filtering and created_at sorting in Python.
    rows = (
        _client()
        .collection("tenants")
        .document(tenant_id)
        .collection("governance_checkpoints")
        .where(filter=FieldFilter("status", "==", "PENDING"))
        .stream()
    )
    docs = []
    for doc in rows:
        payload = doc.to_dict() or {}
        if str(payload.get("expires_at") or "") > now:
            docs.append(payload)
    docs.sort(key=lambda d: d.get("created_at", ""), reverse=True)
    return docs[:limit]


def verify_checkpoint(checkpoint_id: str, verified_by: str, tenant_id: str) -> dict[str, Any] | None:
    """Mark a checkpoint as VERIFIED (operator has signed off)."""
    now = _now()
    ref = _client().collection("tenants").document(tenant_id).collection("governance_checkpoints").document(checkpoint_id)
    snap = ref.get()
    if not snap.exists or (snap.to_dict() or {}).get("status") != "PENDING":
        return None
    ref.set({"status": "VERIFIED", "verified_by": verified_by, "verified_at": now}, merge=True)

    add_audit("checkpoint_verified", f"{checkpoint_id}:by={verified_by}")
    return ref.get().to_dict() or None


def override_checkpoint(checkpoint_id: str, override_by: str, reason: str, tenant_id: str) -> dict[str, Any] | None:
    """Override a checkpoint without meeting verification (operator accepts risk)."""
    now = _now()
    ref = _client().collection("tenants").document(tenant_id).collection("governance_checkpoints").document(checkpoint_id)
    if not ref.get().exists:
        return None
    ref.set({"status": "OVERRIDDEN", "verified_by": override_by, "verified_at": now, "override_reason": reason}, merge=True)

    add_audit("checkpoint_overridden", f"{checkpoint_id}:by={override_by}:reason={reason[:80]}")
    return ref.get().to_dict() or None


def _row_to_checkpoint(row: tuple) -> dict[str, Any]:
    return {
        "checkpoint_id": row[0],
        "incident_id": row[1],
        "tenant_id": row[2],
        "risk_trigger": row[3],
        "risk_level": row[4],
        "exposure_usd": row[5],
        "gnn_confidence": row[6],
        "status": row[7],
        "verified_by": row[8] or "",
        "verified_at": row[9] or "",
        "override_reason": row[10] or "",
        "created_at": row[11],
        "expires_at": row[12],
    }


# ── Feedback loop ─────────────────────────────────────────────────────────────

def submit_feedback(
    incident_id: str,
    tenant_id: str,
    submitted_by: str,
    verdict: FeedbackVerdict,
    notes: str = "",
    affected_stage: str = "",
) -> dict[str, Any]:
    """
    Submit operator feedback on a resolved/dismissed incident.
    Verdict drives the feedback governance table and is used to calibrate
    alert thresholds in the next pipeline run.
    """
    feedback_id = f"fb_{uuid4().hex[:12]}"
    now = _now()

    _client().collection("tenants").document(tenant_id).collection("governance_feedback").document(feedback_id).set({
        "feedback_id": feedback_id,
        "incident_id": incident_id,
        "tenant_id": tenant_id,
        "verdict": verdict,
        "submitted_by": submitted_by,
        "notes": notes,
        "affected_stage": affected_stage,
        "created_at": now,
    })

    add_audit("governance_feedback", f"{feedback_id}:{incident_id}:{verdict}:by={submitted_by}")
    return {
        "feedback_id": feedback_id,
        "incident_id": incident_id,
        "verdict": verdict,
        "submitted_by": submitted_by,
        "notes": notes,
        "affected_stage": affected_stage,
        "created_at": now,
    }


def list_feedback(tenant_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """Return feedback records for a tenant, newest first."""
    rows = _client().collection("tenants").document(tenant_id).collection("governance_feedback").order_by("created_at", direction=g_firestore.Query.DESCENDING).limit(limit).stream()
    return [doc.to_dict() or {} for doc in rows]


def feedback_for_incident(incident_id: str) -> list[dict[str, Any]]:
    """Return all feedback records for a specific incident."""
    rows = (
        _client()
        .collection_group("governance_feedback")
        .where(filter=FieldFilter("incident_id", "==", incident_id))
        .order_by("created_at", direction=g_firestore.Query.DESCENDING)
        .stream()
    )
    return [doc.to_dict() or {} for doc in rows]


def governance_summary(tenant_id: str) -> dict[str, Any]:
    """
    Compute aggregate governance metrics for the tenant.
    Used by the post-action verification dashboard.
    """
    feedbacks = list_feedback(tenant_id, limit=500)
    checkpoints = list_pending_checkpoints(tenant_id, limit=500)

    total_fb = len(feedbacks)
    tp = sum(1 for f in feedbacks if f["verdict"] == "TRUE_POSITIVE")
    fp = sum(1 for f in feedbacks if f["verdict"] == "FALSE_POSITIVE")
    fn = sum(1 for f in feedbacks if f["verdict"] == "FALSE_NEGATIVE")
    unc = sum(1 for f in feedbacks if f["verdict"] == "UNCERTAIN")

    # If no manual feedback exists, derive baseline metrics dynamically from actual incident statuses
    # This prevents the UI from showing hardcoded 0% while still tracking real operational data.
    if total_fb == 0:
        from services.firestore_store import list_incidents
        # Only evaluate non-simulation incidents for governance baselines
        incidents = [inc for inc in list_incidents(tenant_id=tenant_id, limit=1000) if inc.get("severity") != "SIMULATION"]
        tp = sum(1 for inc in incidents if inc.get("status") in ("RESOLVED", "APPROVED"))
        fp = sum(1 for inc in incidents if inc.get("status") == "DISMISSED")
        fn = 0  # False negatives cannot be reliably inferred without operator feedback
        unc = sum(1 for inc in incidents if inc.get("status") in ("DETECTED", "PENDING_APPROVAL", "AWAITING_APPROVAL"))
        total_fb = tp + fp + fn + unc

    precision = tp / max(1, tp + fp)
    recall    = tp / max(1, tp + fn)
    f1        = 2 * precision * recall / max(1e-9, precision + recall)

    # Stage breakdown for false positives
    fp_by_stage: dict[str, int] = {}
    for f in feedbacks:
        if f["verdict"] == "FALSE_POSITIVE" and f["affected_stage"]:
            fp_by_stage[f["affected_stage"]] = fp_by_stage.get(f["affected_stage"], 0) + 1

    return {
        "total_feedback": total_fb,
        "verdicts": {"TRUE_POSITIVE": tp, "FALSE_POSITIVE": fp, "FALSE_NEGATIVE": fn, "UNCERTAIN": unc},
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1_score": round(f1, 3),
        "false_positive_by_stage": fp_by_stage,
        "pending_checkpoints": len(checkpoints),
    }
