"""
threshold_tuner.py — Automated Alert Threshold Calibration
==========================================================
Closes SCRM Pillar 12 gap: consumes governance_feedback to compute
precision/recall/F1 per pipeline stage, then adjusts alert thresholds
to minimize false positives while preserving recall.

Algorithm:
  1. Pull all feedback records (TRUE_POSITIVE, FALSE_POSITIVE, FALSE_NEGATIVE)
  2. Group by affected_stage (gnn_propagation, financial_assessment, etc.)
  3. Compute per-stage precision, recall, F1
  4. If F1 is below target AND we have enough samples:
     - High false-positive rate → raise threshold (fewer but higher-confidence alerts)
     - High false-negative rate → lower threshold (more alerts, higher recall)
  5. Write updated thresholds to tenant config
  6. Log all changes to audit trail

Schedule: runs weekly via the worldmonitor cron or on-demand via API.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore as g_firestore

from services.firestore_store import _client, add_audit
from services.governance_checkpoint import list_feedback


# ── Configuration ─────────────────────────────────────────────────────────────

# Minimum feedback samples per stage before we adjust thresholds
MIN_SAMPLES_FOR_TUNING = int(os.getenv("THRESHOLD_TUNING_MIN_SAMPLES", "10"))

# Target F1 score — thresholds are only adjusted when F1 is below this
TARGET_F1 = float(os.getenv("THRESHOLD_TUNING_TARGET_F1", "0.80"))

# Maximum threshold adjustment per tuning cycle (prevents oscillation)
MAX_ADJUSTMENT_STEP = float(os.getenv("THRESHOLD_TUNING_MAX_STEP", "0.05"))

# Default thresholds per stage (used if no tenant-specific override exists)
DEFAULT_THRESHOLDS: dict[str, dict[str, float]] = {
    "gnn_propagation": {
        "affected_score_threshold": 0.30,   # min risk score to flag a node
        "confidence_floor": 0.65,           # min GNN confidence to act
    },
    "financial_assessment": {
        "exposure_threshold_usd": 500_000,  # governance gate trigger
        "stockout_threshold_days": 3.0,     # critical stockout window
    },
    "signal_detection": {
        "severity_floor": 4.0,              # min severity to process
        "corroboration_minimum": 2,         # min cross-source corroborations
    },
    "route_generation": {
        "cost_deviation_max": 0.50,         # max cost increase vs baseline
    },
}


@dataclass
class StageMetrics:
    """Precision/recall/F1 metrics for a specific pipeline stage."""
    stage: str
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    uncertain: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    total_samples: int = 0
    recommendation: str = ""  # "raise" | "lower" | "stable"

    def compute(self) -> None:
        self.total_samples = self.true_positives + self.false_positives + self.false_negatives
        if self.total_samples == 0:
            return
        self.precision = self.true_positives / max(1, self.true_positives + self.false_positives)
        self.recall = self.true_positives / max(1, self.true_positives + self.false_negatives)
        denom = self.precision + self.recall
        self.f1 = (2 * self.precision * self.recall / denom) if denom > 0 else 0.0

        if self.f1 >= TARGET_F1:
            self.recommendation = "stable"
        elif self.false_positives > self.false_negatives:
            self.recommendation = "raise"
        else:
            self.recommendation = "lower"

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "uncertain": self.uncertain,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "total_samples": self.total_samples,
            "recommendation": self.recommendation,
        }


# ── Schema migration ─────────────────────────────────────────────────────────

def _ensure_tuning_schema() -> None:
    """Firestore does not require runtime schema creation."""
    _client()

_ensure_tuning_schema()


# ── Threshold read/write ──────────────────────────────────────────────────────

def get_threshold(tenant_id: str, stage: str, param: str) -> float:
    """Get current threshold for a tenant's pipeline stage."""
    doc = _client().collection("tenants").document(tenant_id).collection("thresholds").document(f"{stage}__{param}").get()
    if doc.exists:
        data = doc.to_dict() or {}
        if data.get("value") is not None:
            return float(data["value"])
    # Fall back to defaults
    return DEFAULT_THRESHOLDS.get(stage, {}).get(param, 0.5)


