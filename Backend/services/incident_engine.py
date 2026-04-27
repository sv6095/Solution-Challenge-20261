"""
Incident Engine — The autonomous pipeline.

This is the core of the v4 redesign:
  Event detected → GNN scores all tiers → incident auto-created → user approves

No user interaction until the final approval step.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4
import math
import difflib

from ml.gnn_stub import (
    DisruptionEvent,
    GNNResult,
    SupplyChainGraph,
    build_graph_from_dataset,
)
from agents.reasoning_logger import log_reasoning_step
from services.erp_sync import fetch_live_node_state


IncidentStatus = Literal[
    "DETECTED",
    "ANALYZED",
    "AWAITING_APPROVAL",
    "APPROVED",
    "EXECUTING",
    "RESOLVED",
    "DISMISSED",
    "AUTO_RESOLVED",
]

IncidentSeverity = Literal["CRITICAL", "HIGH", "MODERATE", "LOW"]


@dataclass
class RouteOption:
    mode: str  # sea | air | land
    description: str
    transit_days: float
    cost_usd: float
    risk_score: float
    recommended: bool = False


@dataclass
class Incident:
    id: str
    event_id: str
    event_title: str
    event_type: str
    event_description: str
    event_lat: float
    event_lng: float
    severity: IncidentSeverity
    status: IncidentStatus
    affected_node_count: int = 0
    total_exposure_usd: float = 0.0
    revenue_at_risk_usd: float = 0.0
    margin_exposed_usd: float = 0.0
    min_stockout_days: float = 0.0
    gnn_confidence: float = 0.0
    affected_nodes: list[dict] = field(default_factory=list)
    route_options: list[dict] = field(default_factory=list)
    recommendation: str = ""
    recommendation_detail: str = ""
    rfq_draft: dict = field(default_factory=dict)
    created_at: str = ""
    analyzed_at: str = ""
    approved_at: str = ""
    resolved_at: str = ""
    approved_by: str = ""
    dismiss_reason: str = ""
    source_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _severity_from_score(score: float) -> IncidentSeverity:
    if score >= 8:
        return "CRITICAL"
    if score >= 6:
        return "HIGH"
    if score >= 4:
        return "MODERATE"
    return "LOW"


def _score_from_severity(label: str) -> float:
    mapping = {"CRITICAL": 9.0, "HIGH": 7.0, "MODERATE": 5.0, "LOW": 3.0}
    return mapping.get(label.upper(), 5.0)


class IncidentEngine:
    """
    Autonomous incident pipeline.

    When a disruption event is detected:
    1. Build/load the supplier graph
    2. Run GNN forward pass → risk scores for all nodes
    3. If affected nodes exist → create Incident
    4. Auto-compute route options + RFQ draft
    5. Surface to user as AWAITING_APPROVAL
    """

    def __init__(self) -> None:
        self._graph: SupplyChainGraph | None = None

    def _build_subgraph(self, event: DisruptionEvent, suppliers: list[dict]) -> SupplyChainGraph:
        """
        OOM Prevention: Instead of holding millions of nodes in memory,
        this acts as a CTE/GraphDB proxy, filtering down to only the impacted
        subgraph (nodes within radius + immediate N-tier dependents).
        """
        # Step A: Geographic bounding box filter (simulating PostGIS / Neo4j spatial query)
        lat_bound = event.radius_km / 111.0 # roughly 111 km per degree lat
        lng_bound = event.radius_km / (111.0 * max(0.1, abs(math.cos(math.radians(event.lat)))))
        
        impacted_candidates = []
        for s in suppliers:
            name = str(s.get("name") or "").lower()
            evt_title = str(event.title or "").lower()
            evt_desc = str(event.description or "").lower()
            
            # 1. Geographic Check
            slat = float(s.get("lat") or 0)
            slng = float(s.get("lng") or 0)
            geo_match = (event.lat - lat_bound <= slat <= event.lat + lat_bound) and \
                        (event.lng - lng_bound <= slng <= event.lng + lng_bound)
                        
            # 2. Fuzzy Naming Check (Zero-Match Fix)
            # If the event lacks precise geo, or name variation exists, fallback to text similarity
            text_match = False
            if name and len(name) > 3:
                if name in evt_title or name in evt_desc:
                    text_match = True
                else:
                    # Fuzzy match threshold > 0.8
                    title_sim = difflib.SequenceMatcher(None, name, evt_title).ratio()
                    if title_sim > 0.80:
                        text_match = True

            if geo_match or text_match:
                impacted_candidates.append(s)
                
        # If no nodes in bounding box, don't even build the memory stub
        if not impacted_candidates:
            return SupplyChainGraph()
            
        # Step B: Graph Traversal and ERP Live Data Hydration
        tier_set = {int(s.get("tier", 1)) for s in impacted_candidates}
        subgraph_nodes = []
        for s in suppliers:
            t = int(s.get("tier", 1))
            if t in tier_set or t in {t - 1 for t in tier_set} or t in {t + 1 for t in tier_set}:
                # Real-time ERP injection overriding static onboarding data
                duns = s.get("dunsNumber") or s.get("duns_number") or ""
                live_state = fetch_live_node_state(duns, s.get("id", ""))
                s["safety_stock_days"] = live_state["live_safety_stock_days"]
                s["daily_throughput_usd"] = live_state["live_daily_throughput_usd"]
                s["contract_value_usd"] = live_state["live_daily_throughput_usd"] * 365
                s["margin_percentage"] = live_state["margin_percentage"]
                subgraph_nodes.append(s)
                
        return build_graph_from_dataset(subgraph_nodes)

    def process_event(
        self,
        event_data: dict,
        suppliers: list[dict],
        routes_fn=None,
    ) -> Incident | None:
        """
        The main autonomous pipeline. Takes a raw event dict from the signal agent
        and returns a fully analyzed Incident (or None if no impact).
        """
        now = datetime.now(timezone.utc).isoformat()
        incident_id = f"inc_{uuid4().hex[:12]}"

        # Parse event
        severity_raw = float(event_data.get("severity", 0) or 0)
        if isinstance(event_data.get("severity"), str):
            severity_raw = _score_from_severity(event_data["severity"])

        event = DisruptionEvent(
            id=str(event_data.get("id", "")),
            title=str(event_data.get("title", "Unknown event")),
            event_type=str(event_data.get("event_type", event_data.get("type", "disruption"))),
            severity=severity_raw,
            lat=float(event_data.get("lat", 0) or 0),
            lng=float(event_data.get("lng", 0) or 0),
            radius_km=float(event_data.get("radius_km", 500)),
            duration_days=float(event_data.get("duration_days", 7)),
            description=str(event_data.get("description", "")),
            source=str(event_data.get("source", event_data.get("analyst", ""))),
            url=str(event_data.get("url", "")),
        )

        # Skip zero-location events
        if event.lat == 0 and event.lng == 0:
            return None

        # Step 1: Build bounded subgraph (mitigating OOM)
        graph = self._build_subgraph(event, suppliers)
        if len(graph.nodes) == 0:
            return None

        # Step 2: GNN forward pass
        gnn_result = graph.propagate_risk(event)

        # No affected nodes → log and skip
        if not gnn_result.affected_nodes:
            return None

        # Step 3: Build incident
        severity_label = _severity_from_score(event.severity)
        total_exposure = sum(n.exposure_usd for n in gnn_result.affected_nodes)
        
        # Calculate pure financial metrics from ERP margin data
        margin_exposed = sum((n.exposure_usd * getattr(n, "margin_percentage", 0.20)) for n in gnn_result.affected_nodes)

        # Step 4: Generate route options (stub — real version calls routing_agent)
        route_options = self._generate_route_options(event, gnn_result)

        # Step 5: Build recommendation
        rec, rec_detail = self._build_recommendation(
            gnn_result, route_options, severity_label
        )

        # Step 6: Draft RFQ stub
        rfq_draft = self._draft_rfq(event, gnn_result)

        analyzed_at = datetime.now(timezone.utc).isoformat()

        incident = Incident(
            id=incident_id,
            event_id=event.id,
            event_title=event.title,
            event_type=event.event_type,
            event_description=event.description,
            event_lat=event.lat,
            event_lng=event.lng,
            severity=severity_label,
            status="AWAITING_APPROVAL" if severity_label in ("CRITICAL", "HIGH") else "ANALYZED",
            affected_node_count=len(gnn_result.affected_nodes),
            total_exposure_usd=round(total_exposure, 2),
            revenue_at_risk_usd=round(total_exposure, 2),
            margin_exposed_usd=round(margin_exposed, 2),
            min_stockout_days=gnn_result.min_stockout_days,
            gnn_confidence=gnn_result.confidence,
            affected_nodes=[asdict(n) for n in gnn_result.affected_nodes],
            route_options=route_options,
            recommendation=rec,
            recommendation_detail=rec_detail,
            rfq_draft=rfq_draft,
            created_at=now,
            analyzed_at=analyzed_at,
            source_url=event.url,
        )

        return incident

    def _generate_route_options(
        self, event: DisruptionEvent, gnn_result: GNNResult
    ) -> list[dict]:
        """Generate route alternatives. Sprint 1: stub data. Sprint 2: real routing agents."""
        options = []
        base_cost = 5000 + event.severity * 500
        base_days = max(2, 14 - event.severity)

        # Air option (fastest, most expensive)
        options.append({
            "mode": "air",
            "description": f"Air freight bypass — avoids {event.title} impact zone",
            "transit_days": round(base_days * 0.3, 1),
            "cost_usd": round(base_cost * 2.5, 0),
            "risk_score": round(max(0.1, 1.0 - gnn_result.confidence) * 0.3, 2),
            "recommended": event.severity >= 7,
        })

        # Sea reroute
        options.append({
            "mode": "sea",
            "description": f"Sea reroute — alternative corridor avoiding disruption",
            "transit_days": round(base_days * 1.5, 1),
            "cost_usd": round(base_cost * 0.8, 0),
            "risk_score": round(max(0.2, 1.0 - gnn_result.confidence) * 0.6, 2),
            "recommended": 4 <= event.severity < 7,
        })

        # Land/rail
        options.append({
            "mode": "land",
            "description": f"Land/rail contingency route",
            "transit_days": round(base_days * 1.2, 1),
            "cost_usd": round(base_cost * 1.1, 0),
            "risk_score": round(max(0.15, 1.0 - gnn_result.confidence) * 0.5, 2),
            "recommended": False,
        })

        return options

    def _build_recommendation(
        self,
        gnn_result: GNNResult,
        route_options: list[dict],
        severity: str,
    ) -> tuple[str, str]:
        """Build human-readable recommendation."""
        if severity == "CRITICAL":
            rec = "ACTIVATE BACKUP SUPPLIER + AIR FREIGHT"
            detail = (
                f"GNN confidence {gnn_result.confidence:.0%}. "
                f"{len(gnn_result.affected_nodes)} nodes at risk. "
                f"Stockout in {gnn_result.min_stockout_days:.0f} days. "
                f"Recommend immediate air freight reroute and backup supplier activation."
            )
        elif severity == "HIGH":
            rec = "REROUTE SHIPMENTS"
            detail = (
                f"GNN confidence {gnn_result.confidence:.0%}. "
                f"{len(gnn_result.affected_nodes)} nodes affected. "
                f"Recommend sea/air reroute within 48h to prevent stockout."
            )
        elif severity == "MODERATE":
            rec = "MONITOR — AUTO-RESOLVE IF STABLE"
            detail = (
                f"GNN confidence {gnn_result.confidence:.0%}. "
                f"Impact moderate. System will auto-resolve if conditions stabilize within 48h."
            )
        else:
            rec = "LOW PRIORITY — LOGGED"
            detail = f"Minimal network impact. Logged for compliance records."

        return rec, detail

    def _draft_rfq(self, event: DisruptionEvent, gnn_result: GNNResult) -> dict:
        """Draft RFQ for backup supplier. Sprint 1: template. Sprint 2: Gemini drafts."""
        if not gnn_result.affected_nodes:
            return {}
        top_node = gnn_result.affected_nodes[0]
        return {
            "to": f"procurement@backup-supplier.com",
            "subject": f"Emergency RFQ — {top_node.name} Disruption — Ref {event.id[:8].upper()}",
            "body": (
                f"Dear Procurement Team,\n\n"
                f"Due to {event.title} ({event.event_type}), our supply node "
                f"'{top_node.name}' (Tier {top_node.tier}) is at risk.\n\n"
                f"GNN Risk Score: {top_node.risk_score:.0%}\n"
                f"Financial Exposure: ${top_node.exposure_usd:,.0f} USD\n"
                f"Days to Stockout: {top_node.days_to_stockout:.0f}\n\n"
                f"We require emergency supply for the affected components. "
                f"Please provide availability and pricing within 24 hours.\n\n"
                f"Best regards,\nPraecantator Autonomous SCRM"
            ),
            "editable": True,
        }

    def approve_incident(self, incident: Incident, user_id: str) -> Incident:
        """User approves the recommended action."""
        incident.status = "APPROVED"
        incident.approved_at = datetime.now(timezone.utc).isoformat()
        incident.approved_by = user_id
        return incident

    def dismiss_incident(self, incident: Incident, reason: str, user_id: str) -> Incident:
        """User dismisses with reason."""
        incident.status = "DISMISSED"
        incident.dismiss_reason = reason
        incident.approved_at = datetime.now(timezone.utc).isoformat()
        incident.approved_by = user_id
        return incident

    def resolve_incident(self, incident: Incident) -> Incident:
        """Mark as resolved after execution."""
        incident.status = "RESOLVED"
        incident.resolved_at = datetime.now(timezone.utc).isoformat()
        return incident


# Singleton
incident_engine = IncidentEngine()
