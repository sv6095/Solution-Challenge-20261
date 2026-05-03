"""
GNN Stub — Lightweight graph risk propagation.

Sprint 1: Weighted message-passing on a NetworkX graph.
Sprint 2: Replace with PyTorch Geometric GraphSAGE+GAT.

The core idea: when a disruption event hits a geographic region,
risk propagates THROUGH the supplier dependency graph.
A Tier 2 supplier failure cascades to Tier 1, which cascades to the company.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class SupplierNode:
    id: str
    name: str
    tier: int  # 1, 2, 3
    lat: float
    lng: float
    country: str = ""
    contract_value_usd: float = 100_000
    daily_throughput_usd: float = 10_000
    margin_percentage: float = 0.20
    product_category: str = "general"
    safety_stock_days: int = 7
    single_source: bool = False
    criticality: str = "medium"  # critical | high | medium | low
    location_precision: str = "exact"  # exact | country | synthetic
    risk_score: float = 0.0  # computed by GNN
    exposure_usd: float = 0.0  # computed
    days_to_stockout: float = 0.0  # computed


@dataclass
class SupplyEdge:
    from_id: str
    to_id: str
    tier_level: int = 1
    lead_time_days: int = 7
    substitutability: float = 0.5  # 0 = sole source, 1 = many alternatives
    mode: str = "sea"


@dataclass
class DisruptionEvent:
    id: str
    title: str
    event_type: str
    severity: float  # 0-10
    lat: float
    lng: float
    radius_km: float = 500.0
    duration_days: float = 7.0
    description: str = ""
    source: str = ""
    url: str = ""


@dataclass
class GNNResult:
    """Output of a single GNN forward pass."""
    event: DisruptionEvent
    affected_nodes: list[SupplierNode] = field(default_factory=list)
    all_scores: dict[str, float] = field(default_factory=dict)
    max_exposure_usd: float = 0.0
    min_stockout_days: float = 999.0
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event.id,
            "event_title": self.event.title,
            "affected_count": len(self.affected_nodes),
            "affected_nodes": [asdict(n) for n in self.affected_nodes],
            "max_exposure_usd": round(self.max_exposure_usd, 2),
            "min_stockout_days": round(self.min_stockout_days, 1),
            "confidence": round(self.confidence, 3),
            "all_scores": {k: round(v, 3) for k, v in self.all_scores.items()},
        }


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _proximity_score(event: DisruptionEvent, node: SupplierNode) -> float:
    """0–1 score: how close is the node to the event?"""
    dist = _haversine_km(event.lat, event.lng, node.lat, node.lng)
    effective_radius = event.radius_km
    if node.location_precision == "country":
        effective_radius = max(event.radius_km * 12.0, 3000.0)
    elif node.location_precision == "synthetic":
        effective_radius = max(event.radius_km * 8.0, 1800.0)
    if dist >= effective_radius:
        return 0.0
    return max(0.0, 1.0 - (dist / effective_radius))


def _criticality_weight(node: SupplierNode) -> float:
    """Multiplier based on node criticality."""
    weights = {"critical": 1.5, "high": 1.2, "medium": 1.0, "low": 0.7}
    return weights.get(node.criticality, 1.0)


class SupplyChainGraph:
    """
    In-memory supply chain graph for risk propagation.

    Sprint 1: Simple weighted message-passing.
    Sprint 2: Replace with PyG Data + GraphSAGE model.
    """

    def __init__(self) -> None:
        self.nodes: dict[str, SupplierNode] = {}
        self.edges: list[SupplyEdge] = []
        # adjacency: node_id -> list of (neighbor_id, edge)
        self._adj: dict[str, list[tuple[str, SupplyEdge]]] = {}

    def add_node(self, node: SupplierNode) -> None:
        self.nodes[node.id] = node
        self._adj.setdefault(node.id, [])

    def add_edge(self, edge: SupplyEdge) -> None:
        self.edges.append(edge)
        self._adj.setdefault(edge.from_id, []).append((edge.to_id, edge))
        self._adj.setdefault(edge.to_id, []).append((edge.from_id, edge))

    def propagate_risk(
        self,
        event: DisruptionEvent,
        iterations: int = 3,
        affected_score_threshold: float = 0.3,
    ) -> GNNResult:
        """
        Message-passing risk propagation.

        Dispatch order:
        1. If trained GNN weights exist → use PyTorch Geometric model (gnn_model.py)
        2. Otherwise → fall back to heuristic message-passing below

        The heuristic path:
        1. Seed: nodes within event radius get initial risk from proximity × severity.
        2. Propagate: risk flows through edges, weighted by:
           - (1 - substitutability): sole-source edges propagate more risk
           - tier weight: downstream propagation is amplified
           - single_source flag: 1.5× multiplier
        3. After `iterations` rounds, compute financial exposure and stockout days.
        """
        # ── Try trained GNN model first ───────────────────────────────────
        try:
            from ml.gnn_model import propagate_risk_learned
            learned_result = propagate_risk_learned(
                self, event, affected_score_threshold=affected_score_threshold
            )
            if learned_result is not None:
                return learned_result
        except Exception:
            pass  # Graceful fallback to heuristic

        # ── Heuristic fallback ────────────────────────────────────────────
        severity_factor = min(1.0, event.severity / 10.0)

        # Step 1: Seed scores from geographic proximity
        scores: dict[str, float] = {}
        for nid, node in self.nodes.items():
            prox = _proximity_score(event, node)
            if prox > 0:
                base = prox * severity_factor * _criticality_weight(node)
                if node.single_source:
                    base *= 1.3
                if node.location_precision == "country":
                    base *= 1.4
                elif node.location_precision == "synthetic":
                    base *= 1.15
                # Use tanh for a smooth probability curve that approaches but rarely hits 1.0
                scores[nid] = min(0.985, math.tanh(base))
            else:
                scores[nid] = 0.0

        # Step 2: Message passing (risk propagation through edges)
        for _ in range(iterations):
            new_scores = dict(scores)
            for nid in self.nodes:
                neighbors = self._adj.get(nid, [])
                if not neighbors:
                    continue
                incoming_risk = 0.0
                for neighbor_id, edge in neighbors:
                    neighbor_score = scores.get(neighbor_id, 0.0)
                    if neighbor_score <= 0:
                        continue
                    # Edge weight: sole-source edges propagate more
                    edge_weight = 1.0 - (edge.substitutability * 0.5)
                    # Tier amplification: Tier 2→1 carries more weight than 3→2
                    tier_factor = 1.0 / max(1.2, edge.tier_level)
                    propagated = neighbor_score * edge_weight * tier_factor * 0.75
                    incoming_risk = max(incoming_risk, propagated)

                # Node keeps max of its own score vs propagated risk, capped realistically
                new_scores[nid] = min(0.985, max(new_scores[nid], incoming_risk))
            scores = new_scores

        # Step 3: Compute financial impact for affected nodes
        affected: list[SupplierNode] = []
        max_exposure = 0.0
        min_stockout = 999.0

        for nid, score in scores.items():
            if score < affected_score_threshold:
                continue
            node = self.nodes[nid]
            node.risk_score = round(score, 3)
            # Financial exposure = contract × probability × duration / lead_time
            duration_factor = min(1.0, event.duration_days / 30.0)
            node.exposure_usd = round(
                node.contract_value_usd * score * duration_factor, 2
            )
            # Days to stockout
            if severity_factor > 0:
                node.days_to_stockout = round(
                    node.safety_stock_days / (1 + severity_factor * score), 1
                )
            else:
                node.days_to_stockout = node.safety_stock_days
                
            # BOM Granularity: Perishables degrade into total loss upon delay
            if node.product_category.lower() in ("cold-chain", "perishable", "hazardous"):
                if node.days_to_stockout < node.safety_stock_days - 1.0:
                    node.exposure_usd = node.contract_value_usd
                    node.days_to_stockout = 0.0

            max_exposure = max(max_exposure, node.exposure_usd)
            min_stockout = min(min_stockout, node.days_to_stockout)
            affected.append(node)

        # Sort by risk score descending
        affected.sort(key=lambda n: n.risk_score, reverse=True)

        # Confidence = algorithmic certainty based on signal overlap and node density
        if affected:
            avg_prox = sum(_proximity_score(event, n) for n in affected) / len(affected)
            node_coverage = min(0.15, len(affected) * 0.01)
            # Realistic max confidence ~96%, dependent on proximity + quantity of nodes
            confidence = min(0.96, 0.75 + node_coverage + (avg_prox * 0.1))
        else:
            confidence = 0.0

        return GNNResult(
            event=event,
            affected_nodes=affected,
            all_scores=scores,
            max_exposure_usd=max_exposure,
            min_stockout_days=min_stockout if min_stockout < 999 else 0,
            confidence=round(confidence, 3),
        )


def build_graph_from_context(context: dict) -> SupplyChainGraph:
    """
    Build a SupplyChainGraph from the user's onboarding context
    (stored in Firestore/SQLite).
    """
    graph = SupplyChainGraph()

    # Add supplier nodes
    for s in context.get("suppliers", []):
        node = SupplierNode(
            id=str(s.get("id", "")),
            name=str(s.get("name", "")),
            tier=int(s.get("tier", 1)),
            lat=float(s.get("lat", 0)),
            lng=float(s.get("lng", 0)),
            country=str(s.get("country", "")),
            product_category=str(s.get("category") or s.get("products") or "general"),
            contract_value_usd=float(s.get("contract_value_usd", s.get("daily_throughput_usd", 100_000))),
            daily_throughput_usd=float(s.get("daily_throughput_usd", 10_000)),
            safety_stock_days=int(s.get("safety_stock_days", 7)),
            single_source=bool(s.get("single_source", False)),
            criticality=str(s.get("criticality", "medium")),
        )
        graph.add_node(node)

    # Add logistics nodes
    for n in context.get("logistics_nodes", []):
        node = SupplierNode(
            id=str(n.get("id", "")),
            name=str(n.get("name", "")),
            tier=0,  # logistics nodes are tier 0 (your infrastructure)
            lat=float(n.get("lat", 0)),
            lng=float(n.get("lng", 0)),
            country=str(n.get("country", "")),
            criticality=str(n.get("criticality", "medium")),
        )
        graph.add_node(node)

    # Add edges (supply relationships)
    node_ids = list(graph.nodes.keys())
    for i, nid in enumerate(node_ids):
        node = graph.nodes[nid]
        # Auto-connect: each Tier 2 connects to at least one Tier 1
        for j, other_id in enumerate(node_ids):
            if nid == other_id:
                continue
            other = graph.nodes[other_id]
            # Connect Tier N to Tier N-1
            if node.tier == other.tier + 1:
                graph.add_edge(SupplyEdge(
                    from_id=nid,
                    to_id=other_id,
                    tier_level=node.tier,
                    substitutability=0.2 if node.single_source else 0.6,
                    mode="sea",
                ))
                break  # one connection per tier is enough for stub

    # If no explicit edges, create a simple chain from suppliers
    if not graph.edges and len(node_ids) > 1:
        for i in range(len(node_ids) - 1):
            graph.add_edge(SupplyEdge(
                from_id=node_ids[i],
                to_id=node_ids[i + 1],
                tier_level=1,
                substitutability=0.5,
            ))

    return graph


def build_graph_from_dataset(suppliers: list[dict]) -> SupplyChainGraph:
    """
    Build graph from the backend _dataset_suppliers() output.
    Used when no user context exists (demo mode).
    """
    graph = SupplyChainGraph()

    for s in suppliers:
        tier_str = str(s.get("tier", "Tier 1"))
        tier_num = int(tier_str.replace("Tier ", "").strip()) if "Tier" in tier_str else 1
        exposure = float(s.get("exposureScore", 50))

        node = SupplierNode(
            id=str(s.get("id", "")),
            name=str(s.get("name", "")),
            tier=tier_num,
            lat=float(s.get("lat", 0)),
            lng=float(s.get("lng", 0)),
            country=str(s.get("country", "")),
            product_category=str(s.get("category") or s.get("products") or "general"),
            contract_value_usd=exposure * 1000 if not s.get("margin_percentage") else float(s.get("contract_value_usd", 100000)),
            daily_throughput_usd=exposure * 100 if not s.get("margin_percentage") else float(s.get("daily_throughput_usd", 10000)),
            margin_percentage=float(s.get("margin_percentage", 0.20)),
            safety_stock_days=max(3, 14 - int(exposure / 10)) if not s.get("margin_percentage") else int(s.get("safety_stock_days", 7)),
            single_source=exposure >= 80,
            criticality="critical" if exposure >= 80 else "high" if exposure >= 60 else "medium",
        )
        graph.add_node(node)

    # Create tier-based edges
    nodes_by_tier: dict[int, list[str]] = {}
    for nid, node in graph.nodes.items():
        nodes_by_tier.setdefault(node.tier, []).append(nid)

    for tier in sorted(nodes_by_tier.keys()):
        if tier <= 1:
            continue
        upstream = nodes_by_tier.get(tier, [])
        downstream = nodes_by_tier.get(tier - 1, [])
        if not downstream:
            continue
        for i, up_id in enumerate(upstream):
            down_id = downstream[i % len(downstream)]
            graph.add_edge(SupplyEdge(
                from_id=up_id,
                to_id=down_id,
                tier_level=tier,
                substitutability=0.3 if graph.nodes[up_id].single_source else 0.6,
                mode=str(graph.nodes[up_id].criticality),
            ))

    # Chain within same tier for proximity-based propagation
    for tier, ids in nodes_by_tier.items():
        for i in range(min(len(ids) - 1, 5)):  # limit cross-connections
            graph.add_edge(SupplyEdge(
                from_id=ids[i],
                to_id=ids[i + 1],
                tier_level=tier,
                substitutability=0.7,
            ))

    return graph