def get_all_thresholds(tenant_id: str) -> dict[str, dict[str, float]]:
    """Get all thresholds for a tenant, merged with defaults."""
    result: dict[str, dict[str, float]] = {}
    for stage, params in DEFAULT_THRESHOLDS.items():
        result[stage] = {}
        for param, default_val in params.items():
            result[stage][param] = get_threshold(tenant_id, stage, param)
    return result


def _update_threshold(
    tenant_id: str,
    stage: str,
    param: str,
    new_value: float,
    old_value: float,
    f1_before: float,
    reason: str,
) -> None:
    """Write updated threshold and log change."""
    now = datetime.now(timezone.utc).isoformat()
    db = _client()
    db.collection("tenants").document(tenant_id).collection("thresholds").document(f"{stage}__{param}").set({
        "tenant_id": tenant_id,
        "stage": stage,
        "param": param,
        "value": new_value,
        "updated_at": now,
    }, merge=True)
    db.collection("tenants").document(tenant_id).collection("threshold_history").document().set({
        "tenant_id": tenant_id,
        "stage": stage,
        "param": param,
        "old_value": old_value,
        "new_value": new_value,
        "f1_before": f1_before,
        "reason": reason,
        "created_at": now,
    })
    add_audit(
        "threshold_tuned",
        json.dumps({
            "tenant_id": tenant_id,
            "stage": stage,
            "param": param,
            "old": old_value,
            "new": new_value,
            "f1_before": round(f1_before, 4),
            "reason": reason,
        }),
    )


# ── Analysis ──────────────────────────────────────────────────────────────────

def compute_stage_metrics(tenant_id: str) -> dict[str, StageMetrics]:
    """Compute precision/recall/F1 per pipeline stage from feedback data."""
    metrics: dict[str, StageMetrics] = {}

    for row in list_feedback(tenant_id, limit=1000):
        verdict = row.get("verdict")
        stage = row.get("affected_stage") or "unknown"
        if verdict not in {"TRUE_POSITIVE", "FALSE_POSITIVE", "FALSE_NEGATIVE", "UNCERTAIN"}:
            continue
        if stage not in metrics:
            metrics[stage] = StageMetrics(stage=stage)
        m = metrics[stage]
        if verdict == "TRUE_POSITIVE":
            m.true_positives += 1
        elif verdict == "FALSE_POSITIVE":
            m.false_positives += 1
        elif verdict == "FALSE_NEGATIVE":
            m.false_negatives += 1
        elif verdict == "UNCERTAIN":
            m.uncertain += 1

    for m in metrics.values():
        m.compute()

    return metrics


# ── Tuning engine ─────────────────────────────────────────────────────────────

def _compute_adjustment(metrics: StageMetrics, current_threshold: float) -> tuple[float, str]:
    """
    Compute threshold adjustment based on precision/recall balance.
    
    Returns (adjustment_delta, reason_string).
    adjustment_delta > 0 means raise threshold (fewer alerts).
    adjustment_delta < 0 means lower threshold (more alerts).
    """
    if metrics.total_samples < MIN_SAMPLES_FOR_TUNING:
        return 0.0, f"Insufficient samples ({metrics.total_samples}/{MIN_SAMPLES_FOR_TUNING})"

    if metrics.f1 >= TARGET_F1:
        return 0.0, f"F1={metrics.f1:.3f} meets target={TARGET_F1:.3f}"

    # Calculate adjustment magnitude proportional to the F1 gap
    f1_gap = TARGET_F1 - metrics.f1
    raw_step = min(MAX_ADJUSTMENT_STEP, f1_gap * 0.3)  # conservative: 30% of gap per cycle

    if metrics.recommendation == "raise":
        # Too many false positives → raise threshold
        fp_ratio = metrics.false_positives / max(1, metrics.total_samples)
        step = raw_step * min(1.0, fp_ratio * 2)
        reason = (
            f"F1={metrics.f1:.3f} < target={TARGET_F1:.3f}. "
            f"FP ratio={fp_ratio:.2f} ({metrics.false_positives} FPs). "
            f"Raising threshold by {step:.4f} to reduce false positives."
        )
        return step, reason

    elif metrics.recommendation == "lower":
        # Too many false negatives → lower threshold
        fn_ratio = metrics.false_negatives / max(1, metrics.total_samples)
        step = raw_step * min(1.0, fn_ratio * 2)
        reason = (
            f"F1={metrics.f1:.3f} < target={TARGET_F1:.3f}. "
            f"FN ratio={fn_ratio:.2f} ({metrics.false_negatives} FNs). "
            f"Lowering threshold by {step:.4f} to improve recall."
        )
        return -step, reason

    return 0.0, "No adjustment needed"


