from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ALLOWED_MODES = {"sea", "air", "land", "rail", "multimodal", "mixed"}
ALLOWED_TIERS = {1, 2, 3}


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]


def parse_tier(value: Any) -> int | None:
    raw = str(value or "").strip().lower()
    if raw in {"1", "tier 1", "t1"}:
        return 1
    if raw in {"2", "tier 2", "t2"}:
        return 2
    if raw in {"3", "tier 3", "t3"}:
        return 3
    return None


def validate_supplier_rows(suppliers: list[dict[str, Any]]) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    seen_ids: set[str] = set()
    for idx, row in enumerate(suppliers):
        sid = str(row.get("id") or row.get("supplier_id") or "").strip()
        if not sid:
            errors.append(f"suppliers[{idx}]: missing supplier id")
            continue
        if sid in seen_ids:
            errors.append(f"suppliers[{idx}]: duplicate supplier id '{sid}'")
        seen_ids.add(sid)
        tier = parse_tier(row.get("tier"))
        if tier not in ALLOWED_TIERS:
            errors.append(f"suppliers[{idx}]: invalid tier '{row.get('tier')}'")
        lat = row.get("lat", row.get("latitude"))
        lng = row.get("lng", row.get("longitude"))
        if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
            errors.append(f"suppliers[{idx}]: invalid coordinates")
        mode = str(row.get("mode") or row.get("transport_mode") or "land").strip().lower()
        if mode not in ALLOWED_MODES:
            errors.append(f"suppliers[{idx}]: invalid transport mode '{mode}'")
        if not row.get("country"):
            warnings.append(f"suppliers[{idx}]: missing country")
    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)


def validate_network_graph(nodes: list[dict[str, Any]], routes: list[dict[str, Any]]) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    node_ids: set[str] = set()
    for idx, node in enumerate(nodes):
        nid = str(node.get("id") or "").strip()
        if not nid:
            errors.append(f"nodes[{idx}]: missing node id")
            continue
        if nid in node_ids:
            errors.append(f"nodes[{idx}]: duplicate node id '{nid}'")
        node_ids.add(nid)
        lat = node.get("lat")
        lng = node.get("lng")
        if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
            errors.append(f"nodes[{idx}]: invalid coordinates")

    for idx, route in enumerate(routes):
        from_id = str(route.get("from_node_id") or "").strip()
        to_id = str(route.get("to_node_id") or "").strip()
        mode = str(route.get("mode") or "").strip().lower()
        if from_id == to_id and from_id:
            errors.append(f"routes[{idx}]: self-route not allowed ({from_id})")
        if from_id not in node_ids:
            errors.append(f"routes[{idx}]: unknown from_node_id '{from_id}'")
        if to_id not in node_ids:
            errors.append(f"routes[{idx}]: unknown to_node_id '{to_id}'")
        if mode not in ALLOWED_MODES:
            errors.append(f"routes[{idx}]: invalid mode '{mode}'")
        if not route.get("id"):
            warnings.append(f"routes[{idx}]: missing stable route id")
    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)
