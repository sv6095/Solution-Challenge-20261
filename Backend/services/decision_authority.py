from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Any


Stage = Literal["DETECT", "ASSESS", "DECIDE", "ACT", "AUDIT"]


@dataclass(frozen=True)
class DecisionAuthorityRule:
    stage: Stage
    min_role: str
    max_var_usd_without_legal: float
    max_var_usd_without_finance: float
    requires_checklist: bool = True


RULES: dict[Stage, DecisionAuthorityRule] = {
    "DETECT": DecisionAuthorityRule("DETECT", "viewer", 999_999_999, 999_999_999, False),
    "ASSESS": DecisionAuthorityRule("ASSESS", "analyst", 999_999_999, 999_999_999, False),
    "DECIDE": DecisionAuthorityRule("DECIDE", "analyst", 750_000, 1_500_000, True),
    "ACT": DecisionAuthorityRule("ACT", "admin", 500_000, 1_000_000, True),
    "AUDIT": DecisionAuthorityRule("AUDIT", "analyst", 999_999_999, 999_999_999, False),
}


ROLE_ORDER = {
    "viewer": 1,
    "analyst": 2,
    "admin": 3,
    "superadmin": 4,
    "service": 3,
}


def _role_ok(actual_role: str, min_role: str) -> bool:
    return ROLE_ORDER.get(actual_role.lower(), 0) >= ROLE_ORDER.get(min_role.lower(), 99)


def action_readiness_checklist(incident: dict[str, Any]) -> dict[str, Any]:
    import os
    is_dev = os.getenv("DEV_MODE", "true").lower() == "true"
    
    route_options = incident.get("route_options") if isinstance(incident.get("route_options"), list) else []
    backup_supplier = incident.get("backup_supplier") if isinstance(incident.get("backup_supplier"), dict) else {}
    recommendation = str(incident.get("recommendation") or "")
    checks = {
        "has_recommendation": bool(recommendation),
        "has_route_options": len(route_options) > 0,
        "backup_supplier_contactable": bool(str(backup_supplier.get("email") or "").strip()) if not is_dev else True,
        "contract_ready": bool(incident.get("tenant_policy_plane") or incident.get("value_at_risk_context")) if not is_dev else True,
        "compliance_ready": bool(incident.get("source_url") or incident.get("source")) if not is_dev else True,
    }
    return {
        "checks": checks,
        "ready": all(checks.values()),
        "missing": [k for k, v in checks.items() if not v],
    }


def evaluate_stage_authority(
    stage: Stage,
    user_role: str,
    incident: dict[str, Any],
) -> dict[str, Any]:
    rule = RULES[stage]
    var_usd = float(incident.get("value_at_risk_usd") or 0.0)
    needs_legal = var_usd > rule.max_var_usd_without_legal
    needs_finance = var_usd > rule.max_var_usd_without_finance
    checklist = action_readiness_checklist(incident) if rule.requires_checklist else {"ready": True, "missing": [], "checks": {}}
    allowed = _role_ok(user_role, rule.min_role) and checklist["ready"]
    return {
        "stage": stage,
        "allowed": allowed,
        "required_min_role": rule.min_role,
        "needs_legal_signoff": needs_legal,
        "needs_finance_signoff": needs_finance,
        "readiness": checklist,
        "var_usd": var_usd,
    }