# Map pipeline stages to their adjustable threshold parameters
STAGE_PARAM_MAP: dict[str, tuple[str, str]] = {
    "gnn_propagation": ("gnn_propagation", "affected_score_threshold"),
    "financial_assessment": ("financial_assessment", "exposure_threshold_usd"),
    "signal_detection": ("signal_detection", "severity_floor"),
    "route_generation": ("route_generation", "cost_deviation_max"),
}

# Scale factors for non-normalized thresholds (exposure_threshold_usd is in dollars)
PARAM_SCALE: dict[str, float] = {
    "affected_score_threshold": 1.0,      # 0-1 range
    "confidence_floor": 1.0,              # 0-1 range
    "exposure_threshold_usd": 100_000.0,  # adjust in $100K increments
    "stockout_threshold_days": 1.0,       # days
    "severity_floor": 1.0,               # 0-10 scale
    "corroboration_minimum": 1.0,         # count
    "cost_deviation_max": 1.0,            # 0-1 range
}


def run_threshold_tuning(tenant_id: str) -> dict[str, Any]:
    """
    Execute a full threshold tuning cycle for a tenant.
    
    Analyzes governance_feedback, computes per-stage F1,
    adjusts thresholds where needed, and returns a report.
    
    Idempotent: safe to call multiple times; adjustments are capped
    at MAX_ADJUSTMENT_STEP per cycle to prevent oscillation.
    """
    stage_metrics = compute_stage_metrics(tenant_id)
    
    adjustments: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for stage_name, (threshold_stage, param_name) in STAGE_PARAM_MAP.items():
        metrics = stage_metrics.get(stage_name)
        if not metrics:
            skipped.append({
                "stage": stage_name,
                "reason": "No feedback data for this stage",
            })
            continue

        current = get_threshold(tenant_id, threshold_stage, param_name)
        scale = PARAM_SCALE.get(param_name, 1.0)
        delta, reason = _compute_adjustment(metrics, current)

        if abs(delta) < 1e-6:
            skipped.append({
                "stage": stage_name,
                "reason": reason,
                "current_value": current,
                "f1": round(metrics.f1, 4),
            })
            continue

        # Apply scaled adjustment
        new_value = current + (delta * scale)

        # Clamp to reasonable bounds
        if param_name == "affected_score_threshold":
            new_value = max(0.10, min(0.70, new_value))
        elif param_name == "exposure_threshold_usd":
            new_value = max(50_000, min(2_000_000, new_value))
        elif param_name == "severity_floor":
            new_value = max(1.0, min(8.0, new_value))
        elif param_name == "cost_deviation_max":
            new_value = max(0.10, min(1.00, new_value))

        _update_threshold(
            tenant_id, threshold_stage, param_name,
            new_value, current, metrics.f1, reason,
        )

        adjustments.append({
            "stage": stage_name,
            "param": param_name,
            "old_value": current,
            "new_value": round(new_value, 4),
            "delta": round(delta * scale, 4),
            "f1_before": round(metrics.f1, 4),
            "reason": reason,
        })

    report = {
        "tenant_id": tenant_id,
        "tuning_timestamp": datetime.now(timezone.utc).isoformat(),
        "target_f1": TARGET_F1,
        "stages_analyzed": {k: v.to_dict() for k, v in stage_metrics.items()},
        "adjustments_applied": adjustments,
        "stages_skipped": skipped,
        "total_adjustments": len(adjustments),
    }

    add_audit("threshold_tuning_run", json.dumps({
        "tenant_id": tenant_id,
        "adjustments": len(adjustments),
        "timestamp": report["tuning_timestamp"],
    }))

    return report


def threshold_tuning_history(tenant_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Return history of threshold changes for a tenant."""
    rows = _client().collection("tenants").document(tenant_id).collection("threshold_history").order_by("created_at", direction=g_firestore.Query.DESCENDING).limit(limit).stream()
    return [doc.to_dict() or {} for doc in rows]
