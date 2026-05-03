from __future__ import annotations

import math
from typing import Any


def _create_rng(seed: int):
    value = seed % 2147483647
    if value <= 0:
        value += 2147483646

    def _next() -> float:
        nonlocal value
        value = (value * 16807) % 2147483647
        return (value - 1) / 2147483646

    return _next


def _triangular(rng, low: float, mode: float, high: float) -> float:
    u = rng()
    c = (mode - low) / (high - low) if high > low else 0.5
    if u < c:
        return low + math.sqrt(u * (high - low) * (mode - low))
    return high - math.sqrt((1 - u) * (high - low) * (high - mode))


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * pct)))
    return float(ordered[idx])


def simulate_incident_monte_carlo(
    incident: dict[str, Any],
    event: dict[str, Any],
    runs: int = 300,
) -> dict[str, Any]:
    runs = max(50, min(int(runs), 1000))
    event_id = str(event.get("id") or event.get("signal_id") or incident.get("id") or "0")
    seed = sum(ord(ch) for ch in event_id)
    rng = _create_rng(seed)

    recommended_route = next(
        (route for route in incident.get("route_options", []) if route.get("recommended")),
        (incident.get("route_options") or [{}])[0],
    )

    route_mode = str(recommended_route.get("mode") or "land").lower()
    route_risk = float(recommended_route.get("risk_score") or 0.25)
    base_transit_days = float(
        recommended_route.get("transit_days")
        or (float(recommended_route.get("duration_hours") or 0.0) / 24.0)
        or 3.0
    )
    base_disruption_days = float(event.get("duration_days") or max(3.0, float(event.get("severity_raw") or event.get("severity") or 5.0) * 1.15))
    stockout_days = max(1.0, float(incident.get("min_stockout_days") or 4.0))
    exposure_usd = max(1.0, float(incident.get("total_exposure_usd") or 1.0))
    gnn_confidence = max(0.1, min(0.99, float(incident.get("gnn_confidence") or 0.5)))
    node_count = max(1, int(incident.get("affected_node_count") or len(incident.get("affected_nodes") or [])))

    mode_variance = {"air": 0.35, "sea": 1.25, "land": 0.65}.get(route_mode, 0.75)
    protected = 0
    reliable = 0
    arrival_days_list: list[float] = []
    disruption_days_list: list[float] = []
    exposure_avoided_list: list[float] = []
    loss_list: list[float] = []
    sample_outcomes: list[dict[str, Any]] = []

    for run in range(runs):
        disruption_days = _triangular(
            rng,
            max(1.0, base_disruption_days * 0.6),
            max(1.2, base_disruption_days),
            max(1.5, base_disruption_days * (1.5 + node_count * 0.03)),
        )
        route_days = _triangular(
            rng,
            max(0.4, base_transit_days * 0.8),
            max(0.5, base_transit_days * (1.0 + route_risk * 0.4)),
            max(0.8, base_transit_days * (1.35 + mode_variance)),
        )
        customs_days = _triangular(
            rng,
            0.05,
            0.25 + (route_risk * 0.8),
            1.2 + (mode_variance * 1.6),
        )
        arrival_days = route_days + customs_days
        continuity_gap_days = max(0.0, arrival_days - stockout_days)
        protected_run = continuity_gap_days <= 0
        route_still_viable = arrival_days <= disruption_days + max(0.5, stockout_days * 0.2)

        continuity_factor = max(0.0, 1.0 - (continuity_gap_days / max(stockout_days, 1.0)))
        avoided_exposure = exposure_usd * min(
            1.0,
            max(0.1, continuity_factor * (0.55 + gnn_confidence * 0.35)),
        )
        loss = exposure_usd * min(
            1.0,
            max(0.05, (continuity_gap_days / max(stockout_days, 1.0)) * (0.7 + route_risk)),
        )

        if protected_run:
            protected += 1
        if route_still_viable:
            reliable += 1

        arrival_days_list.append(arrival_days)
        disruption_days_list.append(disruption_days)
        exposure_avoided_list.append(avoided_exposure)
        loss_list.append(loss)

        if run < 18:
            sample_outcomes.append(
                {
                    "run": run + 1,
                    "arrival_days": round(arrival_days, 2),
                    "disruption_days": round(disruption_days, 2),
                    "continuity_gap_days": round(continuity_gap_days, 2),
                    "protected": protected_run,
                    "loss_usd": round(loss, 2),
                }
            )

    return {
        "runs": runs,
        "seed": seed,
        "route_mode": route_mode,
        "protected_rate": round(protected / runs, 4),
        "route_reliability": round(reliable / runs, 4),
        "average_delay_days": round(sum(max(0.0, x - stockout_days) for x in arrival_days_list) / runs, 4),
        "expected_exposure_avoided_usd": round(sum(exposure_avoided_list) / runs, 2),
        "worst_case_loss_usd": round(max(loss_list), 2),
        "arrival_days_p10": round(_percentile(arrival_days_list, 0.10), 2),
        "arrival_days_p50": round(_percentile(arrival_days_list, 0.50), 2),
        "arrival_days_p90": round(_percentile(arrival_days_list, 0.90), 2),
        "disruption_days_p10": round(_percentile(disruption_days_list, 0.10), 2),
        "disruption_days_p50": round(_percentile(disruption_days_list, 0.50), 2),
        "disruption_days_p90": round(_percentile(disruption_days_list, 0.90), 2),
        "sample_outcomes": sample_outcomes,
    }
