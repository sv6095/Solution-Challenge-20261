from __future__ import annotations

from typing import Any


def assess_context_quality(context: dict[str, Any]) -> dict[str, Any]:
    suppliers = context.get("suppliers") if isinstance(context.get("suppliers"), list) else []
    network = context.get("supply_chain_network") if isinstance(context.get("supply_chain_network"), dict) else {}
    routes = network.get("routes") if isinstance(network.get("routes"), list) else []

    total = max(1, len(suppliers))
    missing_tier = 0
    missing_coords = 0
    missing_identifier = 0
    for supplier in suppliers:
        if not isinstance(supplier, dict):
            missing_identifier += 1
            continue
        if not str(supplier.get("id") or supplier.get("supplier_id") or "").strip():
            missing_identifier += 1
        tier = str(supplier.get("tier") or "").strip().lower()
        if tier not in {"1", "2", "3", "tier 1", "tier 2", "tier 3", "t1", "t2", "t3"}:
            missing_tier += 1
        if not isinstance(supplier.get("lat"), (int, float)) or not isinstance(supplier.get("lng"), (int, float)):
            missing_coords += 1

    routes_with_incoterm = sum(1 for r in routes if isinstance(r, dict) and str(r.get("incoterm") or "").strip())
    route_incoterm_ratio = routes_with_incoterm / max(1, len(routes))

    score = 100.0
    score -= (missing_identifier / total) * 35.0
    score -= (missing_tier / total) * 25.0
    score -= (missing_coords / total) * 20.0
    score -= max(0.0, (0.7 - route_incoterm_ratio) * 20.0)
    score = max(0.0, round(score, 2))

    return {
        "score": score,
        "ready_for_automation": score >= 75.0,
        "metrics": {
            "supplier_count": len(suppliers),
            "missing_identifier": missing_identifier,
            "missing_tier": missing_tier,
            "missing_coords": missing_coords,
            "route_count": len(routes),
            "route_incoterm_ratio": round(route_incoterm_ratio, 3),
        },
    }
