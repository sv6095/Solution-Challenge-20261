from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from services.data_quality_guard import assess_context_quality
from services.data_registry import data_registry_health_report
from services.firestore_store import list_master_data_changes, list_signals


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _onboarding_completeness_gaps(context: dict[str, Any]) -> list[str]:
    gaps: list[str] = []
    suppliers = context.get("suppliers") if isinstance(context.get("suppliers"), list) else []
    network = context.get("supply_chain_network") if isinstance(context.get("supply_chain_network"), dict) else {}
    nodes = network.get("nodes") if isinstance(network.get("nodes"), list) else []
    routes = network.get("routes") if isinstance(network.get("routes"), list) else []
    contacts_ok = bool(context.get("primary_contact_email") or context.get("primary_contact_name"))
    if len(suppliers) == 0:
        gaps.append("suppliers")
    if len(nodes) == 0:
        gaps.append("network_nodes")
    if len(routes) == 0:
        gaps.append("network_routes")
    if not contacts_ok:
        gaps.append("operator_contacts")
    has_tiered = any(
        str(s.get("tier") or "").strip().lower() in {"tier 1", "tier 2", "tier 3", "1", "2", "3"}
        for s in suppliers
        if isinstance(s, dict)
    )
    if not has_tiered:
        gaps.append("tier_mapping")
    has_incoterm = any(bool(str(r.get("incoterm") or "").strip()) for r in routes if isinstance(r, dict))
    if not has_incoterm:
        gaps.append("incoterm_mapping")
    return gaps


def _to_signal(row: dict[str, Any]) -> dict[str, Any] | None:
    payload = row.get("payload_json")
    if not isinstance(payload, str) or not payload.strip():
        return None
    try:
        parsed = json.loads(payload)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return None
    return None


def _signal_age_hours(signal: dict[str, Any]) -> float | None:
    timestamp = signal.get("detected_at") or signal.get("timestamp") or signal.get("created_at")
    if not timestamp:
        return None
    try:
        ts = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0
    except Exception:
        return None


def _signal_corroboration(signal: dict[str, Any]) -> int:
    raw = signal.get("corroboration_count")
    if isinstance(raw, (int, float)):
        return int(raw)
    corroborated_by = signal.get("corroborated_by")
    if isinstance(corroborated_by, list):
        return len([x for x in corroborated_by if x])
    return 0


def _normalize_source_name(signal: dict[str, Any]) -> str:
    return str(signal.get("source") or "").strip().lower()


