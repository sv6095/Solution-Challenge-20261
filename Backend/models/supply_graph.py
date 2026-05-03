"""
customer_supply_graph.py — Canonical Supply Chain Graph Model
=============================================================
Single source of truth for ALL supply chain graph operations in Praecantator.

This module defines the authoritative data shapes for:
  - Supplier nodes (Tier 1, 2, 3)
  - Logistics nodes (ports, DCs, factories)
  - Supply edges (buyer-supplier relationships)
  - Route corridors (mode-specific lanes)
  - Customer's complete network snapshot

Rules:
  - ALL graph construction MUST go through `CustomerSupplyGraph.from_context()`
    or `CustomerSupplyGraph.from_dataset()`.
  - Never instantiate SupplyChainGraph (gnn_stub) directly outside of
    CustomerSupplyGraph. It is an internal impl detail.
  - The canonical schema is the Pydantic model below, not dict literals.

Changed fields vs old gnn_stub.py:
  - Added `tenant_id` for row-level tenancy (see authorization layer)
  - Added `contract_currency` / `contract_currency_rate` for FX awareness
  - Added `is_pre_qualified` for RFQ eligibility
  - Added `tags` for flexible filtering (e.g., ["critical-path", "ESG-red"])
  - Added `node_type` discriminator: "supplier" | "logistics" | "customer"
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Literal


COUNTRY_LOCATION_REFERENCE: dict[str, tuple[float, float]] = {
    "in": (22.5937, 78.9629),
    "india": (22.5937, 78.9629),
    "de": (51.1657, 10.4515),
    "germany": (51.1657, 10.4515),
    "jp": (36.2048, 138.2529),
    "japan": (36.2048, 138.2529),
    "us": (39.8283, -98.5795),
    "usa": (39.8283, -98.5795),
    "united states": (39.8283, -98.5795),
    "united states of america": (39.8283, -98.5795),
    "cn": (35.8617, 104.1954),
    "china": (35.8617, 104.1954),
}

# ── Node model ────────────────────────────────────────────────────────────────


@dataclass
class SupplyNode:
    """
    Canonical supply chain node (supplier, logistics hub, or customer facility).

    This replaces the old SupplierNode from gnn_stub and is the authoritative
    shape used by:
      - GNN risk propagation (via SupplierNode adapter)
      - Frontend render (via to_dict())
      - Authorization layer (checks tenant_id)
      - Master-data validation (validates required fields)
    """

    # Identity
    id: str
    name: str
    tenant_id: str                          # owner tenant — used for row-level tenancy
    node_type: Literal["supplier", "logistics", "customer"] = "supplier"

    # Geo
    lat: float = 0.0
    lng: float = 0.0
    country: str = ""
    city: str = ""
    region: str = ""

    # Tier (1 = direct, 2 = sub-supplier, 3 = raw material, 0 = logistics/hub)
    tier: int = 1

    # Financial
    contract_value_usd: float = 100_000.0
    daily_throughput_usd: float = 10_000.0
    contract_currency: str = "USD"
    contract_currency_rate: float = 1.0     # rate to USD at last refresh

    # Risk profile
    criticality: Literal["critical", "high", "medium", "low"] = "medium"
    single_source: bool = False
    safety_stock_days: int = 7
    is_pre_qualified: bool = False          # eligible for direct RFQ
    location_precision: Literal["exact", "country", "synthetic"] = "exact"
    product_category: str = "general"

    # Metadata
    tags: list[str] = field(default_factory=list)
    external_id: str = ""                   # ERP / SAP / TMS reference
    onboarded_at: str = ""
    updated_at: str = ""

    # Computed at runtime (not stored)
    risk_score: float = 0.0
    exposure_usd: float = 0.0
    days_to_stockout: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def fingerprint(self) -> str:
        """Stable hash for deduplication — based on stable fields only."""
        key = f"{self.tenant_id}:{self.id}:{self.lat:.4f}:{self.lng:.4f}"
        return hashlib.md5(key.encode()).hexdigest()[:12]

    @classmethod
    def from_context_supplier(cls, tenant_id: str, raw: dict) -> "SupplyNode":
        """Build from onboarding context supplier dict."""
        tier_raw = raw.get("tier", raw.get("tier_level", 1))
        tier_num = _parse_tier_value(tier_raw, default=1)
        supplier_name = str(raw.get("name", "")).strip()
        country = str(raw.get("country", "")).strip()
        node_id = str(
            raw.get("id")
            or raw.get("supplier_id")
            or raw.get("external_id")
            or _stable_supplier_id(supplier_name, country, tier_num)
        )
        lat, lng, location_precision = _resolve_supply_coordinates(raw)
        daily_throughput = _coerce_float(raw.get("daily_throughput_usd"), 25_000.0)
        contract_value = _coerce_float(
            raw.get("contract_value_usd"),
            max(daily_throughput * 21.0, 250_000.0),
        )
        single_source = _coerce_bool(raw.get("single_source"), tier_num == 1)
        category = str(raw.get("category") or raw.get("products") or "general")
        return cls(
            id=node_id,
            name=supplier_name or node_id,
            tenant_id=tenant_id,
            node_type="supplier",
            lat=lat,
            lng=lng,
            country=country,
            city=str(raw.get("city", "")),
            tier=tier_num,
            contract_value_usd=contract_value,
            daily_throughput_usd=daily_throughput,
            criticality=str(raw.get("criticality", "medium")),  # type: ignore[arg-type]
            single_source=single_source,
            safety_stock_days=int(_coerce_float(raw.get("safety_stock_days"), 7)),
            is_pre_qualified=bool(raw.get("is_pre_qualified", False)),
            tags=list(raw.get("tags", [])),
            external_id=str(raw.get("external_id", "")),
            onboarded_at=str(raw.get("onboarded_at", "")),
            location_precision=location_precision,
            product_category=category,
        )

    @classmethod
    def from_context_logistics(cls, tenant_id: str, raw: dict) -> "SupplyNode":
        """Build from onboarding context logistics_node dict."""
        return cls(
            id=str(raw.get("id", "")),
            name=str(raw.get("name", "")),
            tenant_id=tenant_id,
            node_type="logistics",
            lat=float(raw.get("lat", 0)),
            lng=float(raw.get("lng", 0)),
            country=str(raw.get("country", "")),
            tier=0,
            criticality=str(raw.get("criticality", "medium")),  # type: ignore[arg-type]
            tags=list(raw.get("tags", [])),
            location_precision="exact" if raw.get("lat") and raw.get("lng") else "synthetic",
        )

    @classmethod
    def from_dataset_row(cls, tenant_id: str, raw: dict) -> "SupplyNode":
        """Build from backend dataset dict (demo / fallback mode)."""
        tier_num = _parse_tier_value(raw.get("tier", "Tier 1"), default=1)
        exposure = float(raw.get("exposureScore", 50))

        return cls(
            id=str(raw.get("id", "")),
            name=str(raw.get("name", "")),
            tenant_id=tenant_id,
            node_type="supplier",
            lat=float(raw.get("lat", 0)),
            lng=float(raw.get("lng", 0)),
            country=str(raw.get("country", "")),
            tier=tier_num,
            contract_value_usd=exposure * 1000,
            daily_throughput_usd=exposure * 100,
            single_source=exposure >= 80,
            safety_stock_days=max(3, 14 - int(exposure / 10)),
            criticality=(
                "critical" if exposure >= 80
                else "high" if exposure >= 60
                else "medium"
            ),
            location_precision="exact" if raw.get("lat") and raw.get("lng") else "synthetic",
        )


def _coerce_float(value: Any, default: float) -> float:
    try:
        if value in ("", None):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_bool(value: Any, default: bool) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return default


def _stable_supplier_id(name: str, country: str, tier: int) -> str:
    basis = f"{name.strip().lower()}|{country.strip().lower()}|{tier}"
    digest = hashlib.md5(basis.encode("utf-8")).hexdigest()[:12]
    return f"sup_{digest}"


def _resolve_supply_coordinates(raw: dict[str, Any]) -> tuple[float, float, Literal["exact", "country", "synthetic"]]:
    lat = _coerce_float(raw.get("lat"), 0.0)
    lng = _coerce_float(raw.get("lng"), 0.0)
    if abs(lat) > 0.0001 or abs(lng) > 0.0001:
        return lat, lng, "exact"
    country = str(raw.get("country", "")).strip().lower()
    if country in COUNTRY_LOCATION_REFERENCE:
        ref_lat, ref_lng = COUNTRY_LOCATION_REFERENCE[country]
        return ref_lat, ref_lng, "country"
    return 0.0, 0.0, "synthetic"


def _parse_tier_value(value: Any, default: int = 1) -> int:
    """
    Parse tier from heterogeneous legacy formats:
      1, "1", "Tier 1", "tier_2", "T3"
    """
    if isinstance(value, (int, float)):
        parsed = int(value)
        return parsed if parsed in (0, 1, 2, 3) else default
    raw = str(value or "").strip().lower()
    if not raw:
        return default
    match = re.search(r"([0-3])", raw)
    if not match:
        return default
    parsed = int(match.group(1))
    return parsed if parsed in (0, 1, 2, 3) else default


# ── Edge model ────────────────────────────────────────────────────────────────


@dataclass
class SupplyEdge:
    """Canonical directed supply relationship between two nodes."""
    from_id: str
    to_id: str
    tenant_id: str

    tier_level: int = 1
    lead_time_days: int = 7
    substitutability: float = 0.5           # 0 = sole-source, 1 = many alternatives
    mode: Literal["sea", "air", "land", "rail", "multimodal"] = "sea"

    # Contract metadata
    annual_value_usd: float = 0.0
    incoterm: str = "FOB"
    payment_terms_days: int = 30

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Canonical graph ───────────────────────────────────────────────────────────


class CustomerSupplyGraph:
    """
    Canonical supply chain graph for one tenant.

    This is the ONLY way to construct a graph used by the pipeline.
    Do not call gnn_stub.build_graph_from_context() directly.

    Usage:
        graph = CustomerSupplyGraph.from_context(tenant_id, context)
        gnn_graph = graph.to_gnn_graph()  # delegate to gnn_stub for compute
        result = gnn_graph.propagate_risk(disruption)
    """

    GRAPH_VERSION = "1.0"

    def __init__(self, tenant_id: str, source: Literal["context", "dataset"]) -> None:
        self.tenant_id = tenant_id
        self.source = source
        self.nodes: dict[str, SupplyNode] = {}
        self.edges: list[SupplyEdge] = []
        self.built_at: str = datetime.now(timezone.utc).isoformat()
        self.metadata: dict[str, Any] = {}

    # ── Builders ──────────────────────────────────────────────────────────────

    @classmethod
    def from_context(cls, tenant_id: str, context: dict) -> "CustomerSupplyGraph":
        """Build canonical graph from onboarding context (stored in DB)."""
        g = cls(tenant_id=tenant_id, source="context")
        g.metadata["company_name"] = str(context.get("company_name", ""))

        for raw in context.get("suppliers", []):
            node = SupplyNode.from_context_supplier(tenant_id, raw)
            if node.id:
                g.nodes[node.id] = node

        for raw in context.get("logistics_nodes", []):
            node = SupplyNode.from_context_logistics(tenant_id, raw)
            if node.id:
                g.nodes[node.id] = node

        g._auto_wire_edges()
        return g

    @classmethod
    def from_dataset(cls, tenant_id: str, suppliers: list[dict]) -> "CustomerSupplyGraph":
        """Build canonical graph from raw dataset (demo / fallback mode)."""
        g = cls(tenant_id=tenant_id, source="dataset")

        for raw in suppliers:
            node = SupplyNode.from_dataset_row(tenant_id, raw)
            if node.id:
                g.nodes[node.id] = node

        g._auto_wire_edges()
        return g

    # ── Edge wiring ───────────────────────────────────────────────────────────

    def _auto_wire_edges(self) -> None:
        """Wire tier-based supply edges automatically (same logic as gnn_stub)."""
        node_ids = list(self.nodes.keys())

        # Tier N → Tier N-1 connections
        for nid in node_ids:
            node = self.nodes[nid]
            for other_id in node_ids:
                if nid == other_id:
                    continue
                other = self.nodes[other_id]
                if node.tier == other.tier + 1:
                    self.edges.append(SupplyEdge(
                        from_id=nid,
                        to_id=other_id,
                        tenant_id=self.tenant_id,
                        tier_level=node.tier,
                        substitutability=0.2 if node.single_source else 0.6,
                    ))
                    break

        # Fallback: simple chain if no edges were created
        if not self.edges and len(node_ids) > 1:
            for i in range(len(node_ids) - 1):
                self.edges.append(SupplyEdge(
                    from_id=node_ids[i],
                    to_id=node_ids[i + 1],
                    tenant_id=self.tenant_id,
                    tier_level=1,
                    substitutability=0.5,
                ))

    def add_edge(self, edge: SupplyEdge) -> None:
        if edge.tenant_id != self.tenant_id:
            raise ValueError(
                f"Edge tenant '{edge.tenant_id}' does not match graph tenant '{self.tenant_id}'"
            )
        self.edges.append(edge)

    # ── gnn_stub adapter ──────────────────────────────────────────────────────

    def to_gnn_graph(self):
        """
        Convert this canonical graph to gnn_stub.SupplyChainGraph for risk compute.
        This is the ONLY bridge between the canonical model and the GNN layer.
        """
        from ml.gnn_stub import SupplyChainGraph as GNNGraph, SupplierNode as GNNNode, SupplyEdge as GNNEdge

        gnn = GNNGraph()
        for node in self.nodes.values():
            gnn.add_node(GNNNode(
                id=node.id,
                name=node.name,
                tier=node.tier,
                lat=node.lat,
                lng=node.lng,
                country=node.country,
                contract_value_usd=node.contract_value_usd,
                daily_throughput_usd=node.daily_throughput_usd,
                product_category=node.product_category if hasattr(node, "product_category") else "general",
                safety_stock_days=node.safety_stock_days,
                single_source=node.single_source,
                criticality=node.criticality,
                location_precision=node.location_precision,
            ))
        for edge in self.edges:
            gnn.add_edge(GNNEdge(
                from_id=edge.from_id,
                to_id=edge.to_id,
                tier_level=edge.tier_level,
                substitutability=edge.substitutability,
                mode=edge.mode,
                lead_time_days=edge.lead_time_days,
            ))
        return gnn

    # ── Utilities ─────────────────────────────────────────────────────────────

    def get_pre_qualified_suppliers(self) -> list[SupplyNode]:
        """Return nodes eligible for direct RFQ dispatch."""
        return [n for n in self.nodes.values() if n.is_pre_qualified and n.node_type == "supplier"]

    def get_nodes_by_tier(self, tier: int) -> list[SupplyNode]:
        return [n for n in self.nodes.values() if n.tier == tier]

    def get_supplier_dicts(self) -> list[dict[str, Any]]:
        """Flat list of supplier dicts for backup-selection logic."""
        return [n.to_dict() for n in self.nodes.values() if n.node_type == "supplier"]

    def summary(self) -> dict[str, Any]:
        tiers = {}
        for n in self.nodes.values():
            tiers[n.tier] = tiers.get(n.tier, 0) + 1
        return {
            "tenant_id": self.tenant_id,
            "graph_version": self.GRAPH_VERSION,
            "source": self.source,
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "tier_breakdown": tiers,
            "built_at": self.built_at,
            "metadata": self.metadata,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
        }
