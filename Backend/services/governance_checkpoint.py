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

Tables (appended to the single SQLite DB via idempotent migration):

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

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from services.local_store import DB_PATH, add_audit


# ── Schema migration (idempotent) ─────────────────────────────────────────────

def _ensure_schema() -> None:
    with sqlite3.connect(DB_PATH) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("""
            CREATE TABLE IF NOT EXISTS governance_checkpoints (
                checkpoint_id  TEXT PRIMARY KEY,
                incident_id    TEXT NOT NULL,
                tenant_id      TEXT NOT NULL,
                risk_trigger   TEXT NOT NULL,
                risk_level     TEXT NOT NULL,
                exposure_usd   REAL,
                gnn_confidence REAL,
                status         TEXT NOT NULL DEFAULT 'PENDING',
                verified_by    TEXT,
                verified_at    TEXT,
                override_reason TEXT,
                created_at     TEXT NOT NULL,
                expires_at     TEXT NOT NULL
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_chkpt_incident ON governance_checkpoints(incident_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_chkpt_tenant   ON governance_checkpoints(tenant_id, status)")
        con.execute("""
            CREATE TABLE IF NOT EXISTS governance_feedback (
                feedback_id    TEXT PRIMARY KEY,
                incident_id    TEXT NOT NULL,
                tenant_id      TEXT NOT NULL,
                verdict        TEXT NOT NULL,
                submitted_by   TEXT NOT NULL,
                notes          TEXT,
                affected_stage TEXT,
                created_at     TEXT NOT NULL
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_fb_incident ON governance_feedback(incident_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_fb_tenant   ON governance_feedback(tenant_id, created_at)")


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


def _conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


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

    with _conn() as con:
        con.execute(
            """
            INSERT OR IGNORE INTO governance_checkpoints
                (checkpoint_id, incident_id, tenant_id, risk_trigger, risk_level,
                 exposure_usd, gnn_confidence, status, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)
            """,
            (checkpoint_id, incident_id, tenant_id, risk_trigger, risk_level,
             exposure_usd, gnn_confidence, now, expires_at),
        )

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
    with _conn() as con:
        if tenant_id:
            row = con.execute(
                "SELECT checkpoint_id, incident_id, tenant_id, risk_trigger, risk_level, "
                "exposure_usd, gnn_confidence, status, verified_by, verified_at, override_reason, "
                "created_at, expires_at FROM governance_checkpoints "
                "WHERE incident_id = ? AND tenant_id = ? ORDER BY created_at DESC LIMIT 1",
                (incident_id, tenant_id),
            ).fetchone()
        else:
            row = con.execute(
                "SELECT checkpoint_id, incident_id, tenant_id, risk_trigger, risk_level, "
                "exposure_usd, gnn_confidence, status, verified_by, verified_at, override_reason, "
                "created_at, expires_at FROM governance_checkpoints "
                "WHERE incident_id = ? ORDER BY created_at DESC LIMIT 1",
                (incident_id,),
            ).fetchone()
    if not row:
        return None
    return _row_to_checkpoint(row)


def list_pending_checkpoints(tenant_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Return all PENDING (non-expired) checkpoints for a tenant."""
    now = _now()
    with _conn() as con:
        rows = con.execute(
            "SELECT checkpoint_id, incident_id, tenant_id, risk_trigger, risk_level, "
            "exposure_usd, gnn_confidence, status, verified_by, verified_at, override_reason, "
            "created_at, expires_at FROM governance_checkpoints "
            "WHERE tenant_id = ? AND status = 'PENDING' AND expires_at > ? "
            "ORDER BY created_at DESC LIMIT ?",
            (tenant_id, now, limit),
        ).fetchall()
    return [_row_to_checkpoint(r) for r in rows]


def verify_checkpoint(checkpoint_id: str, verified_by: str, tenant_id: str) -> dict[str, Any] | None:
    """Mark a checkpoint as VERIFIED (operator has signed off)."""
    now = _now()
    with _conn() as con:
        cur = con.execute(
            "UPDATE governance_checkpoints SET status='VERIFIED', verified_by=?, verified_at=? "
            "WHERE checkpoint_id=? AND tenant_id=? AND status='PENDING'",
            (verified_by, now, checkpoint_id, tenant_id),
        )
        if not cur.rowcount:
            return None

    add_audit("checkpoint_verified", f"{checkpoint_id}:by={verified_by}")
    with _conn() as con:
        row = con.execute(
            "SELECT checkpoint_id, incident_id, tenant_id, risk_trigger, risk_level, "
            "exposure_usd, gnn_confidence, status, verified_by, verified_at, override_reason, "
            "created_at, expires_at FROM governance_checkpoints WHERE checkpoint_id = ?",
            (checkpoint_id,),
        ).fetchone()
    return _row_to_checkpoint(row) if row else None


def override_checkpoint(checkpoint_id: str, override_by: str, reason: str, tenant_id: str) -> dict[str, Any] | None:
    """Override a checkpoint without meeting verification (operator accepts risk)."""
    now = _now()
    with _conn() as con:
        cur = con.execute(
            "UPDATE governance_checkpoints SET status='OVERRIDDEN', verified_by=?, verified_at=?, "
            "override_reason=? WHERE checkpoint_id=? AND tenant_id=?",
            (override_by, now, reason, checkpoint_id, tenant_id),
        )
        if not cur.rowcount:
            return None

    add_audit("checkpoint_overridden", f"{checkpoint_id}:by={override_by}:reason={reason[:80]}")
    with _conn() as con:
        row = con.execute(
            "SELECT checkpoint_id, incident_id, tenant_id, risk_trigger, risk_level, "
            "exposure_usd, gnn_confidence, status, verified_by, verified_at, override_reason, "
            "created_at, expires_at FROM governance_checkpoints WHERE checkpoint_id = ?",
            (checkpoint_id,),
        ).fetchone()
    return _row_to_checkpoint(row) if row else None


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

    with _conn() as con:
        con.execute(
            """
            INSERT INTO governance_feedback
                (feedback_id, incident_id, tenant_id, verdict, submitted_by, notes, affected_stage, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (feedback_id, incident_id, tenant_id, verdict, submitted_by, notes, affected_stage, now),
        )

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
    with _conn() as con:
        rows = con.execute(
            "SELECT feedback_id, incident_id, tenant_id, verdict, submitted_by, notes, affected_stage, created_at "
            "FROM governance_feedback WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ?",
            (tenant_id, limit),
        ).fetchall()
    return [
        {
            "feedback_id": r[0], "incident_id": r[1], "tenant_id": r[2],
            "verdict": r[3], "submitted_by": r[4], "notes": r[5] or "",
            "affected_stage": r[6] or "", "created_at": r[7],
        }
        for r in rows
    ]


def feedback_for_incident(incident_id: str) -> list[dict[str, Any]]:
    """Return all feedback records for a specific incident."""
    with _conn() as con:
        rows = con.execute(
            "SELECT feedback_id, incident_id, tenant_id, verdict, submitted_by, notes, affected_stage, created_at "
            "FROM governance_feedback WHERE incident_id = ? ORDER BY created_at DESC",
            (incident_id,),
        ).fetchall()
    return [
        {
            "feedback_id": r[0], "incident_id": r[1], "tenant_id": r[2],
            "verdict": r[3], "submitted_by": r[4], "notes": r[5] or "",
            "affected_stage": r[6] or "", "created_at": r[7],
        }
        for r in rows
    ]


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
        from services.local_store import list_incidents
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