def build_intelligence_gap_report(user_id: str, context: dict[str, Any]) -> dict[str, Any]:
    if os.getenv("INTELLIGENCE_GAP_TRACKER_ENABLED", "true").strip().lower() == "false":
        return {
            "user_id": user_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "overall_status": "disabled",
            "blocking": False,
            "gap_count": 0,
            "gaps": [],
            "summary": {"message": "Intelligence gap tracker disabled by environment."},
        }

    now = datetime.now(timezone.utc).isoformat()
    gaps: list[dict[str, Any]] = []
    context_quality_min = _env_float("INTELLIGENCE_GAP_CONTEXT_QUALITY_MIN", 75.0)
    signal_stale_hours = _env_float("INTELLIGENCE_GAP_SIGNAL_STALE_HOURS", 24.0)
    signal_stale_ratio_threshold = _env_float("INTELLIGENCE_GAP_SIGNAL_STALE_RATIO_THRESHOLD", 0.4)
    signal_low_corr_ratio_threshold = _env_float("INTELLIGENCE_GAP_SIGNAL_LOW_CORR_RATIO_THRESHOLD", 0.5)
    master_data_pending_threshold = _env_int("INTELLIGENCE_GAP_MASTER_DATA_PENDING_THRESHOLD", 20)
    registry_stale_hours = _env_float("INTELLIGENCE_GAP_REGISTRY_STALE_HOURS", 24.0 * 30.0)

    onboarding_gaps = _onboarding_completeness_gaps(context)
    if onboarding_gaps:
        gaps.append(
            {
                "id": "onboarding-completeness",
                "category": "completeness",
                "severity": "critical",
                "blocking": True,
                "status": "open",
                "evidence": {"missing": onboarding_gaps},
                "recommended_fix": "Complete onboarding fields for suppliers, network graph, contacts, tier mapping, and incoterms.",
            }
        )

    context_quality = assess_context_quality(context)
    quality_score = float(context_quality.get("score") or 0.0)
    if quality_score < context_quality_min:
        gaps.append(
            {
                "id": "context-quality",
                "category": "completeness",
                "severity": "high",
                "blocking": True,
                "status": "open",
                "evidence": context_quality,
                "recommended_fix": "Improve supplier identifiers, tier labels, coordinates, and route incoterm coverage.",
            }
        )

    health = data_registry_health_report()
    freshness = health.get("freshness") if isinstance(health.get("freshness"), dict) else {}
    stale_sources: list[dict[str, Any]] = []
    for source, info in freshness.items():
        if not isinstance(info, dict):
            continue
        age_hours = info.get("age_hours")
        exists = bool(info.get("exists"))
        if not exists:
            stale_sources.append({"source": source, "reason": "missing"})
            continue
        if isinstance(age_hours, (int, float)) and age_hours > registry_stale_hours:
            stale_sources.append({"source": source, "reason": "stale", "age_hours": round(float(age_hours), 2)})
    if stale_sources:
        gaps.append(
            {
                "id": "registry-freshness",
                "category": "freshness",
                "severity": "medium",
                "blocking": False,
                "status": "open",
                "evidence": {"stale_or_missing_sources": stale_sources},
                "recommended_fix": "Refresh local registry datasets and rerun ingestion bootstrap.",
            }
        )

    signal_rows = list_signals(limit=250)
    signals = [s for s in (_to_signal(r) for r in signal_rows) if s]
    if not signals:
        gaps.append(
            {
                "id": "signal-coverage",
                "category": "coverage",
                "severity": "high",
                "blocking": False,
                "status": "open",
                "evidence": {"active_signals": 0},
                "recommended_fix": "Run signal refresh to populate active intelligence signals.",
            }
        )
    else:
        stale_count = 0
        low_corroboration_count = 0
        active_sources = {_normalize_source_name(signal) for signal in signals if _normalize_source_name(signal)}
        for signal in signals:
            age = _signal_age_hours(signal)
            if isinstance(age, (int, float)) and age > signal_stale_hours:
                stale_count += 1
            if _signal_corroboration(signal) < 2:
                low_corroboration_count += 1
        expected_sources = {
            "acled": "ACLED political disruption coverage",
            "imf_portwatch": "IMF PortWatch chokepoint transit coverage",
            "imf_portwatch_disruptions": "IMF PortWatch disruption coverage",
            "cii_model": "Country instability scoring coverage",
            "wingbits_gps": "GPS interference coverage",
            "wto": "WTO tariff and trade policy coverage",
        }
        missing_expected = [
            {"source": source, "label": label}
            for source, label in expected_sources.items()
            if source not in active_sources
        ]
        stale_ratio = stale_count / max(1, len(signals))
        low_corr_ratio = low_corroboration_count / max(1, len(signals))
        if missing_expected:
            gaps.append(
                {
                    "id": "source-coverage",
                    "category": "coverage",
                    "severity": "high",
                    "blocking": False,
                    "status": "open",
                    "evidence": {"missing_sources": missing_expected},
                    "recommended_fix": "Enable the missing intelligence adapters or provide their API credentials before relying on automated decisions.",
                }
            )
        if stale_ratio > signal_stale_ratio_threshold:
            gaps.append(
                {
                    "id": "signal-freshness",
                    "category": "freshness",
                    "severity": "high",
                    "blocking": False,
                    "status": "open",
                    "evidence": {
                        "stale_signal_count": stale_count,
                        "total_signals": len(signals),
                        "stale_ratio": round(stale_ratio, 3),
                    },
                    "recommended_fix": "Increase poll cadence or trigger immediate refresh to reduce stale active signals.",
                }
            )
        if low_corr_ratio > signal_low_corr_ratio_threshold:
            gaps.append(
                {
                    "id": "signal-corroboration",
                    "category": "completeness",
                    "severity": "medium",
                    "blocking": False,
                    "status": "open",
                    "evidence": {
                        "low_corroboration_count": low_corroboration_count,
                        "total_signals": len(signals),
                        "low_corroboration_ratio": round(low_corr_ratio, 3),
                    },
                    "recommended_fix": "Add/align corroborating sources before automated decisions for weakly corroborated signals.",
                }
            )

    pending_changes = list_master_data_changes(user_id, limit=200)
    recent_changes = len(pending_changes)
    if recent_changes >= master_data_pending_threshold:
        gaps.append(
            {
                "id": "master-data-drift",
                "category": "drift",
                "severity": "medium",
                "blocking": False,
                "status": "open",
                "evidence": {"pending_changes": recent_changes},
                "recommended_fix": "Run master-data propagation and verify downstream routing/assessment sync.",
            }
        )

    severity_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    top_severity = max((severity_rank.get(str(g.get("severity", "low")).lower(), 1) for g in gaps), default=0)
    overall_status = "healthy" if not gaps else ("critical" if top_severity >= 4 else "degraded")

    return {
        "user_id": user_id,
        "generated_at": now,
        "overall_status": overall_status,
        "blocking": any(bool(g.get("blocking")) for g in gaps),
        "gap_count": len(gaps),
        "gaps": gaps,
        "summary": {
            "onboarding_missing_count": len(onboarding_gaps),
            "context_quality_score": quality_score,
            "active_signals": len(signals),
            "master_data_pending_changes": recent_changes,
        },
    }
